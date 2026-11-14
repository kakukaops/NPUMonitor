import json,copy,math
from pathlib import Path
R=Path(__file__).resolve().parents[5];M=R/'modules/devices/nvidia-gpu/rules';index=json.loads((M/'docs/14-GPU监控指标与告警规则说明表.coverage.json').read_text());base=json.loads((M/'monitoring/os-sre/catalog.json').read_text());existing=base['metric_contracts'];records=index['candidate_dispositions']+index['beyond_candidate_contracts']
preferred={'nvidia.board_power':'DCGM_FI_DEV_POWER_USAGE','nvidia.requested_power_limit':'DCGM_FI_DEV_POWER_MGMT_LIMIT','nvidia.enforced_power_limit':'DCGM_FI_DEV_ENFORCED_POWER_LIMIT','nvidia.gr_engine_ratio':'DCGM_FI_PROF_GR_ENGINE_ACTIVE','nvidia.sm_active_ratio':'DCGM_FI_PROF_SM_ACTIVE','nvidia.sm_occupancy_ratio':'DCGM_FI_PROF_SM_OCCUPANCY','nvidia.tensor_active_ratio':'DCGM_FI_PROF_PIPE_TENSOR_ACTIVE','nvidia.dram_active_ratio':'DCGM_FI_PROF_DRAM_ACTIVE','nvidia.fb_used_ratio':'DCGM_FI_DEV_FB_USED_RATIO','nvidia.remapped_correctable':'DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS','nvidia.remapped_uncorrectable':'DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS','nvidia.nvlink_aggregate_rate':'DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL'}
normal_by_id={84:1,100:1410,101:1593,153:35,155:250,157:250,158:90,159:100,160:700,164:700,171:0,174:0,190:0,203:42,204:25,235:5,236:16,240:0,250:81920,251:54613,252:26214,253:1093,254:26214/(81920-1093),300:1,301:1,385:0,386:16,387:0,388:0,389:0,390:0,391:0,392:0,393:0,394:0,1001:.42,1002:.35,1003:.4,1004:.24,1005:.25,1011:12000000000,1012:10000000000,449:22000,1507:0,1523:0,1617:0,1618:0}
contracts={};coverage=[];defaults={};by_id={}
for r in records:
 record={'metric_id':r['metric_id'],'field_id':r['field_id'],'requirement':r['requirement'],'source_anchor':r['doc_anchor'],'names_and_aliases':r['names_and_aliases']}
 if r['field_id'] is None:
  record.update(mode='excluded' if r['requirement']=='排除' else 'existing_feature' if r['implementation_status']=='current_feature' else 'external_fixture' if r['requirement']=='外部' else 'metadata_or_capability_gap');coverage.append(record);continue
 if r['semantic_type'] in ('label','string'):
  record.update(mode='metadata',wire_name='sre_sim_gpu_info');coverage.append(record);continue
 if r['semantic_type']=='unknown':
  record.update(mode='unsupported_semantics',reason='Master definition does not establish code/counter semantics; no fabricated healthy samples');coverage.append(record);continue
 found=[n for n in r['names_and_aliases'] if n in existing];name=found[0] if found else preferred.get(r['metric_id'],r['names_and_aliases'][0]);by_id[r['metric_id']]=name
 if found:c=copy.deepcopy(existing[name])
 else:
  t=r['semantic_type'];kind='counter' if t=='counter' else 'boolean' if r['semantic_unit']=='boolean' or t=='boolean' else 'gauge' if t in ('gauge','ratio') else 'integer';low=-273.15 if r['semantic_unit']=='celsius' else 0;high=1.000000001 if t=='ratio' or r['semantic_unit'] in ('ratio','0–1') else 100.000000001 if r['semantic_unit']=='percent' else 2 if kind=='boolean' else 9007199254740991
  c={'kind':kind,'minimum':low,'maximum':high,'unit':r['semantic_unit'],'identity_labels':r['identity'].split(','),'alternative_identity_labels':[r['identity'].split(',')],'business_labels_required':False}
 contracts[name]=c;record.update(mode='numeric_simulation',wire_name=name,type='counter' if c['kind']=='counter' else 'gauge',unit=c['unit']);coverage.append(record)
 if r['field_id'] in normal_by_id:defaults[name]=normal_by_id[r['field_id']]
profile={'schema':1,'profile':'h100-master-simulation-v1','master_revision':index['document_revision'],'master_document_sha256':index['document_sha256'],'scope':'Synthetic all-selected-capabilities fixture; not a certified real H100 exporter mapping','metric_contracts':contracts,'coverage':coverage,'defaults':defaults,'metric_ids':by_id,'scenarios':{}}
scenarios={'resource_busy':{'nvidia.gpu_util':96,'nvidia.sm_active_ratio':.91,'nvidia.tensor_active_ratio':.8},'memory_capacity_high':{'nvidia.fb_used':77000,'nvidia.fb_free':3827},'inforom_invalid':{'nvidia.inforom_valid':0},'memory_unrepairable':{'nvidia.memory_unrepairable':1},'recovery_required':{'nvidia.recovery_action':1},'remap_exhausted':{'nvidia.remap_bank_none':1,'nvidia.remap_bank_high':15},'thermal_margin':{'nvidia.gpu_temp_margin':-2,'nvidia.gpu_temp':92},'power_violation':{'nvidia.power_violation_ns':1000000000},'ecc_pending':{'nvidia.ecc_pending':0},'fabric_error':{'nvidia.fm_error':1},'nvlink_sleep':{'nvidia.nvlink_link_state':2},'nvlink_disabled':{'nvidia.nvlink_link_state':3},'nvlink_inactive':{'nvidia.nvlink_link_state':0}}
for key,vals in scenarios.items():profile['scenarios'][key]={by_id[mid]:value for mid,value in vals.items()}
# Every master item receives an explicit simulation disposition; no unclassified fallback.
# Preserve the core fixture's fixed enum/limit contract by wire name.
stable_names={'DCGM_FI_DEV_GPU_TEMP':55,'DCGM_FI_DEV_GPU_MAX_OP_TEMP':95,'DCGM_FI_DEV_MEMORY_TEMP':60,
'DCGM_FI_DEV_MEM_MAX_OP_TEMP':110,'DCGM_FI_DEV_PCIE_LINK_GEN':5,'DCGM_FI_DEV_PCIE_LINK_WIDTH':16,
'DCGM_FI_DEV_NVLINK_GET_STATE':1,'DCGM_FI_DEV_FABRIC_MANAGER_STATUS':3,'DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY':1,
'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT':50,'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_LIMIT_SLOWDOWN':95,'DCGM_FI_DEV_NVSWITCH_LINK_STATUS':2}
for name in contracts:defaults.setdefault(name,stable_names.get(name,0))
dynamic_ids=set('gpu_util mem_copy_util gr_engine_ratio sm_active_ratio sm_occupancy_ratio tensor_active_ratio dram_active_ratio fb_used fb_free board_power board_power_raw gpu_temp memory_temp gpu_temp_margin sm_clock pcie_tx_rate pcie_rx_rate nvlink_tx_rate nvlink_rx_rate nvlink_aggregate_rate switch_temp'.split())
limit_ids=set('mem_clock memory_max_temp gpu_max_temp slowdown_temp shutdown_temp requested_power_limit enforced_power_limit pcie_max_gen pcie_max_width fb_total fb_reserved'.split())
for item in coverage:
    mid=item['metric_id'];short=mid.removeprefix('nvidia.');mode=item['mode']
    if mode=='numeric_simulation':
        name=item['wire_name'];kind=contracts[name]['kind']
        behavior='load_correlated' if short in dynamic_ids else 'derived_capacity_ratio' if short=='fb_used_ratio' else 'power_integral_millijoules' if short=='energy' else 'event_counter' if kind=='counter' else 'fixed_device_configuration' if short in limit_ids else 'discrete_health_or_configuration'
        item['simulation']={'behavior':behavior,'baseline':defaults[name],'fault_control':'counter_activity or override' if kind=='counter' else 'scenario or override','identity_scoped':True,'unit':item['unit']}
    else:item['simulation']={'behavior':mode,'fault_control':'not a numeric DCGM sample','reason':'Explicit master disposition; unknown/excluded inputs are never fabricated'}
profile['simulation_policy_version']=1
p=M/'runtime/src/npumonitor_rules/master-profile.json';p.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n');print('master fixture',len(contracts),'numeric fields;',len(coverage),'tracked master items;',len([r for r in coverage if r['mode']=='metadata']),'metadata definitions')

# The simulator consumes this public, credential-free catalog; runtime compiles the same policy per deployment.
import sys,yaml
sys.path.insert(0,str(M/'runtime/src'));sys.path.insert(0,str(M/'scripts'))
from build_os_sre import compile_profile
from npumonitor_rules.master_profile import extend_catalog
p=yaml.safe_load((R/'deploy/nvidia-gpu/rules/current/profile.yaml').read_text())
catalog=extend_catalog(compile_profile(p,with_provenance=False),p)
(M/'runtime/master/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
print('Master simulation catalog:',len(catalog['rules']),'rules')
