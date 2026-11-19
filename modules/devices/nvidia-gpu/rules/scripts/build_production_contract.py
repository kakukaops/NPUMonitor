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

def build(native_triggers=None):
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
    profile=yaml.safe_load((MODULE/'monitoring/os-sre/profile.yaml').read_text());catalog=extend_selected_catalog(compile_profile(profile,with_provenance=False,native_triggers=native_triggers),profile,definition,production=True,native_triggers=native_triggers)
    return definition,catalog

def prometheus_rules(catalog, native_triggers):
    groups = []
    inventory = catalog['inventory_records']
    if inventory:
        groups.append({'name': 'os-sre-gpu-inventory', 'interval': '30s', 'rules': inventory})

    alerts = []
    for rule in catalog['rules']:
        if rule['kind'] != 'stateful':
            continue
        rule_id = rule['rule_id']
        title = rule['title']
        expression = rule['expression']
        annotations = {'summary': title + ' · {{ $labels.instance }}',
                       'input_metrics': ', '.join(rule['input_fields'])}
        if rule_id.startswith(('os_sre.xid_', 'os_sre.sxid_')):
            expression = native_triggers[rule_id]
            code = 'SXID' if rule_id.startswith('os_sre.sxid_') else 'XID'
            annotations['summary'] = f'{title} · {code} {{{{ printf "%.0f" $value }}}} · {{{{ $labels.instance }}}}'
            annotations[code.lower() + '_code'] = '{{ printf "%.0f" $value }}'
            annotations['input_metrics'] = rule['input_fields'][0]
        else:
            # Stateful boolean observations must be filtered before native alerting.
            expression = native_triggers.get(rule_id, f'({expression}) == 1')
        identity = 'switch_id' if 'switch_id' in rule['identity_labels'] else 'UUID'
        annotations['summary'] += ' · {{ $labels.' + identity + ' }}'
        if 'link_id' in rule['identity_labels']:
            annotations['summary'] += ' · port {{ $labels.link_id }}'
        alerts.append({
            'alert': rule_id.replace('.', '_'),
            'expr': expression,
            'for': f'{rule["for_seconds"]}s',
            'labels': {'severity': str(rule['severity']), 'sre_rule_id': rule_id},
            'annotations': annotations,
        })
    groups.append({'name': 'os-sre-gpu-native', 'interval': '30s', 'rules': alerts})
    return {'groups': groups}


def prometheus_yaml(catalog, native_triggers):
    return yaml.safe_dump(prometheus_rules(catalog, native_triggers), allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--prometheus-profile', type=Path)
    parser.add_argument('--prometheus-output', type=Path)
    args = parser.parse_args()
    if args.prometheus_profile and not args.prometheus_output:
        parser.error('--prometheus-profile requires --prometheus-output')
    native_triggers = {}
    definition,catalog=build(native_triggers)
    if args.prometheus_output:
        if args.prometheus_profile:
            profile = yaml.safe_load(args.prometheus_profile.read_text())
            base = compile_profile(profile, with_provenance=False,
                                   additional_required_fields=definition['metric_contracts'],
                                   native_triggers=native_triggers)
            catalog = extend_selected_catalog(base, profile, definition, production=True, native_triggers=native_triggers)
        text = prometheus_yaml(catalog, native_triggers)
        if args.check:
            if args.prometheus_output.read_text() != text:
                raise SystemExit('Stale Prometheus rules: ' + str(args.prometheus_output))
        else:
            args.prometheus_output.write_text(text)
        return
    dest=MODULE/'runtime/production';dest.mkdir(exist_ok=True)
    for path,data in [(MODULE/'runtime/src/npumonitor_rules/production-contract.json',definition),(dest/'catalog.json',catalog)]:
        text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('Stale production artifact: '+str(path))
        else:path.write_text(text)
    native = dest/'gpu-native-alerts.prom.yaml'
    text = prometheus_yaml(catalog, native_triggers)
    if args.check:
        if not native.exists() or native.read_text() != text:
            raise SystemExit('Stale Prometheus rules: ' + str(native))
    else:
        native.write_text(text)
    print('PASS: production contract: %s numeric fields, %s tracked entries, %s rules; no fixture defaults'%(len(definition['metric_contracts']),len(definition['coverage']),len(catalog['rules'])))
if __name__=='__main__':main()
