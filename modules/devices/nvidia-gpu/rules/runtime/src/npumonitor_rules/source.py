"""Bounded read-only Prometheus client and declared metric-contract preflight."""
import base64,json,math,re,threading,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener
from .bundle import canonical,IDENTITIES

class SourceError(RuntimeError):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**k):return None

class Source:
    def __init__(self,bundle):
        self.bundle=bundle;self.config=bundle['config'];self.limit=self.config['limits'];self.base=self.config['upstream']['url']
        self.opener=build_opener(ProxyHandler({}),NoRedirect());self.lock=threading.Lock();self.stats={'requests':0,'errors':0,'bytes':0}
    def request(self,path,params):
        headers={};file=self.config['upstream'].get('auth_file')
        if file:
            auth=json.loads(Path(file).read_text())
            if auth.get('type')=='bearer':headers['Authorization']='Bearer '+auth['token']
            elif auth.get('type')=='basic':headers['Authorization']='Basic '+base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
            else:raise SourceError('unsupported upstream credential type')
        data=urlencode(params).encode()
        if len(data)>512*1024:raise SourceError('query request quota exceeded')
        if path.endswith('/query'):
            headers['Content-Type']='application/x-www-form-urlencoded';request=Request(self.base+path,data=data,headers=headers,method='POST')
        else:request=Request(self.base+path+'?'+urlencode(params),headers=headers)
        try:
            with self.opener.open(request,timeout=self.limit['query_timeout_seconds']) as response:raw=response.read(self.limit['max_response_bytes']+1)
            if len(raw)>self.limit['max_response_bytes']:raise SourceError('query response quota exceeded')
            value=json.loads(raw)
            if value.get('status')!='success' or value.get('warnings'):raise SourceError('upstream returned error or incomplete data')
            with self.lock:self.stats['bytes']+=len(raw)
            return value['data']
        except Exception as exc:
            with self.lock:self.stats['errors']+=1
            raise SourceError('upstream request failed: '+type(exc).__name__) from None
        finally:
            with self.lock:self.stats['requests']+=1
    def query(self,expression,at=None):
        params={'query':expression,'timeout':str(self.limit['query_timeout_seconds'])+'s'}
        if at is not None:params['time']=str(at)
        data=self.request('/api/v1/query',params)
        if data.get('resultType')!='vector' or not isinstance(data.get('result'),list):raise SourceError('expected instant vector')
        if len(data['result'])>self.limit['max_series']:raise SourceError('series cardinality quota exceeded')
        return data['result']
    def preflight(self):
        profile=self.config['profile'];aliases=self.config['upstream'].get('metric_aliases',{})
        names=[aliases.get(n,n) for n in self.bundle['metric_contracts'] if n.startswith('DCGM_')]
        job=json.dumps(profile['collector_job_regex']);selector='{job=~'+job+',__name__=~'+json.dumps('|'.join(map(re.escape,names)))+'}'
        production=self.bundle.get('production_contract');meta_config=self.config.get('source_contract',{}).get('metadata',{})
        extra=(' or '+meta_config['metric']+'{job=~'+job+'}') if production and meta_config.get('metric') else ''
        raw=self.query(selector+' or up{job=~'+job+'}'+extra)
        clocks={}
        if production:
            clock_rows=self.query('timestamp(label_replace(('+selector+extra+'),"sre_source_field","$1","__name__","(.*)"))')
            for row in clock_rows:
                labels={k:v for k,v in row['metric'].items() if k!='__name__'}
                # timestamp() drops metric names; inject a name label in the query below to disambiguate.
                clocks[canonical(labels)]=float(row['value'][1])
        metadata=self.request('/api/v1/metadata',{'limit':5000})
        if not isinstance(metadata,dict):raise SourceError('metadata contract mismatch')
        lookup={aliases.get(n,n):v for n,v in self.bundle['metric_contracts'].items()}
        present=set();target_up=[];entities={};invalid_id=0;metadata_rows=[]
        for row in raw:
            lab=row['metric'];name=lab.get('__name__')
            source_stamp=None
            if production and name!='up':
                clock_labels={k:v for k,v in lab.items() if k!='__name__'};clock_labels['sre_source_field']=name
                source_stamp=clocks.get(canonical(clock_labels))
            if production and name==meta_config.get('metric'):
                copied=dict(row);copied['value']=[source_stamp if source_stamp is not None else 0,row['value'][1]]
                metadata_rows.append(copied);continue
            if name=='up':target_up.append({'job':lab.get('job'),'instance':lab.get('instance'),'up':row['value'][1]});continue
            if lab.get('GPU_I_ID') or lab.get('GPU_I_PROFILE'):continue
            present.add(name)
            contract=lookup.get(name)
            if not contract:continue
            dims=contract['identity_labels']
            if not all(lab.get(k) for k in dims):invalid_id+=1;continue
            identity={k:lab[k] for k in dims};key=canonical(identity)
            entity=entities.setdefault(key,{'identity':identity,'fields':[],'invalid_fields':[]})
            entity['fields'].append(name)
            try:
                value=float(row['value'][1]);valid=math.isfinite(value) and contract['minimum']<=value<contract['maximum'] and (contract['kind']=='gauge' or contract.get('unit')=='seconds' or value==math.floor(value)) and (not contract.get('allowed_values') or value in contract['allowed_values'])
            except (ValueError,TypeError):valid=False
            if production and (source_stamp is None or not math.isfinite(source_stamp) or not 0<=time.time()-source_stamp<=profile['freshness_seconds']):valid=False
            if not valid:entity['invalid_fields'].append(name)
        fields={}
        for logical,contract in self.bundle['metric_contracts'].items():
            if not logical.startswith('DCGM_'):continue
            actual=aliases.get(logical,logical);expected='counter' if contract['kind']=='counter' else 'gauge';types={r.get('type') for r in metadata.get(actual,[])}
            status='ready' if actual in present and types=={expected} else 'missing_field' if actual not in present else 'unverified_or_mismatched_type'
            fields[actual]={'logical_name':logical,'status':status,'expected_type':expected,'reported_types':sorted(t for t in types if t),'unit':contract['unit'],'unit_verification':'declared contract; not inferred from numeric values'}
        production_report=None
        if production:
            from .production_profile import live_report
            production_report=live_report(self.config,production,fields,entities,metadata_rows,metadata,target_up)
            selected=set(production['definition']['selected_fields'])
            for actual,field in fields.items():
                if field['logical_name'] not in selected:field['status']='not_selected'
                field['unit_verification']='deployment declaration; never inferred from values or HELP/TYPE'
                if field['logical_name'] in selected and not production_report['declaration_ready']:field['status']='unverified_source_contract'
        rules={}
        for rule in self.bundle['rules']:
            if not rule['enabled']:status='disabled_or_blocked'
            elif production_report and not production_report['ready'] and (rule['kind']=='stateful' or rule['rule_id'].startswith('os_sre.master_')):status='source_contract_not_ready'
            elif not rule['inventory_configured']:status='missing_asset_configuration'
            elif rule['kind']=='stateful':status='ready' if all(fields.get(n,{}).get('status')=='ready' for n in rule['required_metrics']) else 'missing_or_incompatible_input'
            elif rule['rule_id'].startswith('os_sre.platform_'):
                required=re.findall(r'\bn9e_[a-z_]+\b',rule['expression'] or '')
                status='ready' if not required or all({r.get('type') for r in metadata.get(n,[])}=={'counter'} for n in required) else 'platform_counter_not_collected'
            else:status='ready' if target_up else 'collector_target_not_observed'
            per_entity=[]
            if rule['kind']=='stateful':
                for entity in entities.values():
                    if set(entity['identity'])!=set(rule['identity_labels']):continue
                    missing=sorted(set(rule['required_metrics'])-set(entity['fields']))
                    duplicates=sorted(n for n in set(entity['fields']) if entity['fields'].count(n)>1 and n in rule['required_metrics'])
                    invalid=sorted(set(entity['invalid_fields'])&set(rule['required_metrics']))
                    per_entity.append({'identity':entity['identity'],'missing_fields':missing,'duplicate_fields':duplicates,'invalid_fields':invalid,'complete':not (missing or duplicates or invalid)})
            for item in per_entity:
                ident=item['identity'];deps=rule.get('inventory_dependencies',[]);asset_missing=False
                matches=lambda row:all(row.get(k)==v for k,v in ident.items())
                if any('link_expected' in dep for dep in deps):asset_missing=not any(matches(row) for row in profile.get('links',[]))
                elif any('pcie_' in dep for dep in deps):asset_missing=not any(matches(row) and all(row.get(k) is not None for k in ('pcie_gen','pcie_width','pcie_active_bytes_per_second')) for row in profile.get('gpus',[]))
                elif any('fabric_expected' in dep for dep in deps):asset_missing=not any(matches(row) and row.get('fabric_expected') is True for row in profile.get('gpus',[]))
                item['asset_configuration_missing']=asset_missing
                item['complete']=item['complete'] and not asset_missing
            rules[rule['rule_id']]={'status':status,'entity_coverage':per_entity}
        return {'checked_at':time.time(),'contract_profile':self.config['contract_profile'],'fields':fields,'rules':rules,
                'targets':target_up,'observed_entities':len(entities),'invalid_identity_samples':invalid_id,
                'production_contract':production_report,'has_device_data':bool(entities),'upstream':'read_only','requires_prometheus_recording_rules':False}


def normalize(rule,rows,query_time):
    values={};clocks={};stateful=rule['kind']=='stateful'
    for row in rows:
        labels=dict(row.get('metric',{}));labels.pop('__name__',None);kind=labels.pop('sre_result_kind',None)
        if set(labels)-set(IDENTITIES):raise SourceError('unexpected identity labels in normalized result')
        if not labels.get('job') or not labels.get('instance'):raise SourceError('missing collector identity')
        if any(not isinstance(v,str) or not v or len(v)>256 for v in labels.values()):raise SourceError('invalid identity value')
        if 'UUID' in labels and 'switch_id' in labels:raise SourceError('ambiguous hardware identity')
        if stateful and set(labels)!=set(rule['identity_labels']):raise SourceError('hardware identity schema mismatch')
        if stateful and kind not in ('value','clock'):raise SourceError('missing paired source clock marker')
        value=float(row['value'][1]);timestamp=float(row['value'][0])
        if not math.isfinite(value) or not math.isfinite(timestamp):raise SourceError('nonfinite query result')
        if abs(timestamp-query_time)>2:raise SourceError('query time mismatch')
        key=canonical(labels);target=clocks if kind=='clock' else values
        if key in target:raise SourceError('duplicate normalized identity')
        target[key]=(labels,value)
    result=[]
    for key,(identity,value) in values.items():
        if stateful:
            if value not in (0,1) or key not in clocks:raise SourceError('nonboolean or missing original source clock')
            stamp=clocks[key][1]
        else:value=1;stamp=query_time  # Native alert vectors can legitimately have value zero.
        result.append({'identity':identity,'value':value,'source_time':stamp})
    return result
