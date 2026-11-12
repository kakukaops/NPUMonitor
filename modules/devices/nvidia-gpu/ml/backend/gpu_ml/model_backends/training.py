"""Monitor-side data export and remote job coordination, never model.fit()."""
import copy
import concurrent.futures,hashlib,json,math,threading,time,uuid
from pathlib import Path
from .contracts import canonical_rows,dataset_hash,BackendError,BackendUnavailable,BackendProtocolError,BackendUnsupported
from ..settings import DATA,TEMPLATES

class Deferred(Exception):
    def __init__(self,job_id):self.job_id=job_id;super().__init__('external job pending')
class TrainingCoordinator:
    def __init__(self,engine,backend):
        self.engine=engine;self.store=engine.store;self.backend=backend;self.stop=engine.stop
        self.executor=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='model-api-coordinator');self.futures={}
        self.status={'backend_id':backend.backend_id,'state':'not_checked','operations':[]}
        self.recovery=threading.Thread(target=self.recover,daemon=True,name='model-job-reconciliation');self.recovery.start()
    def recover(self):
        while not self.stop.is_set():
            try:
                info=self.backend.info();self.status.update(state='available',platform_id=info['platform_id'],operations=info.get('operations',[]),last_checked=time.time())
                for job in self.store.list('job'):
                    if job.get('backend_id') and job['backend_id']!=self.backend.backend_id:continue
                    if job['status']!='pending_sync' or not job.get('backend_request_id'):continue
                    if job.get('cancel_requested'):self.backend.cancel(job['backend_request_id'])
                    try:
                        remote=self.backend.job(job['backend_request_id'])
                        if remote['status'] in ('completed','failed','cancelled'):self.complete(job,remote)
                    except (BackendProtocolError,BackendUnsupported) as exc:
                        job.update(status='failed',error=str(exc),completed_at=time.time());self.store.put('job',job['id'],job)
            except BackendError:self.status.update(state='unavailable',last_checked=time.time())
            except Exception:self.status.update(state='reconciliation_error',last_checked=time.time())
            self.stop.wait(3)
    def queue(self,task_id,algorithm,start,end,step,config,labels):
        ident=uuid.uuid4().hex
        job={'task':task_id,'kind':'training','status':'queued','algorithm':algorithm,'start':start,'end':end,'step':step,'pipeline_config':config or {},'labels':labels,
             'created_at':time.time(),'cancel_requested':False,'backend_id':self.backend.backend_id}
        self.store.put('job',ident,job);self.futures[ident]=self.executor.submit(self.run,ident)
        return self.store.get('job',ident)
    def run(self,ident):
        job=self.store.get('job',ident)
        try:
            if job['cancel_requested']:raise ValueError('训练已取消')
            job.update(status='running');self.store.put('job',ident,job)
            rows=self.engine.read_job_rows(job)
            current=self.store.get('job',ident);current['excluded_known_fault_samples']=job.get('excluded_known_fault_samples',0);self.store.put('job',ident,current)
            if current.get('cancel_requested'):raise ValueError('训练已取消')
            version=self.train_now(job['task'],rows,'prometheus-history',job['algorithm'],ident,job.get('pipeline_config'),job.get('labels'))
            current=self.store.get('job',ident)
            if current['status']!='cancelled':current.update(status='completed',model_id=version,completed_at=time.time());self.store.put('job',ident,current)
        except Deferred:pass
        except Exception as exc:
            current=self.store.get('job',ident);current.update(status='cancelled' if current.get('cancel_requested') else 'failed',error=str(exc),completed_at=time.time());self.store.put('job',ident,current)
    def prepare(self,task_id,rows,provenance,algorithm,job_id=None,config=None,labels=None):
        task=self.store.get('task',task_id)
        if not task:raise ValueError('检测任务不存在')
        version=uuid.uuid4().hex;payload=canonical_rows(rows);(DATA/'snapshots').mkdir(parents=True,exist_ok=True)
        (DATA/'snapshots'/f'{version}.json').write_bytes(payload)
        spec={'template':task['template'],'algorithm':algorithm,'feature_schema':copy.deepcopy(TEMPLATES[task['template']]),
              'source_type':task['scope'],'entity':task['entity'],'pipeline':config or {},'labels':labels or [],
              'source_window':{'start':rows[0]['t'],'end':rows[-1]['t']+1}}
        ident=job_id or uuid.uuid4().hex;job=self.store.get('job',ident) or {'id':ident,'task':task_id,'kind':'training','status':'running','created_at':time.time(),'cancel_requested':False}
        job.update(model_version=version,backend_request_id=ident,backend_id=self.backend.backend_id,dataset_sha256=hashlib.sha256(payload).hexdigest(),
                   training_spec=spec,snapshot=f'{version}.json',provenance=provenance,algorithm=algorithm)
        self.store.put('job',ident,job)
        return job,{'training_spec':spec,'dataset':{'sha256':job['dataset_sha256'],'rows':rows}}
    def await_result(self,job,operation,payload):
        ident=job['backend_request_id']
        try:
            remote=self.backend.submit(ident,operation,payload)
            current=self.store.get('job',job['id']);current['backend_platform_id']=remote['platform_id'];self.store.put('job',job['id'],current)
            while not self.stop.is_set():
                if self.store.get('job',job['id']).get('cancel_requested'):self.backend.cancel(ident)
                remote=self.backend.job(ident)
                if remote['status'] in ('completed','failed','cancelled'):
                    record=self.complete(self.store.get('job',job['id']),remote)
                    if record:return record
                    raise ValueError(remote.get('error','模型任务取消或执行失败'))
                self.stop.wait(.5)
        except BackendUnavailable:
            current=self.store.get('job',job['id']);current.update(status='pending_sync',error='模型平台暂不可用，任务状态待确认');self.store.put('job',job['id'],current);raise Deferred(job['id'])
        except BackendError as exc:
            current=self.store.get('job',job['id']);current.update(status='failed',error=str(exc),completed_at=time.time());self.store.put('job',job['id'],current);raise
        except Exception:
            current=self.store.get('job',job['id'])
            if current['status'] not in ('completed','failed','cancelled'):
                current.update(status='failed',error='模型平台响应不满足任务契约',completed_at=time.time());self.store.put('job',job['id'],current)
                raise BackendProtocolError('模型平台响应不满足任务契约') from None
            raise
        current=self.store.get('job',job['id']);current.update(status='pending_sync',error='监控进程停止，外部训练任务保留');self.store.put('job',job['id'],current);raise Deferred(job['id'])
    def complete(self,job,remote):
        if job.get('cancel_requested'):
            job.update(status='cancelled',error='取消请求已生效，未注册或发布模型',completed_at=time.time());self.store.put('job',job['id'],job);return None
        if remote['status']!='completed':
            job.update(status=remote['status'],error=remote.get('error','模型任务未完成'),completed_at=time.time());self.store.put('job',job['id'],job);return None
        if job.get('backend_id')!=self.backend.backend_id or (job.get('backend_platform_id') and job['backend_platform_id']!=remote.get('platform_id')):raise BackendProtocolError('训练任务对应的模型平台身份已变化')
        result=remote['result'];spec=job['training_spec'];caps=result.get('capabilities',{});rate=result.get('report',{}).get('held_out_point_alert_rate')
        if result.get('platform_id')!=remote.get('platform_id') or result.get('dataset_sha256')!=job['dataset_sha256'] or result.get('feature_schema')!=spec['feature_schema'] or result.get('source_type')!=spec['source_type']:
            raise BackendProtocolError('训练结果身份、数据摘要或输入schema不匹配')
        if not isinstance(result.get('model_ref'),str) or not result['model_ref'] or len(result['model_ref'])>200:raise BackendProtocolError('模型版本引用无效')
        if not isinstance(rate,(int,float)) or isinstance(rate,bool) or not math.isfinite(rate) or not 0<=rate<=1:raise BackendProtocolError('模型验证报告无效')
        if isinstance(caps.get('history_samples'),bool) or not isinstance(caps.get('history_samples'),int) or not 0<=caps['history_samples']<=12000 or not isinstance(caps.get('cadence_seconds'),(int,float)) or not 2<=caps['cadence_seconds']<=86400:raise BackendProtocolError('模型能力/采样周期无效')
        ident=job['model_version'];existing=self.store.get('model',ident)
        if existing:
            if existing.get('backend',{}).get('model_ref')!=result['model_ref']:raise BackendProtocolError('同一训练任务返回不同模型版本')
            job.update(status='completed',model_id=ident,completed_at=time.time(),error=None);self.store.put('job',job['id'],job);return existing
        backend={'backend_id':self.backend.backend_id,'platform_id':remote['platform_id'],'model_ref':result['model_ref'],'contract_version':1}
        record={'task':job['task'],'entity':spec['entity'],'template':spec['template'],'algorithm':result['algorithm'],'backend':backend,
                'snapshot':job['snapshot'],'dataset_sha256':job['dataset_sha256'],'source':job['provenance'],'source_type':spec['source_type'],
                'status':'validated' if rate<=.1 and result.get('status')=='validated' else 'review_required',
                'report':result['report'],'capabilities':caps,'feature_schema':result['feature_schema'],'pipeline':result.get('pipeline',{}),'evaluation_labels':spec.get('labels',[]),'created_at':time.time()}
        if job.get('parent_model'):record['parent_model']=job['parent_model']
        self.store.put('model',ident,record);job.update(status='completed',model_id=ident,completed_at=time.time(),error=None);self.store.put('job',job['id'],job)
        return self.store.get('model',ident)
    def train_now(self,task_id,rows,provenance,algorithm,job_id=None,config=None,labels=None):
        job,payload=self.prepare(task_id,rows,provenance,algorithm,job_id,config,labels)
        return self.await_result(job,'fit',payload)['id']
    def require_remote(self,record):
        reference=record.get('backend',{})
        if reference.get('backend_id')!=self.backend.backend_id:raise BackendUnsupported('旧本地或其他后端模型请先在目标平台重新训练；不上传任意pickle')
        return reference
    def operation(self,parent_id,operation,payload):
        parent=self.store.get('model',parent_id)
        if not parent:raise ValueError('父模型不存在')
        reference=self.require_remote(parent);path=DATA/'snapshots'/parent['snapshot'];raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=parent['dataset_sha256']:raise ValueError('训练快照摘要不匹配')
        ident=uuid.uuid4().hex;version=uuid.uuid4().hex
        (DATA/'snapshots'/f'{version}.json').write_bytes(raw)
        spec={'entity':parent['entity'],'template':parent['template'],'feature_schema':parent['feature_schema'],'source_type':parent['source_type'],'labels':parent.get('evaluation_labels',[])}
        job={'id':ident,'task':parent['task'],'kind':'model_operation','operation':operation,'status':'running','created_at':time.time(),'cancel_requested':False,
             'model_version':version,'backend_request_id':ident,'backend_id':self.backend.backend_id,'dataset_sha256':parent['dataset_sha256'],'training_spec':spec,
             'snapshot':f'{version}.json','provenance':parent['source'],'parent_model':parent_id}
        self.store.put('job',ident,job)
        return self.await_result(job,operation,{'platform_id':reference['platform_id'],**payload})
    def cancel(self,ident):
        job=self.store.get('job',ident)
        if not job or job.get('kind')!='training' or job['status'] not in ('queued','running','pending_sync'):raise ValueError('作业无法取消')
        job['cancel_requested']=True;self.store.put('job',ident,job)
        future=self.futures.get(ident)
        if future and future.cancel():job.update(status='cancelled');self.store.put('job',ident,job)
        if job.get('backend_request_id'):
            try:self.backend.cancel(job['backend_request_id'])
            except BackendError:pass
        return self.store.get('job',ident)
    def close(self):self.executor.shutdown(wait=True,cancel_futures=True);self.recovery.join(timeout=2)
