import time,unittest
from test_runtime import config,ROOT
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.source import Source

class ContractTests(unittest.TestCase):
    def source(self,aliases=None):
        cfg=config();cfg['upstream']['metric_aliases']=aliases or {};source=Source(compile_bundle(cfg,ROOT));now=time.time()
        def row(name,uuid,value='55',**labels):return {'metric':{'__name__':name,'job':'dcgm-unit','instance':'host:9400','UUID':uuid,**labels},'value':[now,value]}
        source.rows=[row('DCGM_FI_DEV_GPU_TEMP','GPU-0'),row('DCGM_FI_DEV_GPU_MAX_OP_TEMP','GPU-0','95'),row('DCGM_FI_DEV_GPU_TEMP','GPU-1'),{'metric':{'__name__':'up','job':'dcgm-unit','instance':'host:9400'},'value':[now,'1']}]
        source.metadata={name:[{'type':'gauge'}] for name in ('DCGM_FI_DEV_GPU_TEMP','DCGM_FI_DEV_GPU_MAX_OP_TEMP')}
        source.query=lambda *args:source.rows;source.request=lambda *args:source.metadata
        return source
    def test_partial_card_coverage_does_not_imply_all_cards_supported(self):
        result=self.source().preflight()['rules']['os_sre.gpu_thermal'];self.assertEqual(result['status'],'ready')
        coverage={r['identity']['UUID']:r for r in result['entity_coverage']}
        self.assertTrue(coverage['GPU-0']['complete']);self.assertFalse(coverage['GPU-1']['complete'])
        self.assertIn('DCGM_FI_DEV_GPU_MAX_OP_TEMP',coverage['GPU-1']['missing_fields'])
    def test_wrong_type_is_not_ready(self):
        source=self.source();source.metadata['DCGM_FI_DEV_GPU_TEMP']=[{'type':'counter'}]
        self.assertEqual(source.preflight()['rules']['os_sre.gpu_thermal']['status'],'missing_or_incompatible_input')
    def test_mig_excluded_and_duplicates_exposed(self):
        source=self.source();source.rows.append({**source.rows[0],'metric':dict(source.rows[0]['metric'],GPU_I_ID='1')})
        result=source.preflight();self.assertFalse(any(r['duplicate_fields'] for r in result['rules']['os_sre.gpu_thermal']['entity_coverage']))
        source.rows.append(source.rows[0]);result=source.preflight()
        self.assertIn('DCGM_FI_DEV_GPU_TEMP',result['rules']['os_sre.gpu_thermal']['entity_coverage'][0]['duplicate_fields'])
    def test_alias_preserves_logical_contract(self):
        source=self.source({'DCGM_FI_DEV_GPU_TEMP':'vendor_gpu_temp'})
        for row in source.rows:
            if row['metric']['__name__']=='DCGM_FI_DEV_GPU_TEMP':row['metric']['__name__']='vendor_gpu_temp'
        source.metadata['vendor_gpu_temp']=source.metadata.pop('DCGM_FI_DEV_GPU_TEMP')
        result=source.preflight();self.assertEqual(result['fields']['vendor_gpu_temp']['logical_name'],'DCGM_FI_DEV_GPU_TEMP')
        self.assertEqual(result['rules']['os_sre.gpu_thermal']['status'],'ready')

    def test_asset_dependent_rule_exposes_unconfigured_device(self):
        source=self.source();source.rows.append({'metric':{'__name__':'DCGM_FI_DEV_FABRIC_MANAGER_STATUS','job':'dcgm-unit','instance':'host:9400','UUID':'GPU-0'},'value':[time.time(),'3']})
        source.metadata['DCGM_FI_DEV_FABRIC_MANAGER_STATUS']=[{'type':'gauge'}]
        coverage=source.preflight()['rules']['os_sre.fabric_manager']['entity_coverage']
        self.assertTrue(coverage[0]['asset_configuration_missing']);self.assertFalse(coverage[0]['complete'])
