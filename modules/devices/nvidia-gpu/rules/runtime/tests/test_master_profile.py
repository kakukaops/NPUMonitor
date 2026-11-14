import copy,importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_runtime import ROOT,config
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.master_profile import definition,extend_catalog

class MasterProfileTests(unittest.TestCase):
    def setUp(self):
        self.master=definition();self.cfg=config();self.cfg['master_profile']='h100-master-simulation-v1';self.bundle=compile_bundle(self.cfg,ROOT)
    def test_complete_disposition_and_no_fake_unknown_values(self):
        self.assertEqual(len(self.master['coverage']),103)
        self.assertEqual(len(self.master['metric_contracts']),88)
        self.assertEqual(len(self.bundle['rules']),58)
        unknown=[x for x in self.master['coverage'] if x['mode']=='unsupported_semantics'];self.assertEqual(len(unknown),2)
        for x in unknown:self.assertFalse(set(x['names_and_aliases'])&set(self.master['metric_contracts']))
    def test_no_resource_utilization_or_capacity_fault_heuristics(self):
        added=[r for r in self.bundle['rules'] if r['rule_id'] not in {r['rule_id'] for r in compile_bundle(config(),ROOT)['rules']}]
        forbidden=['DCGM_FI_DEV_GPU_UTIL','DCGM_FI_DEV_FB_USED','DCGM_FI_DEV_MEM_COPY_UTIL','DCGM_FI_PROF_PIPE_TENSOR_ACTIVE']
        for rule in added:
            if rule['kind']=='stateful':self.assertFalse(any(n in rule['expression'] for n in forbidden))
        link=next(r for r in self.bundle['rules'] if r['rule_id']=='os_sre.gpu_link_down');self.assertIn('ACTIVE=1 only',link['note']);self.assertIn('== 1) * 0',link['expression'])
    def test_fixture_has_resource_info_and_consistent_framebuffer_ratio(self):
        catalog=json.loads((ROOT/'runtime/master/catalog.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'catalog.json';p.write_text(json.dumps(catalog))
            with patch.dict(os.environ,{'FIXTURE_DATA':tmp,'FIXTURE_CATALOG_FILE':str(p)}):
                spec=importlib.util.spec_from_file_location('master_fixture',ROOT/'runtime/reference/fixture.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            state=copy.deepcopy(mod.DEFAULTS);state['scenario']='memory_capacity_high';text=mod.metrics(state)
            self.assertIn('DCGM_FI_DEV_GPU_UTIL{',text);self.assertIn('sre_sim_gpu_info{',text);self.assertIn('unsupported_semantics',text)
            ratio=self.master['metric_ids']['nvidia.fb_used_ratio'];line=next(l for l in text.splitlines() if l.startswith(ratio+'{') and '0000' in l)
            self.assertAlmostEqual(float(line.rsplit(' ',1)[1]),77000/(81920-1093))
            self.assertNotIn('DCGM_FI_DEV_NVSWITCH_LINK_FATAL_ERRORS{',text)
            def sample(body,mid,index=0):
                name=self.master['metric_ids'][mid]
                return float(next(l for l in body.splitlines() if l.startswith(name+'{') and 'UUID="GPU-CONTRACT-'+str(index).zfill(4)+'"' in l).rsplit(' ',1)[1])
            self.assertNotEqual(sample(text,'nvidia.fb_used',1),77000)
            state=copy.deepcopy(mod.DEFAULTS)
            with patch.object(mod.time,'time',return_value=1000):a=mod.metrics(state)
            with patch.object(mod.time,'time',return_value=1015):b=mod.metrics(state)
            for mid in ['nvidia.gpu_util','nvidia.fb_used','nvidia.gpu_temp','nvidia.board_power','nvidia.pcie_tx_rate','nvidia.nvlink_tx_rate']:
                self.assertNotEqual(sample(a,mid),sample(b,mid),mid)
            self.assertNotEqual(sample(a,'nvidia.gpu_util'),sample(a,'nvidia.gpu_util',1))
            for body in [a,b]:
                for index in [0,1]:
                    used=sample(body,'nvidia.fb_used',index);free=sample(body,'nvidia.fb_free',index)
                    self.assertEqual(used+free,80827)
                    self.assertAlmostEqual(sample(body,'nvidia.fb_used_ratio',index),used/80827)
                    self.assertAlmostEqual(sample(body,'nvidia.gpu_temp_margin',index),90-sample(body,'nvidia.gpu_temp',index))
                self.assertEqual(sample(body,'nvidia.xid_last'),0)
                self.assertEqual(sample(body,'nvidia.fb_total'),81920)
            self.assertGreater(sample(b,'nvidia.energy'),sample(a,'nvidia.energy'))

    def test_every_master_metric_has_explicit_simulation_semantics(self):
        for item in self.master['coverage']:
            self.assertIn('behavior',item['simulation'],item['metric_id'])
            if item['mode']=='numeric_simulation':
                self.assertIn(item['wire_name'],self.master['defaults'])
                self.assertIn('unit',item['simulation'])
        catalog=json.loads((ROOT/'runtime/master/catalog.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'catalog.json';p.write_text(json.dumps(catalog))
            with patch.dict(os.environ,{'FIXTURE_DATA':tmp,'FIXTURE_CATALOG_FILE':str(p)}):
                spec=importlib.util.spec_from_file_location('policy_fixture',ROOT/'runtime/reference/fixture.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            state=copy.deepcopy(mod.DEFAULTS)
            for now in [1000,1005,1075,1300]:
                with patch.object(mod.time,'time',return_value=now):text=mod.metrics(state)
                for name,contract in self.master['metric_contracts'].items():
                    samples=[float(l.rsplit(' ',1)[1]) for l in text.splitlines() if l.startswith(name+'{')]
                    self.assertTrue(samples,name)
                    for value in samples:
                        self.assertGreaterEqual(value,contract['minimum'],name)
                        self.assertLessEqual(value,contract['maximum'],name)
            counter=self.master['metric_ids']['nvidia.power_throttle_seconds']
            state['counter_activity']=[{'metric':counter,'identity':{'UUID':'GPU-CONTRACT-0000'},'rate_per_second':.125}]
            def value(text,index=0):
                return float(next(l for l in text.splitlines() if l.startswith(counter+'{UUID="GPU-CONTRACT-'+str(index).zfill(4)+'"} ')).rsplit(' ',1)[1])
            with patch.object(mod.time,'time',return_value=1400):a=mod.metrics(state)
            with patch.object(mod.time,'time',return_value=1402):b=mod.metrics(state)
            with patch.object(mod.time,'time',return_value=1402):c=mod.metrics(state)
            self.assertAlmostEqual(value(b)-value(a),.25)
            self.assertEqual(value(b),value(c))
            self.assertEqual(value(b,1),0)

    def test_event_showcase_is_timed_repeatable_and_device_scoped(self):
        catalog=json.loads((ROOT/'runtime/master/catalog.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'catalog.json';p.write_text(json.dumps(catalog))
            with patch.dict(os.environ,{'FIXTURE_DATA':tmp,'FIXTURE_CATALOG_FILE':str(p)}):
                spec=importlib.util.spec_from_file_location('showcase_fixture',ROOT/'runtime/reference/fixture.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            state=copy.deepcopy(mod.DEFAULTS);state.update(scenario='event_showcase',showcase_started=1000)
            def sample(mid,index=0):
                name=self.master['metric_ids'][mid]
                return float(next(l for l in text.splitlines() if l.startswith(name+'{') and 'UUID="GPU-CONTRACT-'+str(index).zfill(4)+'"' in l).rsplit(' ',1)[1])
            for elapsed in [29,30,120,180,270,390,510,630]:
                with patch.object(mod.time,'time',return_value=1000+elapsed):text=mod.metrics(state)
                self.assertEqual(sample('nvidia.xid_last'),0 if elapsed<30 else 79)
                self.assertEqual(sample('nvidia.xid_last',1),0)
                self.assertEqual(sample('nvidia.nvlink_link_state'),0 if elapsed==510 else 1)
                if elapsed==120:self.assertEqual(sample('nvidia.nvlink_crc'),6)
                if elapsed==180:self.assertEqual(sample('nvidia.ecc_dbe_volatile_total'),1)
                if elapsed==270:self.assertEqual(sample('nvidia.power_throttle_seconds'),30)
                if elapsed==390:self.assertEqual(sample('nvidia.gpu_temp'),92)
                state=json.loads(json.dumps(state)) # persisted restart must not replay events
                with patch.object(mod.time,'time',return_value=1000+elapsed):repeated=mod.metrics(state)
                self.assertEqual(text,repeated)
            self.assertEqual(len(state['events']),3)
            self.assertEqual(len({e['cursor'] for e in state['events']}),3)
            state['scenario']='baseline'
            with patch.object(mod.time,'time',return_value=1640):text=mod.metrics(state)
            self.assertEqual(sample('nvidia.nvlink_crc'),12)
