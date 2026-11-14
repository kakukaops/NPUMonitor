"""Declared production input contract, independent of synthetic data or defaults."""
import copy,json,re
from pathlib import Path
from .selected_catalog import extend_selected_catalog

def definition():return json.loads(Path(__file__).with_name('production-contract.json').read_text())

def prepare(config):
    d=definition();declaration=config.get('source_contract',{})
    if set(declaration)-{'stack','units','metadata','capabilities','nvlink_policy','confirmed'}:raise ValueError('unknown source contract property')
    records={r['metric_id']:r for r in d['coverage']};requested=declaration.get('capabilities',[])
    if not isinstance(requested,list) or len(set(requested))!=len(requested):raise ValueError('capabilities must be unique metric IDs')
    for mid in requested:
        if mid not in records or records[mid]['support'] not in ('numeric_contract','metadata_label','asset_metadata','runtime_feature'):raise ValueError('unsupported capability: '+str(mid))
    selected={r['metric_id'] for r in d['coverage'] if r['requirement']=='必选' and r['support']=='numeric_contract'}|set(requested)
    fields={d['metric_ids'][mid] for mid in selected if mid in d['metric_ids']}
    units=declaration.get('units',{})
    for mid,unit in units.items():
        if mid not in d['metric_ids'] or unit!=d['metric_contracts'][d['metric_ids'][mid]]['unit']:raise ValueError('unit mismatch or unsupported conversion: '+mid)
    metadata=declaration.get('metadata',{})
    if set(metadata)-{'metric','labels'}:raise ValueError('unknown metadata configuration')
    if metadata:
        if metadata.get('metric') in d['metric_contracts']:raise ValueError('metadata info metric must be distinct from numeric fields')
        if not re.fullmatch('[a-zA-Z_:][a-zA-Z0-9_:]*',metadata.get('metric','')):raise ValueError('invalid metadata metric')
        labels=metadata.get('labels',{})
        if set(labels)-set(d['metadata_contract']['required_labels']):raise ValueError('unknown metadata label')
        if any(not re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]*',v) for v in labels.values()):raise ValueError('invalid metadata label mapping')
        if any(labels.get(k,k)!=k for k in ('job','instance','UUID')):raise ValueError('device identity renaming is unsupported')
    if type(declaration.get('confirmed',False)) is not bool:raise ValueError('confirmed must be boolean')
    stack=declaration.get('stack',{})
    if set(stack)-{'gpu_model','driver_version','dcgm_version','exporter_version','nvml_version','form_factor','mig_enabled'}:raise ValueError('unknown stack property')
    if stack.get('mig_enabled') is True:raise ValueError('MIG is outside physical GPU profile')
    if declaration.get('nvlink_policy') not in (None,'active-only-r595-v1'):raise ValueError('unsupported NVLink policy')
    d['selected_fields']=sorted(fields)
    return d

def catalog(base,profile,definition):return extend_selected_catalog(base,profile,definition,production=True)

def declaration_report(config,d):
    c=config.get('source_contract',{});stack=c.get('stack',{});issues=[]
    required=['gpu_model','driver_version','dcgm_version','exporter_version','nvml_version','form_factor']
    if any(not isinstance(stack.get(k),str) or not stack[k].strip() or stack[k].startswith('REPLACE') for k in required):issues.append('stack_versions_not_declared')
    if 'H100' not in stack.get('gpu_model','') or not stack.get('driver_version','').startswith('595.') or stack.get('form_factor') not in ('PCIe','SXM','NVL') or stack.get('mig_enabled') is not False:issues.append('unsupported_or_unverified_stack')
    if c.get('confirmed') is not True:issues.append('source_semantics_not_confirmed')
    if any(d['metric_contracts'][name]['metric_id'] not in c.get('units',{}) for name in d['selected_fields']):issues.append('selected_units_not_declared')
    if not c.get('metadata',{}).get('metric'):issues.append('metadata_source_not_configured')
    if 'DCGM_FI_DEV_NVLINK_GET_STATE' in d['selected_fields'] and c.get('nvlink_policy')!='active-only-r595-v1':issues.append('nvlink_policy_not_selected')
    return {'ready':not issues,'issues':issues,'authority':d['authority'],'selected_fields':d['selected_fields'],'scope':d['scope'],'actual_hardware_tests':'not_run'}


def live_report(config,production,fields,entities,metadata_rows,prometheus_metadata,targets):
    """Check actual per-GPU metadata and mandatory fields; no healthy placeholders."""
    import math,time
    d=production['definition'];declaration=declaration_report(config,d);c=config.get('source_contract',{});mapping=c.get('metadata',{}).get('labels',{});stack=c.get('stack',{})
    expected=d['metadata_contract']['required_labels'];info={};now=time.time();age=config['profile']['freshness_seconds']
    for row in metadata_rows:
        labels=row.get('metric',{});identity=tuple(labels.get(k) for k in ('job','instance','UUID'))
        item={k:labels.get(mapping.get(k,k),'') for k in expected}
        try:valid=float(row['value'][1])==1 and 0<=now-float(row['value'][0])<=age
        except (KeyError,ValueError,TypeError):valid=False
        item['valid_sample']=valid;info.setdefault(identity,[]).append(item)
    metadata=[]
    for identity in sorted({tuple(e['identity'].get(k) for k in ('job','instance','UUID')) for e in entities.values() if e['identity'].get('UUID')}):
        rows=info.get(identity,[]);issues=[]
        if len(rows)!=1:issues.append('missing_or_duplicate_metadata')
        else:
            item=rows[0]
            if not item['valid_sample'] or any(not item[k] for k in expected):issues.append('incomplete_or_invalid_metadata')
            if item['mig_mode']!='disabled':issues.append('unsupported_mig_mode')
            for key in ('driver_version','dcgm_version','exporter_version','nvml_version'):
                if item[key]!=stack.get(key):issues.append('stack_mismatch:'+key)
            if item['modelName']!=stack.get('gpu_model'):issues.append('stack_mismatch:gpu_model')
        metadata.append({'identity':dict(zip(('job','instance','UUID'),identity)),'issues':issues,'ready':not issues})
    metadata_ready=bool(metadata) and all(m['ready'] for m in metadata)
    mandatory=[];coverage_gaps=[];capabilities=[]
    bylogical={x['logical_name']:x for x in fields.values()};selected=set(d['selected_fields'])
    for r in d['coverage']:
        mode=r['support'];mid=r['metric_id']
        if mode=='numeric_contract':
            field=bylogical[r['wire_name']];status=field['status'] if r['wire_name'] in selected else 'not_selected'
            per_device=[]
            for e in entities.values():
                if set(e['identity'])!=set(d['metric_contracts'][r['wire_name']]['identity_labels']):continue
                actual=next((k for k,v in fields.items() if v['logical_name']==r['wire_name']),r['wire_name'])
                if actual not in e['fields'] or actual in e['invalid_fields'] or e['fields'].count(actual)>1:per_device.append(e['identity'])
            if per_device and status=='ready':status='missing_duplicate_or_invalid_per_device'
            if not declaration['ready'] and status=='ready':status='unverified_source_contract'
        elif mode in ('metadata_label','asset_metadata'):status='ready' if metadata_ready and declaration['ready'] else 'missing_or_incompatible_metadata'
        elif mode=='runtime_feature':
            if mid=='inventory.expected_devices':status='ready' if config['profile'].get('gpus') or config['profile'].get('switches') else 'missing_asset_configuration'
            elif mid=='inventory.expected_links':status='ready' if config['profile'].get('links') else 'missing_asset_configuration'
            elif mid=='prometheus.target_up':status='ready' if targets else 'collector_target_not_observed'
            elif mid=='platform.evaluation_status':status='ready' if {x.get('type') for x in prometheus_metadata.get('n9e_alert_rule_eval_total',[])}=={'counter'} else 'platform_counter_not_collected'
            else:status='ready'
        elif mode=='platform_counter_gap':status='ready' if config.get('notification_counter_verified') is True and {x.get('type') for x in prometheus_metadata.get('n9e_alert_alert_notify_error_total',[])}=={'counter'} else 'blocked_unverified_notification_counter'
        else:status=mode
        capabilities.append({'metric_id':mid,'requirement':r['requirement'],'status':status})
        # Collector/device inventory is optional when no missing-device coverage is promised.
        if r['requirement']=='必选' and status!='ready':
            coverage_gaps.append(mid)
            if mode in ('numeric_contract','metadata_label','asset_metadata'):mandatory.append(mid)
    return {'ready':declaration['ready'] and metadata_ready and not mandatory,'declaration_ready':declaration['ready'],'declaration_issues':declaration['issues'],'metadata':metadata,'mandatory_input_gaps':mandatory,'mandatory_coverage_gaps':coverage_gaps,'capabilities':capabilities,'authority':d['authority'],'hardware_validation':'not_run','release_approval':False}
