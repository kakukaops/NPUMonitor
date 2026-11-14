#!/usr/bin/env python3
"""SRE policy validation plus regression inputs containing no business context."""
import argparse
import copy
import json
from pathlib import Path
import sys
import unittest
import yaml
from build_os_sre import compile_profile,outputs,ROOT,OUT,GPU,SWITCH,GPU_LINK,SWITCH_LINK

sys.path.insert(0,str(ROOT/'lab'))
from comprehensive_model import SCALAR_FAULTS,COUNTER_FAULTS


def profile():
    p=yaml.safe_load((OUT/'profile.yaml').read_text())
    p['gpus']=[{'job':'dcgm','instance':'node-a:9400','UUID':'GPU-A','required_fields':['DCGM_FI_DEV_GPU_TEMP','DCGM_FI_DEV_MEMORY_TEMP'],
                'pcie_gen':5,'pcie_width':16,'pcie_active_bytes_per_second':1000000,'fabric_expected':True}]
    p['switches']=[{'job':'dcgm','instance':'node-a:9400','switch_id':'SW-A'}]
    p['links']=[{'job':'dcgm','instance':'node-a:9400','UUID':'GPU-A','link_id':'0'},
                {'job':'dcgm','instance':'node-a:9400','switch_id':'SW-A','link_id':'0'}]
    p['monitor_targets']=[{'job':'nightingale-self','instance':'n9e:17000','evaluation_expected':True}]
    return p


def fixtures():
    c=compile_profile(profile());rules={r['rule_id'].split('.',1)[1]:r for r in c['rules']}
    contracts=c['metric_contracts']
    normal={'DCGM_FI_DEV_GPU_TEMP':55,'DCGM_FI_DEV_GPU_MAX_OP_TEMP':95,'DCGM_FI_DEV_MEMORY_TEMP':60,
        'DCGM_FI_DEV_MEM_MAX_OP_TEMP':110,'DCGM_FI_DEV_PCIE_LINK_GEN':5,'DCGM_FI_DEV_PCIE_LINK_WIDTH':16,
        'DCGM_FI_DEV_NVLINK_GET_STATE':1,'DCGM_FI_DEV_FABRIC_MANAGER_STATUS':3,'DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY':1,
        'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT':50,'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_LIMIT_SLOWDOWN':95,
        'DCGM_FI_DEV_NVSWITCH_LINK_STATUS':2,'os_sre_recovery_verified':1}
    def labels(name,extra=None):
        dims=contracts[name]['identity_labels'];mapping={'job':'dcgm','instance':'node-a:9400','UUID':'GPU-A','switch_id':'SW-A','link_id':'0'}
        value={k:mapping[k] for k in dims};value.update(extra or {});return value
    def series(name,lab):return name+'{'+','.join(k+'='+json.dumps(str(v)) for k,v in sorted(lab.items()))+'}'
    def samples(name,lab=None,value=None):return {'series':series(name,labels(name) if lab is None else lab),'values':str(normal.get(name,0) if value is None else value)+'+0x30'}
    def base():
        rows=[{'series':'up{job="dcgm",instance="node-a:9400"}','values':'1+0x30'},
              {'series':'up{job="nightingale-self",instance="n9e:17000"}','values':'1+0x30'}]
        for name in contracts:
            rows.append(samples(name))
        # Recovery evidence for a switch has a distinct stable identity.
        rows.append(samples('os_sre_recovery_verified',{'job':'dcgm','instance':'node-a:9400','switch_id':'SW-A'}))
        for name,value in [('gpu_expected',1),('switch_expected',1),('pcie_gen',5),('pcie_width',16),('pcie_active_bps',1000000),('fabric_expected',1),('gpu_link_expected',1),('switch_link_expected',1)]:
            dims=SWITCH_LINK if name=='switch_link_expected' else GPU_LINK if name=='gpu_link_expected' else SWITCH if name=='switch_expected' else GPU
            mapping={'job':'dcgm','instance':'node-a:9400','UUID':'GPU-A','switch_id':'SW-A','link_id':'0'}
            rows.append({'series':series('sre:inventory:'+name,{k:mapping[k] for k in dims}),'values':str(value)+'+0x30'})
        for name in ('DCGM_FI_DEV_GPU_TEMP','DCGM_FI_DEV_MEMORY_TEMP'):
            rows.append({'series':series('sre:inventory:input_expected',dict(labels(name),metric_name=name)),'values':'1+0x30'})
        return rows
    def replace(rows,name,value):
        key=series(name,labels(name))
        for row in rows:
            if row['series']==key:row['values']=value if isinstance(value,str) else str(value)+'+0x30';return
        raise ValueError(name)
    def check(key,count=0,when='5m',positive=True):
        expr=rules[key]['expression'];assert expr
        if rules[key]['kind']=='direct':positive=False
        return {'expr':f'count((({expr}))'+(' > 0' if positive else '')+') or vector(0)',
                'eval_time':when,'exp_samples':[{'labels':'{}','value':count}]}
    cases=[{'name':'all_hardware_without_business_labels','interval':'30s','input_series':base(),
            'promql_expr_test':[check(k) for k in rules if rules[k]['expression'] and k not in ('platform_notify_failure',)]}]
    for key in [k for k,r in rules.items() if r['kind']=='stateful']:
        rows=base();old=rules[key]['previous_rule_id'].split('.',1)[1]
        scene=next(r for r in json.loads((ROOT/'rules/comprehensive-catalog.json').read_text())['rules'] if r['rule_id']=='training.'+old)['scenario']
        if scene in SCALAR_FAULTS:
            name,value=SCALAR_FAULTS[scene]
            if name.startswith('DEMO_'):continue
            replace(rows,name,value)
        elif scene in COUNTER_FAULTS:
            name=COUNTER_FAULTS[scene];replace(rows,name,'0+1x30')
        else:raise ValueError(scene)
        if key=='pcie_degraded':replace(rows,'DCGM_FI_PROF_PCIE_TX_BYTES',2000000)
        cases.append({'name':'fault_'+key,'interval':'30s','input_series':rows,'promql_expr_test':[check(key,1)]})
    rows=base()
    for row in rows:
        if row['series'].startswith('DCGM_') or row['series'].startswith('os_sre_'):
            row['series']=row['series'][:-1]+',cluster_id="ignored",task_id="ignored",tenant="ignored"}'
    replace_key=next(row for row in rows if row['series'].startswith('DCGM_FI_DEV_GPU_TEMP{'));replace_key['values']='100+0x30'
    expected_labels='{job="dcgm",instance="node-a:9400",UUID="GPU-A"}'
    cases.append({'name':'extra_business_labels_are_not_propagated','interval':'30s','input_series':rows,
        'promql_expr_test':[{'expr':rules['gpu_thermal']['expression'],'eval_time':'5m','exp_samples':[{'labels':expected_labels,'value':1}]}]})
    rows=base();replace(rows,'DCGM_FI_DEV_GPU_TEMP',100)
    rows.append(samples('DCGM_FI_DEV_GPU_TEMP',labels('DCGM_FI_DEV_GPU_TEMP',{'pod':'duplicate'}),100))
    cases.append({'name':'duplicate_identity_rejected','interval':'30s','input_series':rows,
        'promql_expr_test':[check('gpu_thermal'),check('input_duplicate',1)]})
    for value in ('NaN','+Inf','-Inf','9223372036854775792'):
        rows=base();replace(rows,'DCGM_FI_DEV_GPU_TEMP',value+'+0x30' if value[0].isdigit() else ' '.join([value]*31))
        cases.append({'name':'invalid_temperature_'+value,'interval':'30s','input_series':rows,
            'promql_expr_test':[check('gpu_thermal'),check('input_invalid',1)]})
    rows=base();rows[0]['values']='0+0x30';replace(rows,'DCGM_FI_DEV_GPU_TEMP',100)
    cases.append({'name':'scrape_failure_never_clears_hardware','interval':'30s','input_series':rows,
        'promql_expr_test':[check('gpu_thermal',0,positive=False),check('collector_down',1)]})
    rows=base();rows=[row for row in rows if not row['series'].startswith('DCGM_FI_DEV_GPU_TEMP{')]
    cases.append({'name':'partial_input_missing','interval':'30s','input_series':rows,
        'promql_expr_test':[check('gpu_thermal',0,positive=False),check('field_missing',1)]})
    rows=[row for row in base() if not row['series'].startswith(('DCGM_','os_sre_'))]
    cases.append({'name':'whole_device_missing_suppresses_field_fanout','interval':'30s','input_series':rows,
        'promql_expr_test':[check('entity_missing',2),check('field_missing')]})
    rows=base();replace(rows,'DCGM_FI_DEV_GPU_TEMP',100)
    # A second exporter with the same UUID must not supply a limit to node-a.
    rows=[row for row in rows if not row['series'].startswith('DCGM_FI_DEV_GPU_MAX_OP_TEMP{')]
    rows.append(samples('DCGM_FI_DEV_GPU_MAX_OP_TEMP',labels('DCGM_FI_DEV_GPU_MAX_OP_TEMP',{'instance':'node-b:9400'}),95))
    rows.append({'series':'up{job="dcgm",instance="node-b:9400"}','values':'1+0x30'})
    cases.append({'name':'same_uuid_different_target_cannot_cross_join','interval':'30s','input_series':rows,
        'promql_expr_test':[check('gpu_thermal',0,positive=False)]})
    rows=base();replace(rows,'DCGM_FI_DEV_PCIE_LINK_GEN',1)
    cases.append({'name':'idle_pcie_downshift_is_unknown_not_degraded_or_clear','interval':'30s','input_series':rows,
        'promql_expr_test':[check('pcie_degraded',0,positive=False)]})
    rows=[row for row in base() if not row['series'].startswith('sre:inventory:')]
    replace(rows,'DCGM_FI_DEV_NVLINK_GET_STATE',0)
    cases.append({'name':'no_inventory_does_not_guess_port_expectations','interval':'30s','input_series':rows,
        'promql_expr_test':[check('gpu_link_down',0,positive=False),check('entity_missing'),check('field_missing')]})
    rows=base();replace(rows,'DCGM_FI_DEV_GPU_TEMP','100 100 _ _ _ _ _ _ _ _ _')
    cases.append({'name':'stale_source_timestamp_never_supplies_clear','interval':'30s','input_series':rows,
        'promql_expr_test':[check('gpu_thermal',0,positive=False),check('input_stale',1)]})
    rows=base();replace(rows,'DCGM_FI_DEV_FABRIC_MANAGER_STATUS',0)
    cases.append({'name':'unsupported_fabric_never_clears_failure','interval':'30s','input_series':rows,
        'promql_expr_test':[check('fabric_manager',0,positive=False),check('fabric_capability',1)]})
    rows=base();rows=[row for row in rows if not row['series'].startswith('os_sre_recovery_verified{')]
    cases.append({'name':'no_recovery_evidence_never_auto_clears_xid','interval':'30s','input_series':rows,
        'promql_expr_test':[check('xid_node',0,positive=False),check('sxid_fatal',0,positive=False)]})
    rows=base();rows.append({'series':'DCGM_FI_DEV_NVLINK_GET_STATE{job="dcgm",instance="node-b:9400"}','values':'0+0x30'})
    rows.append({'series':'up{job="dcgm",instance="node-b:9400"}','values':'1+0x30'})
    cases.append({'name':'both_port_identity_components_missing','interval':'30s','input_series':rows,
        'promql_expr_test':[check('identity_missing',1)]})
    # Native Nightingale error counters carry arbitrary evaluator IDs; no ID is configured.
    rows=base();rows.append({'series':'n9e_alert_query_data_error_total{job="nightingale-self",instance="n9e:17000",rule_id="987654"}','values':'0+1x30'})
    cases.append({'name':'platform_query_errors_without_known_rule_ids','interval':'30s','input_series':rows,
        'promql_expr_test':[check('platform_query_failure',1)]})
    cases.append({'name':'all_diagnostic_views_without_business_labels','interval':'30s','input_series':base(),
        'promql_expr_test':[{'expr':'count(('+v['expression']+')) or vector(0)','eval_time':'5m',
            'exp_samples':[{'labels':'{}','value':0 if v['query_id'].startswith('xid.') else 1}]} for v in c['views']]})
    return {'rule_files':[],'evaluation_interval':'30s','tests':cases}


class ProfileTests(unittest.TestCase):
    def test_all_old_rules_have_explicit_disposition(self):
        c=compile_profile(profile());old=json.loads((ROOT/'rules/comprehensive-catalog.json').read_text())['rules']
        old_ids={r['rule_id'] for r in old}|{r['key'] for r in json.loads((ROOT/'rules/comprehensive-health.json').read_text())}
        self.assertTrue(old_ids<={r['previous_rule_id'] for r in c['rules']});self.assertEqual(len(c['rules']),46)
    def test_no_business_context_in_promql_or_metric_contract(self):
        c=compile_profile(profile())
        for r in c['rules']:
            self.assertNotRegex(r['expression'] or '',r'cluster_id|task_id|job_id|entity_id|DEMO_|rule_id=|pod=|tenant=')
        self.assertTrue(all(not v['business_labels_required'] for v in c['metric_contracts'].values()))
    def test_reject_business_config_and_duplicate_inventory(self):
        p=profile();p['gpus'][0]['task_id']='unavailable'
        with self.assertRaises(ValueError):compile_profile(p)
        p=profile();p['gpus'].append(copy.deepcopy(p['gpus'][0]))
        with self.assertRaises(ValueError):compile_profile(p)
    def test_wrong_collector_job_and_invalid_policy_rejected(self):
        p=profile();p['gpus'][0]['job']='application-job'
        with self.assertRaises(ValueError):compile_profile(p)
        for value in (0,-1,float('nan'),True):
            p=profile();p['gpus'][0]['pcie_active_bytes_per_second']=value
            with self.assertRaises(ValueError):compile_profile(p)
    def test_static_inventory_is_optional_not_invented(self):
        p=yaml.safe_load((OUT/'profile.yaml').read_text());self.assertFalse(compile_profile(p)['inventory_records'])
    def test_notification_gap_is_not_fake_failure_metric(self):
        r=next(r for r in compile_profile(profile())['rules'] if r['previous_rule_id']=='platform_notify_failure')
        self.assertIsNone(r['expression']);self.assertEqual(r['status'],'blocked_missing_input')
    def test_zero_observations_not_exported_as_truthiness_alerts(self):
        o=outputs(compile_profile(profile()));native=yaml.safe_load(o['native-alerts.prom.yaml'])
        self.assertTrue(all('sre:hardware:observation' not in r['expr'] for r in native['groups'][0]['rules']))


if __name__=='__main__':
    if '--generate' in sys.argv or '--check' in sys.argv:
        content=yaml.safe_dump(fixtures(),sort_keys=False,allow_unicode=True);path=OUT/'tests.promtool.yaml'
        if '--check' in sys.argv:
            if path.read_text()!=content:raise SystemExit('SRE测试fixture需重新生成')
        else:path.write_text(content)
        print('PASS: OS SRE fixtures generated/checked')
    else:unittest.main()
