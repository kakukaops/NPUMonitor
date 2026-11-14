"""Offline compilation. Static OS assets are inlined, never written to Prometheus."""
import copy,hashlib,json,math,re,sys
from pathlib import Path
from urllib.parse import urlsplit

EMPTY='(vector(0) > 0)'
IDENTITIES=('job','instance','UUID','switch_id','link_id','metric_name')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def number(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('numeric policy outside supported range')
    return value

def url(value):
    p=urlsplit(value)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment:raise ValueError('URL must be HTTP(S), without embedded credentials/query/fragment')
    return value.rstrip('/')

def compile_bundle(config,root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(root/'scripts'))
    from build_os_sre import compile_profile
    config=copy.deepcopy(config)
    allowed={'deployment_id','profile','upstream','gateway','nightingale','watchdog','limits','rule_overrides','contract_profile','notification_counter_verified','master_profile','source_contract'}
    if set(config)-allowed:raise ValueError('unknown production configuration fields')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',config.get('deployment_id','')):raise ValueError('invalid deployment identity')
    production=config.get('contract_profile')=='h100-dcgm-master-v1'
    if config.get('contract_profile') not in ('dcgm-os-sre-physical-v1','h100-dcgm-master-v1'):raise ValueError('explicit supported field/enum contract must be selected')
    upstream=config['upstream'];url(upstream['url'])
    if set(upstream)-{'url','auth_file','metric_aliases'}:raise ValueError('unknown upstream option')
    profile=config['profile'];declared=None
    if production:
        from .production_profile import prepare
        declared=prepare(config)
    catalog=compile_profile(profile,with_provenance=False,additional_required_fields=declared['selected_fields'] if declared else ())
    if production:
        if config.get('master_profile'):raise ValueError('production and simulation profiles cannot be combined')
        from .production_profile import prepare,catalog as production_catalog,declaration_report
        declared=prepare(config);catalog=production_catalog(catalog,profile,declared)
    elif config.get('source_contract'):raise ValueError('source_contract requires production master profile')
    if config.get('master_profile'):
        if config['master_profile']!='h100-master-simulation-v1':raise ValueError('unknown master simulation profile')
        from .master_profile import extend_catalog
        catalog=extend_catalog(catalog,profile)
    aliases=upstream.get('metric_aliases',{})
    for name,actual in aliases.items():
        if name not in catalog['metric_contracts'] or not re.fullmatch('[a-zA-Z_:][a-zA-Z0-9_:]*',actual):raise ValueError('unknown or invalid metric alias')
    effective_names=[aliases.get(n,n) for n in catalog['metric_contracts']]
    if len(effective_names)!=len(set(effective_names)):raise ValueError('metric aliases merge distinct logical fields')
    gateway=config['gateway']
    if set(gateway)-{'admin_token_file','viewer_token_file','listen','port','tls_cert_file','tls_key_file'}:raise ValueError('unknown gateway option')
    for field in ('admin_token_file','viewer_token_file'):
        if not isinstance(gateway.get(field),str) or not gateway[field].startswith('/'):raise ValueError('secret references must be absolute file paths')
    lim={'poll_seconds':30,'query_timeout_seconds':7,'query_workers':4,'max_response_bytes':32*1024*1024,'max_series':100000,
         'max_states':300000,'max_poll_age_seconds':120,'max_source_gap_seconds':90,'recovery_ttl_seconds':600,'preflight_seconds':120}
    if set(config.get('limits',{}))-set(lim):raise ValueError('unknown runtime limit')
    lim.update(config.get('limits',{}))
    for k,v in lim.items():number(v,1,300000000)
    for k in ('query_workers','max_response_bytes','max_series','max_states'):
        if type(lim[k]) is not int:raise ValueError('integer runtime quota required')
    if lim['query_workers']>16 or lim['max_response_bytes']>64*1024*1024:raise ValueError('runtime quota too large')
    for name,lo,hi in [('poll_seconds',1,300),('query_timeout_seconds',1,30),('max_source_gap_seconds',1,3600),('max_poll_age_seconds',3,3600),('preflight_seconds',1,3600),('recovery_ttl_seconds',10,3600)]:number(lim[name],lo,hi)
    if type(lim['query_timeout_seconds']) is not int:raise ValueError('query timeout requires integer seconds')
    config['limits']=lim
    records={}
    for row in catalog['inventory_records']:records.setdefault(row['record'],[]).append(row['expr'])
    inventory={k:'('+' or '.join(v)+')' for k,v in records.items()}
    all_inventory={'sre:inventory:'+k for k in ('gpu_expected','switch_expected','input_expected','pcie_gen','pcie_width','pcie_active_bps','fabric_expected','gpu_link_expected','switch_link_expected','monitor_expected','evaluation_expected')}
    overrides=config.get('rule_overrides',{})
    if set(overrides)-{r['rule_id'] for r in catalog['rules']}:raise ValueError('unknown rule override')
    rules=[]
    def names(expr):
        for name,actual in sorted(aliases.items(),key=lambda i:-len(i[0])):expr=re.sub(r'(?<![\w:])'+re.escape(name)+r'(?![\w:])',actual,expr)
        return expr
    for original in catalog['rules']:
        r={k:copy.deepcopy(original[k]) for k in ('rule_id','title','kind','expression','identity_labels','input_fields','for_seconds','severity','requirements','status','note','source_ids')}
        r['enabled']=True;ov=overrides.get(r['rule_id'],{})
        if set(ov)-{'enabled','for_seconds','severity'}:raise ValueError('unsupported rule override')
        if 'enabled' in ov and type(ov['enabled']) is not bool:raise ValueError('enabled must be boolean')
        r.update(ov);number(r['for_seconds'],0,3600)
        if r['severity'] not in (1,2,3):raise ValueError('invalid severity')
        # A verified native counter is an opt-in capability, never replaced with a demo value.
        if r['rule_id']=='os_sre.platform_notify_failure' and config.get('notification_counter_verified') is True:
            job=json.dumps(profile['nightingale_job_regex']);w=profile['counter_window_seconds']
            r['expression']=f'sum by (job,instance) (increase(n9e_alert_alert_notify_error_total{{job=~{job}}}[{w}s])) > 0'
            r['status']='candidate';r['note']='Native Nightingale notification error counter; channel scope and integration verified by deployment operator.'
        r['inventory_dependencies']=sorted(n for n in all_inventory if n in (r['expression'] or ''))
        r['inventory_configured']=(True if r['rule_id'] in ('os_sre.collector_down','os_sre.platform_nightingale_metrics_missing') else any(n in inventory for n in r['inventory_dependencies']) if r['rule_id']=='os_sre.entity_missing' else all(n in inventory for n in r['inventory_dependencies']))
        if production:
            unselected=set(r['input_fields'])&set(declared['metric_contracts'])-set(declared['selected_fields'])
            if unselected:
                r['enabled']=False;r['capability_status']='not_selected';r['capability_reason']=sorted(unselected)
            if r['rule_id'] in ('os_sre.input_invalid','os_sre.input_stale','os_sre.input_duplicate','os_sre.field_missing'):
                r['enabled']=False;r['capability_status']='replaced_by_selected_quality_rules'
        if not r['expression']:r['enabled']=False
        if r['expression']:
            expr=r['expression']
            for metric in sorted(all_inventory,key=len,reverse=True):expr=re.sub(r'(?<![\w:])'+re.escape(metric)+r'(?![\w:])',lambda m:inventory.get(metric,EMPTY),expr)
            r['expression']=names(expr)
        r['required_metrics']=[aliases.get(n,n) for n in r['input_fields'] if n.startswith('DCGM_')]
        r['clock_expression']=None
        if r['kind']=='stateful':
            identity=r['identity_labels'];parts=[]
            for field in r['input_fields']:
                if not field.startswith('DCGM_'):continue
                actual=aliases.get(field,field);selector=[f'job=~{json.dumps(profile["collector_job_regex"])}']
                selector += [k+'!=""' for k in identity if k not in ('job','instance')]
                if 'UUID' in identity:selector+=['GPU_I_ID=""','GPU_I_PROFILE=""']
                parts.append('label_replace(timestamp('+actual+'{'+','.join(selector)+'}),"sre_clock_field",'+json.dumps(field)+',"__name__",".*")')
            if not parts:raise ValueError('stateful rule missing source clock contract')
            union='('+' or '.join(parts)+')';by=','.join(identity)
            r['clock_expression']=f'(min by ({by}) ({union})) and on ({by}) (count by ({by}) ({union}) == {len(parts)})'
        r['signature']=digest(r);rules.append(r)
    bundle={'schema':1,'version':'1.0.0-rc1','config':config,'rules':rules,'metric_contracts':catalog['metric_contracts'],
            'inventory_record_count':len(catalog['inventory_records']),'source_catalog_version':catalog['version']}
    if production:bundle['production_contract']={'definition':declared,'declaration':declaration_report(config,declared)}
    bundle['sha256']=digest(bundle);validate_bundle(bundle);return bundle


def validate_bundle(b):
    if b.get('schema')!=1 or b.get('sha256')!=digest({k:v for k,v in b.items() if k!='sha256'}):raise ValueError('bundle checksum/schema mismatch')
    if len({r['rule_id'] for r in b['rules']})!=len(b['rules']):raise ValueError('duplicate rules')
    for r in b['rules']:
        if r.get('signature')!=digest({k:v for k,v in r.items() if k!='signature'}):raise ValueError('rule signature mismatch')
        if r.get('kind') not in ('stateful','direct') or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}',r['rule_id']):raise ValueError('invalid compiled rule')
        if r['expression'] and 'sre:inventory:' in r['expression']:raise ValueError('external recording rule dependency')
        if r['expression'] and re.search(r'\b(cluster_id|task_id|job_id|entity_id|tenant|pod)\b',r['expression']):raise ValueError('business label dependency')
        if r['kind']=='stateful' and not r['clock_expression']:raise ValueError('source clock missing')
    return b


def recovery_vectors(actions,identity):
    parts=[]
    for action in actions:
        labels=action['identity']
        if not all(k in labels for k in identity):continue
        expr='vector(1)'
        for k in identity:expr='label_replace(('+expr+'),'+json.dumps(k)+','+json.dumps(labels[k])+',"__name__",".*")'
        parts.append(expr)
    return '('+' or '.join(parts)+')' if parts else EMPTY


def expand_recovery(rule,actions):
    expression=rule['expression']
    if not expression or 'os_sre_recovery_verified' not in expression:return expression
    expr=recovery_vectors(actions,rule['identity_labels'])
    return re.sub(r'os_sre_recovery_verified\{(?:[^"{}]|"(?:\\.|[^"\\])*")*\}',lambda m:expr,expression)
