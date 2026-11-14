"""Versioned, owned Nightingale projection with preflight conflicts and compensating rollback."""
import copy,json,time,uuid
from pathlib import Path
from urllib.request import Request,ProxyHandler,build_opener
from .bundle import digest,url
from .store import Conflict
from .source import NoRedirect

OWNER='npumonitor-os-sre'

class API:
    def __init__(self,config):self.config=config;self.base=url(config['url'])+'/api/n9e';self.opener=build_opener(ProxyHandler({}),NoRedirect())
    def call(self,method,path,body=None):
        token=Path(self.config['token_file']).read_text().strip()
        if not token:raise ValueError('Nightingale credential missing')
        req=Request(self.base+path,data=None if body is None else json.dumps(body).encode(),method=method,headers={'X-User-Token':token,'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=15) as response:raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:raise RuntimeError('Nightingale response quota exceeded')
            value=json.loads(raw)
            if isinstance(value,dict):
                if value.get('err') or value.get('error'):raise RuntimeError('Nightingale rejected operation')
                return value.get('dat',value.get('data',value))
            return value
        except Exception as exc:raise RuntimeError('Nightingale API failed: '+type(exc).__name__) from None


def one(rows,name):
    values=[r for r in rows or [] if r.get('name')==name]
    if len(values)>1:raise Conflict('duplicate object name')
    return values[0] if values else None


def projection(rule):
    fields=('name','group_id','cate','prod','prom_eval_interval','prom_for_duration','disabled','notify_version','notify_rule_ids','notify_recovered','notify_repeat_step','notify_max_number','recover_duration','note')
    out={k:copy.deepcopy(rule.get(k)) for k in fields};out['append_tags']=sorted(rule.get('append_tags') or [])
    out['datasource_queries']=rule.get('datasource_queries');out['rule_config']=rule.get('rule_config')
    # Only our managed annotation keys participate; server-generated audit fields do not.
    ann=rule.get('annotations') or {};out['annotations']={k:ann.get(k) for k in ('managed_by','deployment_id','sre_rule_id','bundle_sha')}
    return out

class Sync:
    def __init__(self,store,api=None):
        self.store=store;self.bundle,self.generation=store.current();self.config=self.bundle['config']['nightingale'];self.api=api or API(self.config)
        self.deployment=self.bundle['config']['deployment_id'];self.group=int(self.config['group_id']);self.notify=int(self.config['notify_rule_id'])
    def sources(self):return self.api.call('POST','/datasource/list',{'plugin_type':'prometheus'})
    def source_name(self):return 'NPUMonitor OS SRE '+self.deployment
    def ensure_source(self,apply):
        existing=one(self.sources(),self.source_name());gateway=url(self.config['gateway_url'])
        if existing:
            if existing.get('http',{}).get('url')!=gateway or existing.get('description')!=OWNER+':'+self.deployment:raise Conflict('datasource collision or endpoint change; refusing overwrite')
            if not existing.get('auth',{}).get('basic_auth'):raise Conflict('managed datasource authentication changed')
            return existing['id']
        if not apply:return None
        password=Path(self.bundle['config']['gateway']['viewer_token_file']).read_text().strip()
        self.api.call('POST','/datasource/upsert',{'name':self.source_name(),'identifier':'npumonitor-sre-'+self.deployment,
            'plugin_type':'prometheus','plugin_type_name':'Prometheus','category':'timeseries','status':'enabled','cluster_name':'default',
            'settings':{'prometheus_cluster_name':'default'},'http':{'url':gateway,'timeout':10000,'dial_timeout':3000},
            'auth':{'basic_auth':True,'basic_auth_user':'monitor','basic_auth_password':password},'description':OWNER+':'+self.deployment})
        return one(self.sources(),self.source_name())['id']
    def desired(self,ds):
        result=[]
        specs=list(self.bundle['rules'])
        if self.config.get('include_gateway_health_rule',True):specs.append({'rule_id':'gateway_health','title':'规则执行组件健康','severity':1,'enabled':True})
        for r in specs:
            ident=r['rule_id'];expression='sre_gateway_unhealthy' if ident=='gateway_health' else 'sre_rule_active{sre_rule_id="'+ident+'"} == 1'
            result.append({'name':'NPUMonitor '+self.deployment+' '+r['title'],'group_id':self.group,'cate':'prometheus','prod':'metric',
                'datasource_queries':[{'match_type':0,'op':'in','values':[ds]}],
                'rule_config':{'queries':[{'prom_ql':expression,'severity':r['severity'],'recover_config':{'judge_type':0}}]},
                'prom_eval_interval':int(self.config.get('eval_interval_seconds',30)),'prom_for_duration':0,'disabled':int(not r['enabled']),
                'notify_version':1,'notify_rule_ids':[self.notify],'notify_recovered':1,'notify_repeat_step':int(self.config.get('repeat_seconds',3600)),
                'notify_max_number':3,'recover_duration':0,'note':'设备证据由持久状态组件判定；退出可能是有效解除或管理关闭，不等于硬件修复。请关联运行时状态与审计。',
                'append_tags':['managed_by='+OWNER,'deployment='+self.deployment,'sre_rule_id='+ident],
                'annotations':{'managed_by':OWNER,'deployment_id':self.deployment,'sre_rule_id':ident,'bundle_sha':self.bundle['sha256']}})
        return result
    def current(self):return self.api.call('GET',f'/busi-group/{self.group}/alert-rules')
    def plan(self):
        ds=self.ensure_source(False);rows=self.current();result=[]
        for desired in self.desired(ds):
            ident=desired['annotations']['sre_rule_id'];old=one(rows,desired['name'])
            matches=[r for r in rows if (r.get('annotations') or {}).get('deployment_id')==self.deployment and (r.get('annotations') or {}).get('sre_rule_id')==ident]
            if len(matches)>1:raise Conflict('duplicate managed identity')
            old=matches[0] if matches else old
            saved=self.store.get_projection('rule:'+ident)
            if old:
                a=old.get('annotations') or {}
                if a.get('managed_by')!=OWNER or a.get('deployment_id')!=self.deployment or not saved:raise Conflict('unowned or unjournaled object; explicit recovery required')
                if saved['remote_hash']!=digest(projection(old)):raise Conflict('managed rule was externally edited; refusing overwrite')
            action='create' if not old else 'unchanged' if ds is not None and saved.get('desired_hash')==digest(projection(desired)) else 'update'
            result.append({'rule_id':ident,'action':action,'old':old,'desired':desired})
        return {'datasource_exists':ds is not None,'generation':self.generation,'bundle_sha':self.bundle['sha256'],'items':result}
    def apply(self):
        plan=self.plan()  # All rule conflicts are checked before the first write.
        ds=self.ensure_source(True);wanted={r['annotations']['sre_rule_id']:r for r in self.desired(ds)}
        ident=uuid.uuid4().hex;op={'id':ident,'status':'applying','generation':self.generation,'before':{},'after':{},'desired':{},'pending':None}
        self.store.put_operation(ident,op)
        try:
            for item in plan['items']:
                rid=item['rule_id'];desired=wanted[rid];old=item['old']
                if self.store.current()[1]!=self.generation:raise Conflict('runtime release changed during projection')
                op['before'][rid]=old;op['desired'][rid]=desired;op['pending']=rid;self.store.put_operation(ident,op)
                desired['annotations']['sync_operation']=ident
                if old:
                    current=next(r for r in self.current() if r['id']==old['id'])
                    if digest(projection(current))!=digest(projection(old)):raise Conflict('concurrent external edit detected')
                    op['before'][rid]=old
                    if item['action']!='unchanged':self.api.call('PUT',f'/busi-group/{self.group}/alert-rule/{old["id"]}',dict(old,**desired))
                else:
                    op['before'][rid]=None
                    self.api.call('POST',f'/busi-group/{self.group}/alert-rules',[desired])
                reread=one(self.current(),desired['name'])
                if reread is None:raise RuntimeError('rule reread failed')
                op['after'][rid]=reread;op['pending']=None
                self.store.put_projection('rule:'+rid,{'remote_id':reread['id'],'remote_hash':digest(projection(reread)),'operation':ident,'desired_hash':digest(projection(desired))})
                self.store.put_operation(ident,op)
            op['status']='applied';self.store.put_operation(ident,op)
            return {'operation':ident,'status':'applied','rules':len(op['after']),'changed':sum(i['action']!='unchanged' for i in plan['items'])}
        except Exception:
            op['status']='failed';self.store.put_operation(ident,op)
            try:self.recover(ident)
            except Exception:
                op=self.store.get_operation(ident);op['status']='rollback_incomplete';self.store.put_operation(ident,op)
            raise
    def recover(self,operation):
        """Resolve a journaled uncertain write, then compensate; never adopt drift."""
        op=self.store.get_operation(operation)
        if not op or op['status'] not in ('applying','failed','rollback_incomplete'):
            raise Conflict('operation is not recoverable')
        rows=self.current();pending=op.get('pending')
        if pending:
            desired=op['desired'][pending];before=op['before'][pending]
            actual=one(rows,desired['name'])
            if actual is None and before is None:pass  # Request did not create an object.
            elif before and actual and digest(projection(actual))==digest(projection(before)):pass
            elif actual and (actual.get('annotations') or {}).get('sync_operation')==operation and digest(projection(actual))==digest(projection(desired)):
                op['after'][pending]=actual
            else:raise Conflict('uncertain write cannot be verified; refusing to overwrite remote object')
            op['pending']=None
        op['status']='failed';self.store.put_operation(operation,op)
        return self.rollback(operation,compensating=True)

    def rollback(self,operation,compensating=False):
        op=self.store.get_operation(operation)
        if not op or op['status'] not in ('applied','failed'):raise Conflict('operation is not rollbackable')
        current={r['id']:r for r in self.current()}
        for rid,after in op['after'].items():
            actual=current.get(after['id'])
            before=op['before'][rid]
            restored=before if before else dict(after,disabled=1,note='Administrative rollback of newly created rule; not hardware recovery')
            if actual is None or digest(projection(actual)) not in (digest(projection(after)),digest(projection(restored))):raise Conflict('rollback conflicts with subsequent modification')
        for rid,after in reversed(list(op['after'].items())):
            before=op['before'][rid]
            restored=before if before else dict(after,disabled=1,note='Administrative rollback of newly created rule; not hardware recovery')
            self.api.call('PUT',f'/busi-group/{self.group}/alert-rule/{after["id"]}',restored)
            actual=next(r for r in self.current() if r['id']==after['id'])
            self.store.put_projection('rule:'+rid,{'remote_id':actual['id'],'remote_hash':digest(projection(actual)),'operation':operation})
        op['status']='compensated' if compensating else 'rolled_back';self.store.put_operation(operation,op)
        return {'operation':operation,'status':op['status'],'rules':len(op['after'])}

    def rotate_source_auth(self):
        source=one(self.sources(),self.source_name())
        if not source or source.get('description')!=OWNER+':'+self.deployment or source.get('http',{}).get('url')!=url(self.config['gateway_url']):
            raise Conflict('datasource ownership/endpoint mismatch')
        desired={k:source[k] for k in ('id','name','identifier','plugin_type','plugin_type_name','category','status','cluster_name','settings','http','description') if k in source}
        desired['auth']={'basic_auth':True,'basic_auth_user':'monitor','basic_auth_password':Path(self.bundle['config']['gateway']['viewer_token_file']).read_text().strip()}
        self.api.call('POST','/datasource/upsert',desired)
        return {'source_auth_rotated':True,'source_id':source['id']}
