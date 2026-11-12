"""Local training implementation. No Prometheus, Nightingale or monitor database access."""
from contextlib import contextmanager
import concurrent.futures,hashlib,json,os,re,sqlite3,threading,time,uuid
from pathlib import Path
from .plugins import load_plugins
load_plugins()
from gpu_ml_runtime.pipeline import build_pipeline,load_artifact,DetectionPipeline,capabilities_for,CalibratedMaxEnsemble
from model_contracts import canonical_rows,dataset_hash
from gpu_ml_runtime.evaluation import validate_labels

class Conflict(ValueError):pass
class Registry:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
        for part in ('models','datasets','requests'): (self.root/part).mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS objects(kind TEXT,id TEXT,payload TEXT,PRIMARY KEY(kind,id));')
            row=db.execute("SELECT payload FROM objects WHERE kind='meta' AND id='platform'").fetchone()
            self.platform_id=json.loads(row[0])['platform_id'] if row else uuid.uuid4().hex
            if not row:db.execute('INSERT INTO objects VALUES(?,?,?)',('meta','platform',json.dumps({'platform_id':self.platform_id})))
        for job in self.list('job'):
            if job['status'] in ('queued','running'):
                job.update(status='failed',error='模型服务重启中断计算；已部署版本保留');self.put('job',job['request_id'],job)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.root/'registry.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
        try:
            with db:yield db
        finally:db.close()
    def get(self,kind,key):
        with self.lock,self.connect() as db:
            row=db.execute('SELECT payload FROM objects WHERE kind=? AND id=?',(kind,key)).fetchone();return json.loads(row[0]) if row else None
    def put(self,kind,key,value):
        with self.lock,self.connect() as db:db.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?)',(kind,key,json.dumps(value,allow_nan=False)))
        return value
    def list(self,kind):
        with self.lock,self.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM objects WHERE kind=?',(kind,))]

class Runtime:
    def __init__(self,root,allow_laboratory=False):
        self.registry=Registry(root);self.root=self.registry.root;self.allow_laboratory=allow_laboratory
        self.executor=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='independent-trainer');self.cache={};self.cache_lock=threading.RLock()
    def envelope(self,**value):return {'contract_version':1,'platform_id':self.registry.platform_id,**value}
    def info(self):return self.envelope(operations=['fit','postprocess','ensemble'],deployment=True,prediction=True,storage='independent-volume',online_update=False)
    def submit(self,body):
        ident=body.get('request_id','');operation=body.get('operation')
        if body.get('contract_version')!=1 or not isinstance(ident,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,100}',ident):raise ValueError('任务契约或幂等键无效')
        if operation not in ('fit','postprocess','ensemble'):raise ValueError('未知模型操作')
        if operation!='fit' and body.get('platform_id')!=self.registry.platform_id:raise Conflict('平台身份不匹配')
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,allow_nan=False).encode()).hexdigest()
        with self.registry.lock:
            old=self.registry.get('job',ident)
            if old:
                if old['input_sha256']!=digest:raise Conflict('同一幂等键的输入不能改变')
                return self.envelope(**old)
            if sum(j['status'] in ('queued','running') for j in self.registry.list('job'))>=100:raise Conflict('模型任务队列已满')
            (self.root/'requests'/f'{ident}.json').write_text(json.dumps(body,allow_nan=False))
            job={'request_id':ident,'operation':operation,'status':'queued','created_at':time.time(),'input_sha256':digest,'cancel_requested':False}
            self.registry.put('job',ident,job);self.executor.submit(self.execute,ident)
        return self.envelope(**job)
    def job(self,ident):
        value=self.registry.get('job',ident)
        if not value:raise KeyError('模型任务不存在')
        return self.envelope(**value)
    def cancel(self,ident):
        with self.registry.lock:
            job=self.registry.get('job',ident)
            if not job:raise KeyError('模型任务不存在')
            if job['status'] in ('queued','running'):job['cancel_requested']=True;self.registry.put('job',ident,job)
        return self.envelope(**job)
    def load(self,ident):
        record=self.registry.get('model',ident)
        if not record:raise KeyError('模型不存在')
        with self.cache_lock:
            if ident not in self.cache:self.cache[ident]=load_artifact(self.root/'models'/record['artifact'],record['artifact_sha256'])
            return self.cache[ident],record
    def check_scope(self,spec,scope):
        if spec.get('scenario',{}).get('profile')=='laboratory' and (not self.allow_laboratory or scope!='simulated'):raise ValueError('实验模型不能用于真实数据')
    def execute(self,ident):
        with self.registry.lock:
            job=self.registry.get('job',ident)
            if job['cancel_requested']:
                job.update(status='cancelled');self.registry.put('job',ident,job);return
            job.update(status='running');self.registry.put('job',ident,job)
        try:
            body=json.loads((self.root/'requests'/f'{ident}.json').read_text());op=body['operation'];labels=[]
            if op=='fit':
                spec=body['training_spec'];rows=body['dataset']['rows']
                if not isinstance(rows,list) or not 180<=len(rows)<=12000:raise ValueError('训练样本数量超出契约')
                digest=dataset_hash(rows)
                if digest!=body['dataset']['sha256']:raise ValueError('训练数据摘要不匹配')
                self.check_scope(spec['feature_schema'],spec['source_type'])
                model=build_pipeline(spec['template'],spec['algorithm'],spec.get('pipeline'),spec=spec['feature_schema'])
                annotation=spec.get('labels',[]);window=spec.get('source_window',{})
                low=min([rows[0]['t'],window.get('start',rows[0]['t'])]+[l['start'] for l in annotation]);high=max([rows[-1]['t']+1,window.get('end',rows[-1]['t']+1)]+[l['end'] for l in annotation])
                labels=validate_labels(annotation,low,high)
                report=model.fit(rows,labels) if isinstance(model,DetectionPipeline) else model.fit(rows)
                scope=spec['source_type'];feature_schema=model.spec
            elif op=='postprocess':
                parent,record=self.load(body['model_ref'])
                if not isinstance(parent,DetectionPipeline):raise ValueError('该制品不支持独立后处理')
                rows=json.loads((self.root/'datasets'/f"{record['dataset_sha256']}.json").read_text());digest=record['dataset_sha256']
                model=parent.reconfigure(rows,body.get('calibration'),body.get('factor'));labels=record.get('evaluation_labels',[])
                report=model.evaluate_partitions(rows,labels);report.update(detector_retrained=False,preprocessor_refitted=False);model.report=report
                scope=record['source_type'];feature_schema=record['feature_schema']
            else:
                ids=body['models']
                if not isinstance(ids,list) or not 2<=len(ids)<=3 or len(set(ids))!=len(ids):raise ValueError('集成成员数量无效')
                loaded=[self.load(i) for i in ids];records=[r for m,r in loaded]
                if any(not isinstance(m,DetectionPipeline) or isinstance(m,CalibratedMaxEnsemble) or r['status']!='validated' for m,r in loaded):raise ValueError('集成成员不支持或未验证')
                if len({r['dataset_sha256'] for r in records})!=1 or len({json.dumps(r['feature_schema'],sort_keys=True) for r in records})!=1:raise ValueError('成员必须同源、同schema')
                if len({json.dumps(r['report'].get('partitions'),sort_keys=True) for r in records})!=1:raise ValueError('集成时间切分不一致')
                base=records[0];digest=base['dataset_sha256'];rows=json.loads((self.root/'datasets'/f'{digest}.json').read_text())
                model=CalibratedMaxEnsemble([m for m,r in loaded],ids,body.get('factor',1.));labels=base.get('evaluation_labels',[])
                report=model.evaluate_partitions(rows,labels);model.report=report;scope=base['source_type'];feature_schema=base['feature_schema']
            if self.registry.get('job',ident)['cancel_requested']:raise ValueError('任务已取消')
            model_ref=uuid.uuid4().hex;temporary=self.root/'models'/f'{model_ref}.tmp';artifact_hash=model.save(temporary);temporary.replace(self.root/'models'/f'{model_ref}.joblib')
            dataset=self.root/'datasets'/f'{digest}.json'
            if not dataset.exists():
                temporary=dataset.with_suffix('.tmp');temporary.write_bytes(canonical_rows(rows));temporary.replace(dataset)
            descriptor={'model_ref':model_ref,'artifact':f'{model_ref}.joblib','artifact_sha256':artifact_hash,'dataset_sha256':digest,
                'algorithm':model.algorithm,'feature_schema':feature_schema,'report':report,'capabilities':capabilities_for(model),'source_type':scope,
                'pipeline':model.metadata() if isinstance(model,DetectionPipeline) else {'schema':1,'kind':'legacy_combined'},
                'evaluation_labels':labels,'status':'validated' if report['held_out_point_alert_rate']<=.1 else 'review_required','created_at':time.time()}
            self.registry.put('model',model_ref,descriptor)
            job.update(status='completed',result=self.envelope(**{k:v for k,v in descriptor.items() if k not in ('artifact','artifact_sha256')}),completed_at=time.time())
        except Exception as exc:job.update(status='cancelled' if self.registry.get('job',ident).get('cancel_requested') else 'failed',error=str(exc),completed_at=time.time())
        self.registry.put('job',ident,job)
    def deploy(self,model_ref,platform_id):
        if platform_id!=self.registry.platform_id:raise Conflict('平台身份不匹配')
        model,record=self.load(model_ref)
        if record['status']!='validated':raise Conflict('模型未通过自检')
        self.check_scope(record['feature_schema'],record['source_type'])
        ident=uuid.uuid5(uuid.NAMESPACE_URL,self.registry.platform_id+':'+model_ref).hex
        value={'deployment_ref':ident,'model_ref':model_ref,'status':'ready'};self.registry.put('deployment',ident,value)
        return self.envelope(**value)
    def predict(self,ident,rows,factor=1.,deployed=False,platform_id=None):
        if platform_id!=self.registry.platform_id:raise Conflict('平台身份不匹配')
        deployment=self.registry.get('deployment',ident) if deployed else None
        if deployed and not deployment:raise KeyError('部署不存在')
        model_ref=deployment['model_ref'] if deployment else ident;model,record=self.load(model_ref)
        if not isinstance(rows,list) or not 1<=len(rows)<=12000:raise ValueError('推理点数超出契约')
        if isinstance(factor,bool) or not isinstance(factor,(int,float)) or not .8<=factor<=2:raise ValueError('判定倍率无效')
        if isinstance(model,DetectionPipeline):points=model.predict(rows,factor=factor)
        else:
            points=model.predict(rows)
            for point in points:
                point['threshold']*=factor;point['anomaly']=point['score']>point['threshold'];point.update(capabilities=capabilities_for(model),raw_score=None,calibrated_score=point['score'])
        quality='valid'
        if not points or points[-1]['t']!=rows[-1]['t']:
            quality=model.detector.latest_quality(model.preprocessor.transform(rows)) if hasattr(model,'detector') and hasattr(model.detector,'latest_quality') else 'warmup'
            if quality=='valid':quality='reference_window_incomplete'
        return self.envelope(model_ref=model_ref,deployment_ref=ident if deployed else None,points=points,quality=quality)
    def close(self):self.executor.shutdown(wait=True,cancel_futures=True)
