from pathlib import Path
import sys,json,yaml
R=Path(__file__).resolve().parents[5];M=R/'modules/devices/nvidia-gpu/rules';sys.path.insert(0,str(M/'runtime/src'))
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.master_profile import definition
production='--production' in sys.argv
c=json.loads((M/'runtime/config.example.json').read_text());c['master_profile']='h100-master-simulation-v1';c['profile']=yaml.safe_load((R/'deploy/nvidia-gpu/rules/current/profile.yaml').read_text());master=definition()
if production:
 from npumonitor_rules.production_profile import definition as production_definition
 master=production_definition();c.pop('master_profile');c['contract_profile']='h100-dcgm-master-v1';c['source_contract']={'capabilities':list(master['metric_ids'])}
b=compile_bundle(c);rules={r['rule_id'].split('.',1)[1]:r for r in b['rules']};tests=[]
values={'inforom_invalid':([1],[0]),'memory_unrepairable':([0],[1]),'recovery_required':([0],[1]),'remap_resource_exhausted':([0],[1]),'thermal_margin_exhausted':([35],[-2]),'fabric_manager_error':([0],[1]),'ecc_change_pending':([1,1],[1,0]),'power_violation_recent':([0],['0+1x31']),'gpu_link_down':([1],[0])}
for key,(good,bad) in values.items():
 rule=rules[key]
 for case,vals,expected in [('normal',good,0),('fault',bad,1)]+([('sleep',[2],None),('new_version_unknown',[3],None)] if key=='gpu_link_down' else []):
  dims=rule['identity_labels'];identity={k:{'job':'dcgm-os-sre','instance':'gpu-master-source:9490','UUID':'GPU-CONTRACT-0000','link_id':'0'}[k] for k in dims};lab=','.join(k+'='+json.dumps(v) for k,v in identity.items());series=[]
  for name,value in zip(rule['input_fields'],vals):series.append({'series':name+'{'+lab+'}','values':str(value) if isinstance(value,str) else str(value)+'x31'})
  if production:series.append({'series':'up{job="dcgm-os-sre",instance="gpu-master-source:9490"}','values':'1x31'})
  sample=[] if expected is None else [{'labels':'{'+lab+'}','value':expected}]
  tests.append({'name':key+'_'+case,'interval':'10s','input_series':series,'promql_expr_test':[{'expr':rule['expression'],'eval_time':'2m','exp_samples':sample}]})
if production:
 rule=rules['inforom_invalid'];lab='job="dcgm-os-sre",instance="gpu-master-source:9490",UUID="GPU-CONTRACT-0000"'
 tests.append({'name':'collector_down_never_clears_hardware','interval':'10s','input_series':[{'series':'DCGM_FI_DEV_INFOROM_VALID{'+lab+'}','values':'1x31'},{'series':'up{job="dcgm-os-sre",instance="gpu-master-source:9490"}','values':'0x31'}],'promql_expr_test':[{'expr':rule['expression'],'eval_time':'2m','exp_samples':[]}]})
# Contract-quality checks exercise fractional booleans, percentage/ratio units and duplicate identities.
identity={'job':'dcgm-os-sre','instance':'gpu-master-source:9490','UUID':'GPU-CONTRACT-0000'}
for name,value,case in [('DCGM_FI_DEV_INFOROM_VALID',.5,'fractional_boolean'),('DCGM_FI_DEV_GPU_UTIL',101,'percent_out_of_range'),('DCGM_FI_PROF_SM_ACTIVE',1.5,'ratio_out_of_range')]:
 lab=','.join(k+'='+json.dumps(v) for k,v in identity.items());expected=dict(identity,metric_name=name)
 tests.append({'name':case,'interval':'10s','input_series':[{'series':name+'{'+lab+'}','values':str(value)+'x31'},{'series':'up{job="dcgm-os-sre",instance="gpu-master-source:9490"}','values':'1x31'}],
  'promql_expr_test':[{'expr':rules['master_input_invalid']['expression'],'eval_time':'2m','exp_samples':[{'labels':'{'+','.join(k+'='+json.dumps(v) for k,v in expected.items())+'}','value':1}]}]})
name='DCGM_FI_DEV_FB_USED';lab=','.join(k+'='+json.dumps(v) for k,v in identity.items());expected=dict(identity,metric_name=name)
tests.append({'name':'new_field_duplicate','interval':'10s','input_series':[{'series':name+'{'+lab+',replica="a"}','values':'20000x31'},{'series':name+'{'+lab+',replica="b"}','values':'20000x31'},{'series':'up{job="dcgm-os-sre",instance="gpu-master-source:9490"}','values':'1x31'}], 'promql_expr_test':[{'expr':rules['master_input_duplicate']['expression'],'eval_time':'2m','exp_samples':[{'labels':'{'+','.join(k+'='+json.dumps(v) for k,v in expected.items())+'}','value':2}]}]})
name='DCGM_FI_DEV_GPU_UTIL';expected=dict(identity,metric_name=name)
tests.append({'name':'new_field_stale_original_timestamp','interval':'10s','input_series':[{'series':name+'{'+lab+'}','values':'42'},{'series':'up{job="dcgm-os-sre",instance="gpu-master-source:9490"}','values':'1x31'}], 'promql_expr_test':[{'expr':rules['master_input_stale']['expression'],'eval_time':'2m','exp_samples':[{'labels':'{'+','.join(k+'='+json.dumps(v) for k,v in expected.items())+'}','value':120}]}]})
(M/('runtime/production/tests.promtool.yaml' if production else 'runtime/master/tests.promtool.yaml')).write_text(yaml.safe_dump({'evaluation_interval':'10s','tests':tests},allow_unicode=True,sort_keys=False));print('Generated',len(tests),'actual PromQL cases')
