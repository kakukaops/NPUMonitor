"""Remote service connections and import of already-trained/deployed model references."""
import hashlib
import json
import math
import re
from pathlib import Path
import time
import uuid
from .http import HttpModelBackend
from .contracts import BackendProtocolError, BackendUnsupported
from ..settings import DATA, TEMPLATES, FRESHNESS, METRICS


class ModelServices:
    def __init__(self, engine):
        self.engine=engine;self.store=engine.store;self.default=engine.backend;self.cache={}
        self.secret_root=DATA/'model-service-secrets'

    def list(self):
        default_url=getattr(self.default,'url',None)
        return [{'id':self.default.backend_id,'name':'默认训练与模型服务',
                 'url':default_url,'location':'reference' if default_url=='http://model-platform:9470' else 'remote',
                 'readonly':True,'state':self.engine.training.status.get('state','not_checked'),
                 'platform_id':self.engine.training.status.get('platform_id')}]+self.store.list('model_service')

    def backend(self, backend_id):
        if backend_id==self.default.backend_id:return self.default
        record=self.store.get('model_service',backend_id)
        if not record:raise BackendUnsupported('该模型的服务未配置；请先恢复服务连接及凭据')
        if backend_id not in self.cache:
            self.cache[backend_id]=HttpModelBackend(record['url'],str(self.secret_root/backend_id),backend_id,timeout=record['timeout_seconds'])
        return self.cache[backend_id]

    def create(self, name, url, token, timeout=12):
        if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('请输入模型服务名称')
        if not isinstance(url,str) or len(url)>1024 or any(ord(c)<33 for c in url):raise ValueError('模型服务地址无效')
        if not isinstance(token,str) or not token.strip() or len(token)>4096 or any(c in token for c in '\r\n'):raise ValueError('请输入有效Bearer凭据')
        if isinstance(timeout,bool) or not isinstance(timeout,int) or not 1<=timeout<=60:raise ValueError('超时须为1至60秒整数')
        ident='service-'+uuid.uuid4().hex
        backend=HttpModelBackend(url,str(self.secret_root/ident),ident,timeout)
        self.secret_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=self.secret_root/ident;path.write_text(token.strip());path.chmod(0o600)
        try:
            info=backend.info()
            if not isinstance(info.get('platform_id'),str) or not info['platform_id']:raise BackendProtocolError('平台未声明稳定身份')
            record=self.store.put('model_service',ident,{'name':name.strip(),'url':backend.url,'location':'reference' if backend.url=='http://model-platform:9470' else 'remote',
                'timeout_seconds':timeout,'platform_id':info['platform_id'],'state':'available','checked_at':time.time()})
        except Exception:
            path.unlink(missing_ok=True);raise
        self.cache[ident]=backend
        return record

    def credentials(self, backend_id, token):
        record=self.store.get('model_service',backend_id)
        if not record or not re.fullmatch('service-[a-f0-9]{32}',backend_id):raise ValueError('仅支持已登记服务凭据更新')
        if not isinstance(token,str) or not token.strip() or len(token)>4096 or any(c in token for c in '\r\n'):raise ValueError('凭据无效')
        self.secret_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        temporary=self.secret_root/(backend_id+'.'+uuid.uuid4().hex+'.pending')
        temporary.write_text(token.strip());temporary.chmod(0o600)
        try:
            backend=HttpModelBackend(record['url'],str(temporary),backend_id,record['timeout_seconds'])
            info=backend.info()
            if info.get('platform_id')!=record['platform_id']:raise BackendProtocolError('平台身份变化，凭据未更新')
            temporary.replace(self.secret_root/backend_id)
        finally:temporary.unlink(missing_ok=True)
        record.update(state='available',checked_at=time.time());return self.store.put('model_service',backend_id,record)

    def check(self, backend_id):
        backend=self.backend(backend_id)
        try:
            info=backend.info()
            if not isinstance(info.get('platform_id'),str) or not info['platform_id']:raise BackendProtocolError('平台未声明稳定身份')
            record=self.store.get('model_service',backend_id)
            if record and record['platform_id']!=info.get('platform_id'):raise BackendProtocolError('平台身份已变化，不允许旧模型引用指向新平台')
            if record:record.update(state='available',checked_at=time.time());self.store.put('model_service',backend_id,record)
            return info
        except Exception:
            record=self.store.get('model_service',backend_id)
            if record:record.update(state='unavailable',checked_at=time.time());self.store.put('model_service',backend_id,record)
            raise

    def compatible(self, descriptor, task):
        if not isinstance(descriptor,dict):raise ValueError('模型描述必须为对象')
        caps=descriptor.get('capabilities',{})
        if not isinstance(caps,dict):raise ValueError('模型能力声明无效')
        if descriptor.get('report') is not None and not isinstance(descriptor['report'],dict):raise ValueError('模型报告必须为对象')
        if caps.get('online_update',False) is not False or caps.get('stateful',False) is not False:raise ValueError('当前远程调用仅支持冻结无状态模型；有状态/在线更新模型需单独协议')
        if descriptor.get('entity')!=task['entity'] or descriptor.get('source_type')!=task['scope'] or descriptor.get('feature_schema')!=TEMPLATES[task['template']]:
            raise ValueError('远程模型的设备、来源或输入契约不兼容当前任务')
        expected={k:{'metric_id':METRICS[k]['metric_id'],'unit':METRICS[k]['unit']} for k in TEMPLATES[task['template']]['required']}
        if descriptor.get('input_contract')!=expected:raise ValueError('远程模型缺少或不匹配指标语义/单位契约，请由平台或桥接补齐')
        if descriptor.get('status') not in ('validated','published'):raise ValueError('远程模型尚未通过其平台自检')
        if not isinstance(descriptor.get('model_ref'),str) or not descriptor['model_ref']:raise ValueError('远程模型引用无效')
        history=caps.get('history_samples');cadence=caps.get('cadence_seconds')
        if isinstance(history,bool) or not isinstance(history,int) or not 0<=history<=12000:raise ValueError('历史窗口声明无效')
        if isinstance(cadence,bool) or not isinstance(cadence,(int,float)) or not math.isfinite(cadence) or not 2<=cadence<=86400:raise ValueError('采样周期声明无效')
        if caps.get('reference_kind') not in ('none','causal_forecast','joint_reconstruction','conditional_baseline'):raise ValueError('参考曲线能力声明无效')

    def catalog(self, backend_id, task_id):
        info=self.check(backend_id);backend=self.backend(backend_id)
        if not callable(getattr(backend,'catalog',None)):raise BackendUnsupported('服务未提供模型目录，请通过适配桥接补齐或手动登记')
        response=backend.catalog()
        if response.get('platform_id')!=info['platform_id'] or not isinstance(response.get('models'),list) or len(response['models'])>5000:raise BackendProtocolError('远程模型目录契约无效')
        task=self.store.get('task',task_id)
        if not task or task.get('deleted'):raise ValueError('任务不存在或已退役')
        models=[]
        for candidate in response['models']:
            try:
                self.compatible(candidate,task)
                if candidate.get('platform_id')!=info['platform_id']:raise ValueError('平台身份不一致')
            except (ValueError,TypeError):continue
            models.append({k:v for k,v in candidate.items() if k in ('model_ref','deployment_ref','algorithm','created_at','training_window','capabilities','report','source_type')})
        return {'service_id':backend_id,'platform_id':info['platform_id'],'models':models,'excluded':len(response['models'])-len(models)}

    def register(self, backend_id, task_id, model_ref, deployment_ref=None):
        if not isinstance(model_ref,str) or not 1<=len(model_ref)<=200:raise ValueError('请输入远程模型引用')
        if deployment_ref is not None and (not isinstance(deployment_ref,str) or not 1<=len(deployment_ref)<=200):raise ValueError('部署引用无效')
        task=self.store.get('task',task_id)
        if not task or task.get('deleted'):raise ValueError('任务不存在或已退役')
        backend=self.backend(backend_id);info=self.check(backend_id)
        if not callable(getattr(backend,'describe',None)):raise BackendUnsupported('服务未提供模型描述，请通过桥接补齐输入/输出契约')
        descriptor=backend.describe(model_ref)
        if descriptor.get('platform_id')!=info['platform_id'] or descriptor.get('model_ref')!=model_ref:raise BackendProtocolError('远程模型描述身份不匹配')
        self.compatible(descriptor,task)
        selected=deployment_ref or descriptor.get('deployment_ref')
        reference={'backend_id':backend_id,'platform_id':info['platform_id'],'model_ref':model_ref,'contract_version':1}
        if selected:
            if not isinstance(selected,str) or not 1<=len(selected)<=200:raise ValueError('平台部署引用无效')
            if not callable(getattr(backend,'deployment',None)):raise BackendUnsupported('服务未提供已有部署查询接口')
            deployment=backend.deployment(selected)
            if deployment.get('platform_id')!=info['platform_id'] or deployment.get('model_ref')!=model_ref or deployment.get('deployment_ref')!=selected or deployment.get('status')!='ready':raise BackendProtocolError('已有部署未就绪或身份不匹配')
            reference['deployment_ref']=selected
        # Verify against fresh, real source rows. Never create evidence or change the online pointer.
        entity=self.store.get('entity',task['entity']);required=TEMPLATES[task['template']]['required']
        if not entity or any(entity['quality'].get(k)!='valid' for k in required):raise ValueError('当前输入不可用，不能完成试评分')
        end=min(entity['times'][k] for k in required)
        if not 0<=time.time()-end<=FRESHNESS:raise ValueError('当前输入已陈旧，不能完成试评分')
        caps=descriptor['capabilities'];history=caps['history_samples'];cadence=caps['cadence_seconds']
        rows=self.engine.source.history(task['entity'],end-(history+3)*cadence,end,cadence,required) if history else [{'t':end,'values':{k:entity['values'][k] for k in required}}]
        if not rows or rows[-1]['t']!=end:raise ValueError('试评分缺少最新连续历史')
        batch=backend.predict(reference,rows,1.)
        if not 0<=time.time()-end<=FRESHNESS:raise ValueError('试评分耗时导致输入陈旧，请重试')
        if batch.quality!='valid' or not batch.points or batch.points[-1]['t']!=end:raise ValueError('远程试评分尚不能覆盖最新样本')
        reference_kind=caps['reference_kind']
        if reference_kind!='none' and any(k not in batch.points[-1].get('expected',{}) for k in TEMPLATES[task['template']]['targets']):raise BackendProtocolError('模型声明有参考曲线但未返回目标参考值')
        ident='import-'+hashlib.sha256(json.dumps([task_id,backend_id,info['platform_id'],model_ref,selected],sort_keys=True).encode()).hexdigest()[:32]
        old=self.store.get('model',ident)
        if old:return old
        service=next(s for s in self.list() if s['id']==backend_id)
        return self.store.put('model',ident,{'task':task_id,'entity':task['entity'],'template':task['template'],'algorithm':descriptor.get('algorithm','remote'),
            'input_contract':descriptor['input_contract'],'feature_schema':descriptor['feature_schema'],'source_type':task['scope'],'source':'remote-registration',
            'training_origin':descriptor.get('source','platform-declared'),'training_window':descriptor.get('training_window'),
            'status':'validated','backend':reference,'external_registration':True,'execution_location':service['location'],'service_name':service['name'],
            'report':descriptor.get('report') or {},'capabilities':caps,'pipeline':descriptor.get('pipeline') or {},
            'created_at':time.time(),'remote_created_at':descriptor.get('created_at'),
            'connection_validation':{'passed':True,'checked_at':time.time(),'sample_time':end,'scored_points':len(batch.points),'meaning':'connectivity/input/output validation; not detection accuracy'}})
