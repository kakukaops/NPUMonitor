import copy,json,tempfile,unittest
from pathlib import Path
from test_runtime import config,ROOT
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.store import Store,Conflict
from npumonitor_rules.nightingale import Sync,projection,OWNER

class FakeAPI:
    def __init__(self):self.rules=[];self.next_id=1;self.writes=0;self.fail_at=None
    def call(self,method,path,body=None):
        if path=='/datasource/list':return [{'id':1,'name':'NPUMonitor OS SRE unit','description':OWNER+':unit','http':{'url':'http://gateway:9480'},'auth':{'basic_auth':True}}]
        if method=='GET':return copy.deepcopy(self.rules)
        self.writes+=1
        if self.fail_at==self.writes:raise RuntimeError('injected API failure')
        if method=='POST':
            for r in body:self.rules.append(dict(copy.deepcopy(r),id=self.next_id));self.next_id+=1
        if method=='PUT':
            ident=int(path.rsplit('/',1)[-1]);self.rules=[dict(copy.deepcopy(body),id=ident) if r['id']==ident else r for r in self.rules]
        return None

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();c=config();c['nightingale']={'url':'http://nightingale','token_file':'/not-read','group_id':1,'notify_rule_id':1,'gateway_url':'http://gateway:9480'}
        self.config=c;self.bundle=compile_bundle(c,ROOT);path=Path(self.tmp.name)/'state.sqlite';Store.initialize(path,self.bundle);self.store=Store(path,'unit');self.api=FakeAPI()
    def tearDown(self):self.tmp.cleanup()
    def test_sync_twice_has_no_duplicates_or_second_writes(self):
        sync=Sync(self.store,self.api);result=sync.apply();self.assertEqual(result['rules'],47);writes=self.api.writes
        result=sync.apply();self.assertEqual(result['changed'],0);self.assertEqual(self.api.writes,writes);self.assertEqual(len(self.api.rules),47)
    def test_external_edit_prevents_all_changes(self):
        sync=Sync(self.store,self.api);sync.apply();self.api.rules[0]['disabled']=1;writes=self.api.writes
        with self.assertRaises(Conflict):sync.apply()
        self.assertEqual(self.api.writes,writes)
    def test_apply_failure_compensates_completed_writes(self):
        sync=Sync(self.store,self.api);sync.apply();original=[projection(r) for r in self.api.rules]
        c=copy.deepcopy(self.config);c['rule_overrides']['os_sre.gpu_thermal']['severity']=1
        c['rule_overrides']['os_sre.memory_thermal']={'severity':1};b=compile_bundle(c,ROOT);self.store.activate(b,1,'test','severity review')
        self.api.fail_at=self.api.writes+2
        with self.assertRaises(RuntimeError):Sync(self.store,self.api).apply()
        self.assertEqual([projection(r) for r in self.api.rules],original)
    def test_rollback_rejects_subsequent_external_edit(self):
        sync=Sync(self.store,self.api);operation=sync.apply()['operation'];self.api.rules[1]['note']='operator local edit'
        with self.assertRaises(Conflict):sync.rollback(operation)
    def test_runtime_bundle_activation_is_optimistic(self):
        b=compile_bundle(self.config,ROOT);self.assertEqual(self.store.plan(b)['changed'],[])
        with self.assertRaises(Conflict):self.store.activate(b,99,'test','stale activation')

    def interrupted_create(self):
        sync=Sync(self.store,self.api);desired=sync.desired(1)[0];rid=desired['annotations']['sre_rule_id'];desired['annotations']['sync_operation']='interrupted'
        op={'id':'interrupted','status':'applying','generation':1,'before':{rid:None},'after':{},'desired':{rid:copy.deepcopy(desired)},'pending':rid}
        self.store.put_operation('interrupted',op);self.api.call('POST','/busi-group/1/alert-rules',[desired]);return sync
    def test_recover_uncertain_create_after_process_crash(self):
        sync=self.interrupted_create();result=sync.recover('interrupted')
        self.assertEqual(result['status'],'compensated');self.assertEqual(self.api.rules[0]['disabled'],1)
        self.assertIsNone(self.store.get_operation('interrupted')['pending'])
    def test_recover_uncertain_write_refuses_external_drift(self):
        sync=self.interrupted_create();self.api.rules[0]['note']='external edit';writes=self.api.writes
        with self.assertRaises(Conflict):sync.recover('interrupted')
        self.assertEqual(self.api.writes,writes)

    def test_exact_catalog_projection_can_use_independent_watchdog(self):
        c=copy.deepcopy(self.config);c['nightingale']['include_gateway_health_rule']=False
        b=compile_bundle(c,ROOT);self.store.activate(b,1,'test','independent watchdog covers runtime health')
        sync=Sync(self.store,self.api);result=sync.apply()
        self.assertEqual(result['rules'],46)
        self.assertEqual({r['annotations']['sre_rule_id'] for r in self.api.rules},{r['rule_id'] for r in b['rules']})
