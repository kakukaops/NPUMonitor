import copy,json,math,tempfile,time,unittest
from pathlib import Path
from npumonitor_rules.bundle import compile_bundle,digest,expand_recovery
from npumonitor_rules.store import Store,Conflict
from npumonitor_rules.source import normalize,SourceError

ROOT=Path(__file__).resolve().parents[2]

def config():
    import yaml
    return {'deployment_id':'unit','contract_profile':'dcgm-os-sre-physical-v1',
        'profile':yaml.safe_load((ROOT/'monitoring/os-sre/profile.yaml').read_text()),
        'upstream':{'url':'http://prometheus:9090'},'gateway':{'admin_token_file':'/run/admin','viewer_token_file':'/run/viewer'},
        'limits':{'max_source_gap_seconds':10},'rule_overrides':{'os_sre.gpu_thermal':{'for_seconds':4}}}

class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.bundle=compile_bundle(config(),ROOT)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'state.sqlite';Store.initialize(self.path,self.bundle);self.store=Store(self.path,'unit');self.identity={'job':'dcgm','instance':'node:9400','UUID':'GPU-1'}
    def tearDown(self):self.tmp.cleanup()
    def apply(self,value,stamp,now=None,rule='os_sre.gpu_thermal',error=None):
        result={'rule_id':rule,'samples':[] if value is None else [{'identity':self.identity,'value':value,'source_time':stamp}],'error':error}
        self.store.apply_cycle([result],self.store.current()[1],stamp if now is None else now)
        return self.store.snapshot()['states'][0]
    def test_explicit_initialization_and_lost_volume_fail_closed(self):
        with self.assertRaises(Exception):Store(Path(self.tmp.name)/'missing.sqlite','unit')
        self.assertFalse(Store.initialize(self.path,self.bundle)['initialized'])
        self.path.unlink()
        with self.assertRaises(Exception):self.store.health()
    def test_source_duration_and_duplicate_sample_cannot_confirm(self):
        self.assertEqual(self.apply(1,100)['active'],0)
        self.assertEqual(self.apply(1,100,110)['active'],0)
        self.assertEqual(self.apply(1,102)['active'],0)
        self.assertEqual(self.apply(1,104)['active'],1)
        self.assertEqual(self.apply(None,106)['active'],1)
        self.assertEqual(self.apply(0,108)['active'],0)
    def test_pending_restart_and_discontinuous_source_resets(self):
        self.apply(1,100);self.store=Store(self.path,'unit')
        self.assertEqual(self.apply(1,104)['active'],1)
        self.apply(0,106);self.apply(1,108)
        self.assertEqual(self.apply(1,130)['active'],0)
    def test_active_error_stale_and_late_normal_evidence_do_not_clear(self):
        self.apply(1,100);self.apply(1,104)
        self.assertEqual(self.apply(0,106,300)['active'],1)
        self.assertEqual(self.apply(None,302,error='timeout')['active'],1)
        self.assertEqual(self.apply(0,102,304)['active'],1)
    def test_source_failure_resets_pending(self):
        self.apply(1,100);self.apply(None,102,error='error')
        self.assertEqual(self.apply(1,104)['active'],0)
        self.assertEqual(self.apply(1,108)['active'],1)
    def test_direct_zero_valued_vector_is_active_then_empty_clears(self):
        rule=copy.deepcopy(next(r for r in self.bundle['rules'] if r['rule_id']=='os_sre.collector_down'));rule['for_seconds']=0
        cfg=config();cfg['rule_overrides'][rule['rule_id']]={'for_seconds':0};b=compile_bundle(cfg,ROOT)
        self.store.activate(b,1,'test','override direct confirmation')
        points=normalize(rule,[{'metric':{'job':'dcgm','instance':'node:9400'},'value':[100,'0']}],100)
        self.assertEqual(points[0]['value'],1)
        self.store.apply_cycle([{'rule_id':rule['rule_id'],'samples':points}],2,100)
        self.assertEqual(self.store.health(100)['active'],1)
        self.store.apply_cycle([{'rule_id':rule['rule_id'],'samples':[]}],2,102);self.assertEqual(self.store.health(102)['active'],0)
    def test_identity_isolation_and_unexpected_labels(self):
        r=next(r for r in self.bundle['rules'] if r['rule_id']=='os_sre.gpu_thermal')
        lab={**self.identity,'sre_result_kind':'value'}
        with self.assertRaises(SourceError):normalize(r,[{'metric':dict(lab,task_id='x'),'value':[100,'1']}],100)
        with self.assertRaises(SourceError):normalize(r,[{'metric':lab,'value':[100,'1']}],100)
        rows=[{'metric':lab,'value':[100,'1']},{'metric':{**self.identity,'sre_result_kind':'clock'},'value':[100,'99']}]
        self.assertEqual(normalize(r,rows,100)[0]['source_time'],99)
        with self.assertRaises(SourceError):normalize(r,rows+[rows[0]],100)
    def test_recovery_is_episode_bound_and_never_forces_clear(self):
        self.apply(1,100,rule='os_sre.xid_node');row=self.store.snapshot()['states'][0]
        action=self.store.administer('recovery',row['rule_id'],self.identity,row['revision'],'OS recovery review',now=101)
        self.assertFalse(action['forced_clear']);self.assertEqual(self.store.health(101)['active'],1)
        rule=next(r for r in self.bundle['rules'] if r['rule_id']==row['rule_id'])
        expanded=expand_recovery(rule,self.store.actions(row['rule_id'],102));self.assertNotIn('os_sre_recovery_verified',expanded)
        self.apply(0,104,rule=row['rule_id']);self.apply(1,106,rule=row['rule_id']);self.assertFalse(self.store.actions(row['rule_id'],107))
    def test_recovery_stale_revision_and_admin_retire(self):
        row=self.apply(1,100,rule='os_sre.xid_node')
        with self.assertRaises(Conflict):self.store.administer('recovery',row['rule_id'],self.identity,row['revision']-1,'test reason',now=101)
        self.store.administer('retire',row['rule_id'],self.identity,row['revision'],'device replaced',now=101)
        self.assertEqual(self.apply(1,104,rule=row['rule_id'])['active'],0)
        self.assertTrue(self.store.snapshot()['states'][0]['retired'])
    def test_release_cas_preserves_active_and_discards_old_cycle(self):
        self.apply(1,100);self.apply(1,104)
        b=copy.deepcopy(self.bundle);b['config']['limits']['poll_seconds']=15;b['sha256']=digest({k:v for k,v in b.items() if k!='sha256'})
        self.store.activate(b,1,'test','change polling policy')
        with self.assertRaises(Conflict):self.store.activate(self.bundle,1,'test','stale operator')
        with self.assertRaises(Conflict):self.store.apply_cycle([],1,106)
        self.assertEqual(self.store.health(104)['active'],1)
        self.store.activate(self.bundle,2,'test','rollback polling policy');self.assertEqual(self.store.health(104)['active'],1)
    def test_fresh_heartbeat_required_to_serve_vector(self):
        self.apply(1,100);self.apply(1,104)
        self.assertEqual(len(self.store.vector('os_sre.gpu_thermal',106)),1)
        with self.assertRaises(RuntimeError):self.store.vector('os_sre.gpu_thermal',1000)
    def test_backup_is_consistent_and_restorable(self):
        self.apply(1,100);self.apply(1,104)
        backup=Path(self.tmp.name)/'backup.sqlite';self.store.backup(backup)
        restored=Store(backup,'unit');self.assertEqual(restored.health(104)['active'],1)
    def test_inventory_inlined_and_no_business_labels(self):
        for r in self.bundle['rules']:
            self.assertNotIn('sre:inventory:',r['expression'] or '')
            self.assertNotRegex(r['expression'] or '',r'cluster_id|task_id|DEMO_')
    def test_json_bundle_tamper_is_rejected(self):
        from npumonitor_rules.bundle import validate_bundle
        b=copy.deepcopy(self.bundle);b['rules'][0]['severity']=3
        with self.assertRaises(ValueError):validate_bundle(b)

if __name__=='__main__':unittest.main()
