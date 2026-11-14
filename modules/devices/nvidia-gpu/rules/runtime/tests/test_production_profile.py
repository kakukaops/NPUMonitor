import copy,importlib.util,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_runtime import ROOT,config
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.production_profile import definition
from npumonitor_rules.source import Source

class ProductionContractTests(unittest.TestCase):
    def cfg(self,confirmed=True):
        d=definition();c=config();c['contract_profile']='h100-dcgm-master-v1'
        c['source_contract']={'confirmed':confirmed,'capabilities':list(d['metric_ids']),'nvlink_policy':'active-only-r595-v1','stack':{'gpu_model':'NVIDIA H100 SXM 80GB','driver_version':'595.synthetic','dcgm_version':'synthetic-master-v1','exporter_version':'master-sim1','nvml_version':'synthetic-R595','form_factor':'SXM','mig_enabled':False},'units':{mid:d['metric_contracts'][name]['unit'] for mid,name in d['metric_ids'].items()},'metadata':{'metric':'sre_sim_gpu_info','labels':{}}}
        return c
    def source(self,c=None):
        c=c or self.cfg();b=compile_bundle(c,ROOT);source=Source(b)
        # A fixed synthetic source proves contract handling, not physical hardware support.
        with tempfile.TemporaryDirectory() as tmp:
            cat=Path(tmp)/'catalog.json';cat.write_text((ROOT/'runtime/master/catalog.json').read_text())
            with patch.dict(os.environ,{'FIXTURE_DATA':tmp,'FIXTURE_CATALOG_FILE':str(cat)}):
                spec=importlib.util.spec_from_file_location('prod_fixture',ROOT/'runtime/reference/fixture.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            text=mod.metrics(copy.deepcopy(mod.DEFAULTS))
        rows=[];now=time.time()
        import re
        for line in text.splitlines():
            if not (line.startswith('DCGM_') or line.startswith('sre_sim_gpu_info{')):continue
            prefix,value=line.rsplit(' ',1);name,labels=prefix.split('{',1);lab=dict(re.findall(r'(\w+)="([^"]*)"',labels))
            rows.append({'metric':dict(lab,__name__=name,job='dcgm-os-sre',instance='node:9400'),'value':[now,value]})
        rows.append({'metric':{'__name__':'up','job':'dcgm-os-sre','instance':'node:9400'},'value':[now,'1']})
        source.rows=rows;source.metadata={n:[{'type':'counter' if v['kind']=='counter' else 'gauge'}] for n,v in b['metric_contracts'].items() if n.startswith('DCGM_')}
        def query(expr,*args):
            if expr.startswith('timestamp('):return [{'metric':dict({k:v for k,v in r['metric'].items() if k!='__name__'},sre_source_field=r['metric']['__name__']),'value':[now,r['value'][0]]} for r in source.rows if r['metric']['__name__']!='up']
            return source.rows
        source.query=query;source.request=lambda *args:source.metadata
        return source
    def test_production_has_88_fields_58_rules_without_simulator_dependency(self):
        b=compile_bundle(self.cfg(),ROOT);self.assertEqual(len(b['rules']),58)
        self.assertEqual(sum(n.startswith('DCGM_') for n in b['metric_contracts']),88)
        text=json.dumps(b['production_contract']['definition'])
        for forbidden in ['defaults','scenarios','master_simulation','simulation_policy_version']:self.assertNotIn('"'+forbidden+'"',text)
        self.assertTrue(b['production_contract']['declaration']['ready'])
        self.assertEqual(next(r for r in b['rules'] if r['rule_id']=='os_sre.gpu_link_down')['note'].split(':')[0],'Declared R595 observation policy')
    def test_mixed_profiles_wrong_units_and_alias_collision_rejected(self):
        c=self.cfg();c['master_profile']='h100-master-simulation-v1'
        with self.assertRaises(ValueError):compile_bundle(c,ROOT)
        c=self.cfg();c['source_contract']['units']['nvidia.board_power']='mW'
        with self.assertRaises(ValueError):compile_bundle(c,ROOT)
        c=self.cfg();c['upstream']['metric_aliases']={'DCGM_FI_DEV_GPU_TEMP':'DCGM_FI_DEV_MEMORY_TEMP'}
        with self.assertRaises(ValueError):compile_bundle(c,ROOT)
    def test_unconfirmed_stack_units_and_unknown_capability_fail_closed(self):
        s=self.source(self.cfg(False));p=s.preflight();self.assertFalse(p['production_contract']['ready'])
        self.assertEqual(p['rules']['os_sre.gpu_thermal']['status'],'source_contract_not_ready')
        c=self.cfg();c['source_contract']['capabilities'].append('nvidia.switch_link_fatal')
        with self.assertRaises(ValueError):compile_bundle(c,ROOT)
        c=self.cfg();del c['source_contract']['units']['nvidia.gpu_temp']
        self.assertFalse(compile_bundle(c,ROOT)['production_contract']['declaration']['ready'])
    def test_live_metadata_and_per_gpu_coverage(self):
        s=self.source();p=s.preflight();self.assertTrue(p['production_contract']['ready'])
        self.assertEqual(len(p['production_contract']['capabilities']),103)
        # Missing/duplicate metadata for a single card blocks source admission.
        s.rows=[r for r in s.rows if not (r['metric']['__name__']=='sre_sim_gpu_info' and r['metric']['UUID']=='GPU-CONTRACT-0001')]
        p=s.preflight();self.assertFalse(p['production_contract']['ready'])
        self.assertIn('nvidia.gpu_uuid',p['production_contract']['mandatory_input_gaps'])
    def test_optional_fields_not_selected_do_not_create_missing_input_alerts(self):
        c=self.cfg();c['source_contract']['capabilities']=[];b=compile_bundle(c,ROOT)
        r=next(r for r in b['rules'] if r['rule_id']=='os_sre.memory_unrepairable');self.assertFalse(r['enabled'])
        self.assertEqual(r['capability_status'],'not_selected')
        r=next(r for r in b['rules'] if r['rule_id']=='os_sre.master_field_missing')
        self.assertNotIn('DCGM_FI_DEV_MEMORY_UNREPAIRABLE',r['expression'])
    def test_version_mismatch_unknown_nvlink_and_fractional_seconds(self):
        s=self.source()
        for r in s.rows:
            if r['metric']['__name__']=='sre_sim_gpu_info':r['metric']['driver_version']='620.1'
        self.assertFalse(s.preflight()['production_contract']['ready'])
        s=self.source()
        for r in s.rows:
            if r['metric']['__name__']=='DCGM_FI_DEV_NVLINK_GET_STATE':r['value'][1]='3'
            if r['metric']['__name__']=='DCGM_FI_DEV_GPU_POWER_THROTTLE_SECONDS_TOTAL':r['value'][1]='0.125'
        p=s.preflight();caps={r['metric_id']:r['status'] for r in p['production_contract']['capabilities']}
        self.assertEqual(caps['nvidia.nvlink_link_state'],'missing_duplicate_or_invalid_per_device')
        self.assertEqual(caps['nvidia.power_throttle_seconds'],'ready')

    def test_original_timestamps_and_new_asset_required_fields(self):
        s=self.source()
        for row in s.rows:
            if row['metric']['__name__']=='DCGM_FI_DEV_GPU_UTIL':row['value'][0]-=1000
        self.assertIn('nvidia.gpu_util',s.preflight()['production_contract']['mandatory_input_gaps'])
        c=self.cfg();c['profile']['gpus']=[{'job':'dcgm-unit','instance':'host:9400','UUID':'GPU-X','required_fields':['DCGM_FI_DEV_FB_USED']}]
        b=compile_bundle(c,ROOT);self.assertEqual(len(b['rules']),58)
