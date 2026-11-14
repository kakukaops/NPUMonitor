#!/usr/bin/env python3
"""Generate a production input contract from doc14, independently of simulator defaults."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
MODULE=Path(__file__).resolve().parents[1];GPU=MODULE.parent
ROOT=GPU.parents[2]
sys.path.insert(0,str(MODULE/'runtime/src'))
from npumonitor_rules.selected_catalog import extend_selected_catalog
from build_os_sre import compile_profile
import yaml

def build():
    registry=json.loads((GPU/'common/monitoring/catalog/monitoring-contract.json').read_text())
    if registry['authority']['sha256']!=hashlib.sha256((MODULE/'docs/14-GPU监控指标与告警规则说明表.md').read_bytes()).hexdigest():raise ValueError('master changed; regenerate public contract first')
    base=json.loads((MODULE/'monitoring/os-sre/catalog.json').read_text());records=registry['metrics']
    # Reviewed preferred export names; aliases may rename only, never convert units.
    preferred={'nvidia.board_power':'DCGM_FI_DEV_POWER_USAGE','nvidia.requested_power_limit':'DCGM_FI_DEV_POWER_MGMT_LIMIT','nvidia.enforced_power_limit':'DCGM_FI_DEV_ENFORCED_POWER_LIMIT','nvidia.gr_engine_ratio':'DCGM_FI_PROF_GR_ENGINE_ACTIVE','nvidia.sm_active_ratio':'DCGM_FI_PROF_SM_ACTIVE','nvidia.sm_occupancy_ratio':'DCGM_FI_PROF_SM_OCCUPANCY','nvidia.tensor_active_ratio':'DCGM_FI_PROF_PIPE_TENSOR_ACTIVE','nvidia.dram_active_ratio':'DCGM_FI_PROF_DRAM_ACTIVE','nvidia.fb_used_ratio':'DCGM_FI_DEV_FB_USED_RATIO','nvidia.remapped_correctable':'DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS','nvidia.remapped_uncorrectable':'DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS','nvidia.nvlink_aggregate_rate':'DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL'}
    fields={};by_id={};coverage=[]
    for mid,r in sorted(records.items()):
        item={k:r[k] for k in ['metric_id','requirement','semantic_type','semantic_unit','entity','identity','category','doc_anchor','names_and_aliases','sources']}
        if r['field_id'] is None:item['support']='external' if r['requirement']=='外部' else 'excluded' if r['requirement']=='排除' else 'platform_counter_gap' if mid=='platform.notification_status' else 'asset_metadata' if mid=='inventory.hardware_stack' else 'runtime_feature'
        elif r['semantic_type'] in ('label','string'):item['support']='metadata_label'
        elif r['semantic_type']=='unknown':item['support']='unsupported_semantics'
        else:
            found=sorted(set(r['names_and_aliases'])&set(base['metric_contracts']));name=found[0] if found else preferred.get(mid,r['names_and_aliases'][0]);t=r['semantic_type'];unit=r['semantic_unit']
            if found:c=copy.deepcopy(base['metric_contracts'][name])
            else:
                kind='counter' if t=='counter' else 'boolean' if unit=='boolean' or t=='boolean' else 'gauge' if t in ('gauge','ratio') else 'integer'
                c={'kind':kind,'minimum':-273.15 if unit=='celsius' else 0,'maximum':1.000000001 if t=='ratio' or unit in ('ratio','0–1') else 100.000000001 if unit=='percent' else 2 if kind=='boolean' else 9007199254740991,'unit':unit,'identity_labels':r['identity'].split(','),'alternative_identity_labels':[r['identity'].split(',')],'business_labels_required':False}
            c.update(metric_id=mid,requirement=r['requirement'],category=r['category'])
            if mid=='nvidia.nvlink_link_state':c['allowed_values']=[0,1,2]
            if mid=='nvidia.recovery_action':c['allowed_values']=[0,1,2,3,4]
            if mid=='nvidia.pstate':c['allowed_values']=list(range(16))
            fields[name]=c;by_id[mid]=name;item.update(support='numeric_contract',wire_name=name,expected_type='counter' if c['kind']=='counter' else 'gauge')
        coverage.append(item)
    definition={'schema':1,'profile':'h100-dcgm-master-v1','authority':registry['authority'],'scope':'Declared H100 physical GPU input contract; not a hardware/driver certification; no simulator dependency','metric_contracts':fields,'metric_ids':by_id,'coverage':coverage,'nvlink_policy':{'version_scope':'declared R595 observation policy','fault':[0],'clear':[1],'unknown':[2],'unsupported':[3]},'metadata_contract':{'required_labels':['UUID','modelName','driver_version','dcgm_version','exporter_version','nvml_version','mig_mode'],'required_identity':['job','instance','UUID']}}
    profile=yaml.safe_load((MODULE/'monitoring/os-sre/profile.yaml').read_text());catalog=extend_selected_catalog(compile_profile(profile,with_provenance=False),profile,definition,production=True)
    return definition,catalog

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args();definition,catalog=build()
    dest=MODULE/'runtime/production';dest.mkdir(exist_ok=True)
    for path,data in [(MODULE/'runtime/src/npumonitor_rules/production-contract.json',definition),(dest/'catalog.json',catalog)]:
        text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('Stale production artifact: '+str(path))
        else:path.write_text(text)
    print('PASS: production contract: %s numeric fields, %s tracked entries, %s rules; no fixture defaults'%(len(definition['metric_contracts']),len(definition['coverage']),len(catalog['rules'])))
if __name__=='__main__':main()
