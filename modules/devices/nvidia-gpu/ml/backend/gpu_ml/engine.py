import concurrent.futures
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import threading
import time
import uuid
import numpy as np
from .models import GPUModel,ALGORITHMS,build_model
from .pipeline import build_pipeline,load_artifact,DetectionPipeline,capabilities_for,CalibratedMaxEnsemble
from .evaluation import summarize,validate_labels
from .settings import DATA,TEMPLATES,METRICS,SIMULATION,POLL,FRESHNESS
from .simulation import UUIDS,CLUSTER,healthy
from .model_backends.http import HttpModelBackend,RemoteModel
from .model_backends.training import TrainingCoordinator
from .model_backends.contracts import ScoreBatch,BackendUnsupported,BackendUnavailable,BackendProtocolError


class Engine:
    def __init__(self,store,source,model_backend=None):
        self.store=store;self.source=source;self.stop=threading.Event();self.last_poll=0
        self.error=None;self.models={};self.executor=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='training')
        self.futures={};self.lock=threading.RLock()
        (DATA/'models').mkdir(parents=True,exist_ok=True);(DATA/'snapshots').mkdir(parents=True,exist_ok=True)
        self.backend=model_backend or HttpModelBackend();self.training=TrainingCoordinator(self,self.backend)

    def seed(self):
        if not SIMULATION or os.environ.get('GPU_ML_LEGACY_BOOTSTRAP','false').lower()!='true':return
        for i,uid in enumerate(UUIDS):
            entity=CLUSTER+'|'+uid
            for template in ('thermal','relation','activity'):
                key='sim-'+str(i)+'-'+template
                if self.store.get('task',key):continue
                task={'name':f'{uid[-4:]} · {TEMPLATES[template]["name"]}','entity':entity,'template':template,
                      'algorithm':'ridge_iforest','enabled':True,'active_model':None,'scope':'simulated','sensitivity':1.,'created_at':time.time()}
                self.store.put('task',key,task)
                # Explicit simulation-only bootstrap; never presented as Prometheus history.
                ts=np.arange(0,2400,2,dtype=float)
                values=healthy(ts,i,97)
                rows=[{'t':float(t),'values':{k:float(v[n]) for k,v in values.items()}} for n,t in enumerate(ts)]
                self.train_now(key,rows,'simulation-bootstrap','ridge_iforest',publish=True)

    def start(self):
        self.seed()
        self.thread=threading.Thread(target=self.run,daemon=True,name='inference');self.thread.start()

    def load(self,version):
        if version not in self.models:
            record=self.store.get('model',version)
            if not record:raise ValueError('模型版本不存在')
            self.models[version]=RemoteModel(self.backend,record) if record.get('backend') else load_artifact(DATA/'models'/record['artifact'],record['sha256'])
        return self.models[version]

    def train_now(self,task_id,rows,provenance,algorithm,publish=False,job_id=None,config=None,labels=None):
        version=self.training.train_now(task_id,rows,provenance,algorithm,job_id,config,labels)
        if publish:self.publish(task_id,version,'system')
        return version

    def queue_training(self,task_id,algorithm,start,end,step=2,config=None,labels=None):
        task=self.store.get('task',task_id)
        if not task or task.get('deleted'):raise ValueError('任务不存在或已退役')
        build_pipeline(task['template'],algorithm,config)
        if not math.isfinite(start+end) or end<=start or end>time.time()+2:raise ValueError('训练时间范围无效')
        if step<2 or (end-start)/step>12000 or end-start>86400*31:raise ValueError('训练窗口或采样点数超过配额')
        scenario=TEMPLATES[task['template']].get('scenario')
        if scenario and scenario['profile']=='laboratory' and (not SIMULATION or task['scope']!='simulated'):raise ValueError('加速实验profile不能训练真实GPU')
        if scenario and end-start<scenario['minimum_history_seconds']:raise ValueError('场景参考历史不足：需要至少'+str(scenario['minimum_history_seconds'])+'秒；生产与实验profile不能混用')
        minimum=240 if TEMPLATES[task['template']].get('kind') in ('univariate','multivariate') else 180
        if (end-start)/step<minimum:raise ValueError(f'训练窗口至少需要{minimum}个有效源样本；建议覆盖完整正常负载周期')
        if any(j['task']==task_id and j['status'] in ('queued','running') for j in self.store.list('job')):
            raise ValueError('该任务已有训练或回放作业')
        return self.training.queue(task_id,algorithm,start,end,step,config,validate_labels(labels or [],start,end))

    def read_job_rows(self,job):
        task=self.store.get('task',job['task']);required=TEMPLATES[task['template']]['required']
        rows=self.source.history(task['entity'],job['start'],job['end'],job['step'],required)
        if not rows or rows[0]['t']-job['start']>max(15,job['step']*3) or job['end']-rows[-1]['t']>max(15,job['step']*3):
            raise ValueError('请求窗口缺少起止历史，不能静默缩短训练范围')
        if len(rows)<.8*((job['end']-job['start'])/job['step']):raise ValueError('有效样本覆盖率不足80%')
        before=len(rows)
        if task['scope']=='simulated':
            actions=sorted([a for a in self.store.audits() if a['action']=='simulation' and a['object_id']==task['entity'].split('|',1)[1]],key=lambda a:a['at'])
            intervals=[]
            for i,action in enumerate(actions):
                if action['details'].get('scenario') not in ('normal','idle','high_load'):
                    stop=actions[i+1]['at'] if i+1<len(actions) else time.time()
                    expiry=stop if action['details'].get('scenario') in ('thermal_aging','clock_aging') else min(stop,action['at']+90)
                    intervals.append((action['at']-4,expiry+4))
            rows=[r for r in rows if not any(a<=r['t']<=b for a,b in intervals)]
        job['excluded_known_fault_samples']=before-len(rows)
        return rows

    def publish(self,task_id,model_id,actor):
        with self.lock:
            task=self.store.get('task',task_id);record=self.store.get('model',model_id)
            if not task or not record or task.get('deleted'):raise ValueError('任务或模型不存在或任务已退役')
            if (record['entity'],record['template'],record['source_type'])!=(task['entity'],task['template'],task['scope']):
                raise ValueError('模型实体、模板或数据来源不兼容')
            if record['status'] not in ('validated','published'):raise ValueError('模型保留测试异常率超过默认10%自检门槛，需复核后重新训练')
            scenario=record.get('feature_schema',{}).get('scenario')
            if scenario and scenario['profile']=='laboratory' and (not SIMULATION or task['scope']!='simulated'):raise ValueError('加速实验制品不能发布到真实GPU')
            self.load(model_id)
            if record.get('backend'):
                reference=self.training.require_remote(record)
                deployment=self.backend.deploy(reference['model_ref'],reference['platform_id'])
                if deployment.get('status')!='ready':raise BackendUnavailable('模型部署尚未就绪，在线指针不切换')
                if deployment.get('model_ref')!=reference['model_ref'] or deployment.get('platform_id')!=reference['platform_id']:raise BackendProtocolError('部署回执身份不匹配')
                record['backend']={**reference,'deployment_ref':deployment['deployment_ref']}
                self.models.pop(model_id,None)
            old=task.get('active_model');task.update(active_model=model_id,previous_model=old)
            self.store.put('task',task_id,task,expected=task['revision'])
            record.update(status='published');self.store.put('model',model_id,record)
            # Existing active evidence is not cleared by a model version switch.
            self.store.audit(actor,'publish',task_id,{'old':old,'new':model_id})

    def score(self,model,rows,factor=1.):
        if isinstance(model,RemoteModel):return model.evaluate(rows,factor).points
        if isinstance(model,DetectionPipeline):return model.predict(rows,factor=factor)
        points=model.predict(rows);capabilities=capabilities_for(model)
        for point in points:
            point['threshold']*=factor;point['anomaly']=point['score']>point['threshold']
            point.update(capabilities=capabilities,reference_kind=capabilities['reference_kind'],
                         raw_score=None,raw_score_semantics='legacy artifact: raw components not persisted',calibrated_score=point['score'])
        return points

    def score_batch(self,model,rows,factor=1.):
        if isinstance(model,RemoteModel):return model.evaluate(rows,factor)
        points=self.score(model,rows,factor);quality='valid'
        if not points or points[-1]['t']!=rows[-1]['t']:
            quality=model.detector.latest_quality(model.preprocessor.transform(rows)) if hasattr(model,'detector') and hasattr(model.detector,'latest_quality') else 'warmup'
            if quality=='valid':quality='reference_window_incomplete'
        return ScoreBatch(points,quality)

    def reconfigure(self,model_id,calibration=None,factor=None):
        record=self.store.get('model',model_id)
        if not record:raise ValueError('模型不存在')
        if calibration is None and factor is None:raise ValueError('请提供校准配置或阈值倍率')
        reference=self.training.require_remote(record)
        return self.training.operation(model_id,'postprocess',{'model_ref':reference['model_ref'],'calibration':calibration,'factor':factor})

    def create_ensemble(self,task_id,member_ids,factor=1.):
        task=self.store.get('task',task_id)
        if not task or task.get('deleted'):raise ValueError('任务不存在或已退役')
        if not isinstance(member_ids,list) or not 2<=len(member_ids)<=3 or len(set(member_ids))!=len(member_ids):raise ValueError('集成需要2至3个不同成员版本')
        records=[self.store.get('model',key) for key in member_ids]
        for record in records:
            if not record or (record['entity'],record['template'],record['source_type'])!=(task['entity'],task['template'],task['scope']) or record['status'] not in ('validated','published'):raise ValueError('成员不兼容或未通过自检')
        refs=[self.training.require_remote(r) for r in records]
        if len({r['platform_id'] for r in refs})!=1 or len({r['dataset_sha256'] for r in records})!=1 or len({json.dumps(r['report'].get('partitions'),sort_keys=True) for r in records})!=1:raise ValueError('成员必须来自同一模型平台、快照和时间切分')
        return self.training.operation(member_ids[0],'ensemble',{'models':[r['model_ref'] for r in refs],'factor':factor})

    def queue_comparison(self,task_id,algorithms,start,end,step=2,config=None,labels=None):
        task=self.store.get('task',task_id)
        if not task or task.get('deleted'):raise ValueError('任务不存在或已退役')
        if not isinstance(algorithms,list) or not 2<=len(algorithms)<=3 or len(set(algorithms))!=len(algorithms):raise ValueError('请选择2至3个不同候选算法')
        for algorithm in algorithms:
            model=build_pipeline(task['template'],algorithm,config)
            if not isinstance(model,DetectionPipeline):raise ValueError('候选比较仅支持新流水线检测器')
        if not 2<=step or not 0<end-start<=86400*31 or (end-start)/step>12000 or (end-start)/step<240 or end>time.time()+2:raise ValueError('比较时间范围或步长无效')
        if any(j['task']==task_id and j['status'] in ('queued','running') for j in self.store.list('job')):raise ValueError('该任务已有活动作业')
        key=uuid.uuid4().hex
        self.store.put('job',key,{'task':task_id,'kind':'comparison','status':'queued','algorithms':algorithms,'start':start,'end':end,'step':step,'pipeline_config':config or {},'labels':validate_labels(labels or [],start,end),'created_at':time.time()})
        self.futures[key]=self.executor.submit(self._comparison,key)
        return self.store.get('job',key)

    def _comparison(self,key):
        job=self.store.get('job',key)
        try:
            job.update(status='running');self.store.put('job',key,job)
            rows=self.read_job_rows(job);candidates=[]
            for algorithm in job['algorithms']:
                try:
                    ident=self.train_now(job['task'],rows,'prometheus-history',algorithm,config=job['pipeline_config'],labels=job['labels'])
                    record=self.store.get('model',ident)
                    candidates.append({'algorithm':algorithm,'model':ident,'status':record['status'],'dataset_sha256':record['dataset_sha256'],'report':record['report']})
                except Exception as exc:candidates.append({'algorithm':algorithm,'status':'failed','error':str(exc)})
            self.store.put('comparison',key,{'task':job['task'],'candidates':candidates,'automatic_winner':None,
                'selection_policy':'manual review of selection partition; final test is not a selector; no label-free best-model claim',
                'created_at':time.time(),'online_model_unchanged':True})
            job.update(status='completed',candidate_count=len(candidates),completed_at=time.time())
        except Exception as exc:job.update(status='failed',error=str(exc),completed_at=time.time())
        self.store.put('job',key,job)

    def observation_is_fresh(self,stamp):
        return 0<=time.time()-stamp<=FRESHNESS

    def run(self):
        while not self.stop.is_set():
            try:
                control=self.store.get('system','inference') or {'enabled':True}
                if not control['enabled']:
                    self.stop.wait(POLL);continue
                entities=self.source.current()
                for entity in entities.values():self.store.put('entity',entity['id'],entity)
                for task in self.store.list('task'):
                    if not task['enabled']:continue
                    entity=entities.get(task['entity']);required=TEMPLATES[task['template']]['required']
                    if not entity:
                        self.store.apply(task['id'],quality='missing');continue
                    invalid=[entity['quality'].get(k,'missing') for k in required if entity['quality'].get(k)!='valid']
                    if invalid:
                        self.store.apply(task['id'],quality=','.join(sorted(set(invalid))));continue
                    if max(entity['times'][k] for k in required)-min(entity['times'][k] for k in required)>2:
                        self.store.apply(task['id'],quality='unaligned');continue
                    if task['template']=='activity' and entity['values']['job_running']!=1:
                        self.store.apply(task['id'],quality='context_inactive');continue
                    try:
                        row={'t':min(entity['times'][k] for k in required),'values':({k:entity['values'][k] for k in required} if TEMPLATES[task['template']].get('scenario') else entity['values'])}
                        if not self.observation_is_fresh(row['t']):
                            self.store.apply(task['id'],quality='inference_stale');continue
                        prior=self.store.get('state',task['id'])
                        if prior and prior.get('quality')=='valid' and prior.get('last_source',0)>=row['t']:continue
                        if task.get('shadow_model'):
                            try:
                                shadow_model=self.load(task['shadow_model'])
                                shadow_rows=self.source.history(task['entity'],row['t']-(shadow_model.window+3)*shadow_model.cadence,row['t'],shadow_model.cadence,required) if getattr(shadow_model,'window',0) else [row]
                                shadow_predictions=self.score(shadow_model,shadow_rows)
                                if shadow_predictions and shadow_predictions[-1]['t']==row['t']:
                                    shadow=shadow_predictions[-1];shadow['model']=task['shadow_model'];self.store.record_shadow(task['id'],shadow)
                            except Exception:logging.exception('Shadow scoring failed; primary remains independent')
                        if not task.get('active_model'):
                            self.store.apply(task['id'],quality='untrained');continue
                        model=self.load(task['active_model'])
                        rows=self.source.history(task['entity'],row['t']-(model.window+3)*model.cadence,row['t'],model.cadence,required) if getattr(model,'window',0) else [row]
                        batch=self.score_batch(model,rows,task.get('sensitivity',1.))
                        if batch.quality!='valid':
                            self.store.apply(task['id'],quality=batch.quality);continue
                        result=batch.points[-1]
                        if not self.observation_is_fresh(result['t']):
                            self.store.apply(task['id'],quality='inference_stale');continue
                        result['decision_config_revision']=task['revision'];result['effective_task_factor']=task.get('sensitivity',1.)
                        result['model']=task['active_model'];result['cadence_seconds']=getattr(model,'cadence',POLL);result['detector_kind']=TEMPLATES[task['template']].get('kind','legacy');self.store.apply(task['id'],result)
                    except Exception as exc:
                        self.store.apply(task['id'],quality='model_error');logging.exception('Model inference failed')
                self.last_poll=time.time();self.error=None
            except Exception as exc:
                self.error=type(exc).__name__
                for task in self.store.list('task'):
                    if task['enabled']:self.store.apply(task['id'],quality='query_error')
                # The loop is alive; valid normal evidence is still absent.
                self.last_poll=time.time()
                logging.warning('Input query failed: %s',self.error)
            self.stop.wait(POLL)

    def replay(self,task_id,model_id,start,end,step=2,labels=None):
        task=self.store.get('task',task_id);record=self.store.get('model',model_id)
        if not task or not record or task['template']!=record['template'] or task['entity']!=record['entity']:
            raise ValueError('回放模型与任务不兼容')
        if not 0<end-start<=86400*31 or step<2 or (end-start)/step>12000 or end>time.time()+2:raise ValueError('回放范围或步长无效')
        model=self.load(model_id)
        if getattr(model,'window',0) and step!=model.cadence:raise ValueError('回放步长必须与模型训练周期一致')
        annotations=validate_labels(labels or [],start,end)
        key=uuid.uuid4().hex
        self.store.put('job',key,{'task':task_id,'kind':'replay','status':'queued','model_id':model_id,'start':start,'end':end,'created_at':time.time()})
        def run():
            job=self.store.get('job',key)
            try:
                job.update(status='running');self.store.put('job',key,job)
                rows=self.source.history(task['entity'],start,end,step,TEMPLATES[task['template']]['required'])
                if task['template']=='activity':rows=[r for r in rows if r['values'].get('job_running')==1]
                if len(rows)<3:raise ValueError('回放有效样本不足')
                started=time.perf_counter();points=self.score(model,rows)
                evaluation=summarize(points,rows,annotations,getattr(model,'cadence',step),time.perf_counter()-started)
                # Replay outputs remain separate from online result/incident tables.
                self.store.put('replay',key,{'task':task_id,'model':model_id,'points':points,'evaluation':evaluation,'capabilities':capabilities_for(model),'labels':annotations,'created_at':time.time()})
                job.update(status='completed',point_count=len(points),anomaly_points=sum(p['anomaly'] for p in points),completed_at=time.time())
            except Exception as exc:job.update(status='failed',error=str(exc))
            self.store.put('job',key,job)
        self.futures[key]=self.executor.submit(run)
        return self.store.get('job',key)
