"""Local GPU monitoring API, persistent result gateway and independent Web UI."""
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import tarfile
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from .settings import DATA,BASE,SIMULATION,METRICS,TEMPLATES,FRESHNESS
from .store import Store,Conflict,check_initialization
from .source import Source
from .engine import Engine
from .simulation import Simulator,SCENARIOS
from .nightingale import Nightingale
from . import __version__
from .models import ALGORITHMS,build_model
from .pipeline import build_pipeline,describe_algorithms,capabilities_for
from .dcgm_scenarios import CATALOG as DCGM_SCENARIOS,template_name
from .model_backends.contracts import BackendError,BackendUnavailable,BackendProtocolError,BackendUnsupported
from .model_backends.training import Deferred

STORE=None;ENGINE=None;N9E=None
SIM=Simulator()
SESSIONS={};ROLE_ORDER={'viewer':0,'operator':1,'admin':2}


def authenticate(token):
    if not token:return None
    digest=hashlib.sha256(token.encode()).digest()
    for role in ('admin','operator','viewer'):
        filename=os.environ.get('GPU_ML_'+role.upper()+'_TOKEN_FILE')
        if filename:
            try:expected=Path(filename).read_text().strip()
            except OSError:continue
            if expected and hmac.compare_digest(digest,hashlib.sha256(expected.encode()).digest()):return role
    return None


def user(request,minimum='viewer'):
    header=request.headers.get('Authorization','')
    role=authenticate(header[7:]) if header.startswith('Bearer ') else None
    if role is None:
        session=SESSIONS.get(request.cookies.get('gpu_ml_session',''))
        if session and session['expires']>time.time():role=session['role']
    if role is None:raise HTTPException(401,'请先登录')
    if ROLE_ORDER[role]<ROLE_ORDER[minimum]:raise HTTPException(403,'当前角色无操作权限')
    return role


def required_body_value(body,key):
    value=body.get(key)
    if not isinstance(value,str) or not value or len(value)>180:raise ValueError('字段无效: '+key)
    return value


@asynccontextmanager
async def lifespan(app):
    global STORE,ENGINE,N9E
    DATA.mkdir(parents=True,exist_ok=True)
    # Single-process/single-active lease: refuse a second writer on the same volume.
    import fcntl
    lease=(DATA/'writer.lock').open('w')
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    guard_file=os.environ.get('GPU_ML_INIT_GUARD_FILE')
    if guard_file:check_initialization(DATA/'gpu-ml.sqlite',guard_file)
    STORE=Store(DATA/'gpu-ml.sqlite')
    for schema in STORE.list('template'):
        TEMPLATES[schema['id']]={k:v for k,v in schema.items() if k not in ('id','revision')}
        if schema.get('kind')=='multivariate':TEMPLATES[schema['id']]['algorithms']=['joint_pca','joint_iforest']
    source=Source()
    STORE.bind_source(hashlib.sha256(json.dumps({'url':source.url,'metrics':METRICS},sort_keys=True).encode()).hexdigest())
    ENGINE=Engine(STORE,source);N9E=Nightingale(STORE)
    if SIMULATION:
        for record in STORE.list('simulation'):
            if record['id'] in SIM.modes:SIM.modes[record['id']]={'scenario':record['scenario'],'since':record['since']}
    ENGINE.start()
    def maintenance():
        while not ENGINE.stop.wait(15):
            try:
                if STORE.get('system','nightingale'):
                    signature=N9E.signature()
                    if STORE.get('system','nightingale').get('task_signature')!=signature:
                        try:N9E.sync()
                        except Exception as exc:STORE.put('system','sync_error',{'error':type(exc).__name__,'at':time.time()})
                    N9E.events()
                STORE.prune()
            except Exception:logging.exception('Maintenance failed')
    threading.Thread(target=maintenance,daemon=True).start()
    try:yield
    finally:
        ENGINE.stop.set();ENGINE.thread.join(timeout=12)
        ENGINE.training.close()
        ENGINE.executor.shutdown(wait=True,cancel_futures=True)
        lease.close()


app=FastAPI(title='GPU ML Monitoring',version=__version__,lifespan=lifespan,docs_url=None,redoc_url=None)


@app.middleware('http')
async def guard(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc!=request.headers.get('host'):return JSONResponse({'detail':'跨站请求已拒绝'},403)
        if int(request.headers.get('content-length','0') or '0')>65536:return JSONResponse({'detail':'请求过大'},413)
        if len(await request.body())>65536:return JSONResponse({'detail':'请求过大'},413)
    try:response=await call_next(request)
    except Conflict as exc:return JSONResponse({'detail':str(exc)},409)
    except (ValueError,KeyError,TypeError) as exc:return JSONResponse({'detail':str(exc)},400)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(Conflict)
async def conflict_handler(request,exc):return JSONResponse({'detail':str(exc)},409)

@app.exception_handler(BackendError)
async def backend_error(request,exc):return JSONResponse({'detail':str(exc)},503 if isinstance(exc,BackendUnavailable) else 502 if isinstance(exc,BackendProtocolError) else 409)

@app.exception_handler(Deferred)
async def deferred(request,exc):return JSONResponse({'pending':True,'job_id':exc.job_id,'detail':'外部模型任务仍在协调，请查看作业状态；在线模型未切换'},202)

@app.exception_handler(ValueError)
async def value_handler(request,exc):return JSONResponse({'detail':str(exc)},400)


@app.get('/health')
def health():return {'alive':True,'version':__version__}

@app.get('/ready')
def ready():
    good=ENGINE is not None and 0<=time.time()-ENGINE.last_poll<15 and not ENGINE.error
    return JSONResponse({'ready':good,'simulation':SIMULATION},200 if good else 503)

@app.get('/')
def index():return FileResponse(BASE/'frontend/index.html')

app.mount('/assets',StaticFiles(directory=BASE/'frontend'),name='assets')


@app.post('/api/gpu-ml/v1/session')
async def login(request:Request):
    body=await request.json();token=body.get('token','')
    if not isinstance(token,str) or len(token)>256:raise HTTPException(401,'令牌无效')
    if 'role' in body:
        if os.environ.get('GPU_ML_DEMO_LOGIN','false').lower()!='true':
            raise HTTPException(403,'当前部署未启用演示角色登录')
        role=body['role']
        if not isinstance(role,str) or role not in ('admin','operator','viewer'):raise HTTPException(400,'登录类型无效')
    else:
        role=authenticate(token)
    if not role:raise HTTPException(401,'令牌无效')
    if len(SESSIONS)>1000:SESSIONS.clear()
    ident=secrets.token_urlsafe(32);SESSIONS[ident]={'role':role,'expires':time.time()+28800}
    response=JSONResponse({'role':role})
    response.set_cookie('gpu_ml_session',ident,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=28800)
    return response

@app.delete('/api/gpu-ml/v1/session')
def logout(request:Request):
    SESSIONS.pop(request.cookies.get('gpu_ml_session',''),None)
    response=JSONResponse({'logged_out':True});response.delete_cookie('gpu_ml_session');return response


@app.get('/api/gpu-ml/v1/state')
def state(request:Request):
    role=user(request)
    entities=STORE.list('entity')
    for entity in entities:
        entity['fresh']=time.time()-entity['seen_at']<FRESHNESS
        entity['quality']={k:entity['quality'].get(k,'missing') if entity['fresh'] else 'missing' for k in METRICS}
        entity['capabilities']={k:all(entity['quality'].get(m)=='valid' for m in t['required']) for k,t in TEMPLATES.items()}
    states=STORE.list('state')
    for item in states:
        if item['quality']=='valid' and time.time()-item.get('last_source',0)>FRESHNESS:item['quality']='inference_stale'
    return {'role':role,'time':time.time(),'simulation':SIMULATION,'production_admitted':False,
            'entities':entities,'tasks':STORE.list('task'),'states':states,'models':STORE.list('model'),
            'jobs':STORE.list('job'),'model_backend':ENGINE.training.status,'dcgm_scenarios':DCGM_SCENARIOS,'algorithm_catalog':describe_algorithms(),'comparisons':STORE.list('comparison'),'templates':TEMPLATES,'metrics':METRICS,'algorithms':ALGORITHMS,
            'bindings':STORE.list('binding'),'sync_error':STORE.get('system','sync_error'),'nightingale':STORE.get('system','nightingale_events') or {'connected':False,'events':[]},
            'source':ENGINE.source.stats,'inference':{'last_poll':ENGINE.last_poll,'error':ENGINE.error,
                'enabled':(STORE.get('system','inference') or {'enabled':True})['enabled']},
            'event_aggregation':'nightingale','scenarios':SCENARIOS if SIMULATION else [],'feedback':STORE.list('feedback')[-100:],'shadow':STORE.list('shadow')}



@app.post('/api/gpu-ml/v1/scenario-policies')
async def create_scenario_policy(request:Request):
    actor=user(request,'operator');body=await request.json();entities=body.get('entities',[]);scenes=body.get('scenarios',[]);profile=body.get('profile','production')
    if profile not in DCGM_SCENARIOS['profiles']:raise ValueError('场景profile无效')
    if not isinstance(entities,list) or not 1<=len(entities)<=100 or not all(isinstance(e,str) and STORE.get('entity',e) for e in entities):raise ValueError('请选择已发现GPU')
    if not isinstance(scenes,list) or not scenes or not all(isinstance(s,str) and s in DCGM_SCENARIOS['scenarios'] for s in scenes):raise ValueError('请选择DCGM场景')
    entities=sorted(set(entities));scenes=sorted(set(scenes))
    if len(entities)*len(scenes)>200:raise ValueError('一次最多展开200项')
    if profile=='laboratory' and (not SIMULATION or any(STORE.get('entity',e)['source_type']!='simulated' for e in entities)):raise ValueError('加速实验profile仅允许显式模拟GPU，不能用于真实卡')
    created=[];skipped=[]
    for entity in entities:
        for scene in scenes:
            template=template_name(scene,profile);spec=TEMPLATES[template]
            ident='s4-'+hashlib.sha256((entity+'|'+template).encode()).hexdigest()[:24]
            if STORE.get('task',ident):skipped.append(ident);continue
            task={'name':entity.split('|',1)[1]+' · '+spec['name'],'entity':entity,'template':template,'algorithm':spec['algorithm'],
                  'enabled':True,'active_model':None,'scope':STORE.get('entity',entity)['source_type'],'sensitivity':1.,'created_at':time.time(),
                  'policy_kind':'dcgm_scenario','scenario_id':scene,'scenario_profile':profile,'notification_mode':'evidence'}
            created.append(STORE.put('task',ident,task,expected=0))
    STORE.audit(actor,'scenario_policy',profile,{'created':len(created),'scenes':scenes})
    return {'created':created,'skipped':skipped,'notification_mode':'evidence','training':'required; no simulated fallback'}

@app.post('/api/gpu-ml/v1/tasks/{key}/admission')
async def scenario_admission(key:str,request:Request):
    actor=user(request,'admin');body=await request.json();task=STORE.get('task',key)
    if not task or not task.get('scenario_id'):raise ValueError('仅适用于场景任务')
    mode=body.get('mode')
    if mode not in ('evidence','alert'):raise ValueError('通知模式无效')
    if mode=='alert':
        for name in ('evidence_ref','owner','action'):required_body_value(body,name)
        if not task.get('active_model'):raise ValueError('请先发布场景模型')
        task['admission']={'evidence_ref':body['evidence_ref'],'owner':body['owner'],'action':body['action'],'at':time.time(),
                           'scope':task['scope'],'meaning':'manual notification authorization; not an automatic production qualification'}
    task['notification_mode']=mode
    result=STORE.put('task',key,task,expected=task['revision']);STORE.audit(actor,'scenario_admission',key,{'mode':mode,'admission':task.get('admission')})
    return result

@app.post('/api/gpu-ml/v1/policies')
async def create_policy(request:Request):
    """Expand selected entities/metrics into idempotent, untrained detector configs."""
    actor=user(request,'operator');body=await request.json()
    entities=body.get('entities',[]);metrics=body.get('metrics',[]);kind=body.get('kind')
    selectable={'gpu_temp','memory_temp','power','sm_clock','mem_clock','util','mem_util','fb_used'}
    if not isinstance(entities,list) or not 1<=len(entities)<=100 or not all(isinstance(e,str) and STORE.get('entity',e) for e in entities):raise ValueError('请选择1至100张已发现GPU')
    if not isinstance(metrics,list) or not metrics or not all(isinstance(m,str) and m in selectable for m in metrics):raise ValueError('指标组合无效')
    metrics=sorted(set(metrics));entities=sorted(set(entities))
    if kind not in ('univariate','multivariate') or (kind=='multivariate' and len(metrics)<2):raise ValueError('联合检测至少需要两个指标')
    if len(entities)*(len(metrics) if kind=='univariate' else 1)>200:raise ValueError('一次最多生成200项检测')
    algorithm='temporal_mad' if kind=='univariate' else 'joint_pca'
    schemas=['uni_'+m for m in metrics]
    if kind=='multivariate':
        key='joint_'+hashlib.sha256(json.dumps(metrics).encode()).hexdigest()[:16]
        spec={'kind':kind,'name':'多指标联合 · '+', '.join(metrics),'required':metrics,'targets':metrics,'features':[],'algorithms':['joint_pca','joint_iforest'],'description':'PCA标准化联合行为；参考线为重构值，不是预测值；不解释为具体故障'}
        STORE.put('template',key,spec);TEMPLATES[key]=spec;schemas=[key]
    created=[];skipped=[]
    for entity in entities:
        for template in schemas:
            ident='v2-'+hashlib.sha256((entity+'|'+template).encode()).hexdigest()[:24]
            old=STORE.get('task',ident)
            if old:
                skipped.append({'id':ident,'reason':'retired' if old.get('deleted') else 'already_exists'});continue
            task={'name':entity.split('|',1)[1]+' · '+TEMPLATES[template]['name'],'entity':entity,'template':template,'algorithm':algorithm,'enabled':True,'scope':STORE.get('entity',entity)['source_type'],'active_model':None,'sensitivity':1.,'created_at':time.time(),'policy_kind':kind}
            created.append(STORE.put('task',ident,task,expected=0))
    STORE.audit(actor,'policy_expand',kind,{'entities':entities,'metrics':metrics,'created':len(created),'skipped':len(skipped)})
    return {'created':created,'skipped':skipped,'training':'required; no automatic synthetic fallback','event_aggregation':'nightingale'}

@app.post('/api/gpu-ml/v1/tasks')
async def create_task(request:Request):
    actor=user(request,'operator');body=await request.json()
    entity=required_body_value(body,'entity');template=required_body_value(body,'template')
    if not STORE.get('entity',entity) or template not in TEMPLATES:raise ValueError('实体或模板不存在')
    if TEMPLATES[template].get('scenario'):raise ValueError('DCGM场景请使用scenario-policies，不能绕过profile和通知模式检查')
    algorithm=body.get('algorithm','ridge_iforest')
    build_pipeline(template,algorithm)
    key=uuid.uuid4().hex
    task={'name':required_body_value(body,'name'),'entity':entity,'template':template,'algorithm':algorithm,
          'enabled':True,'scope':STORE.get('entity',entity)['source_type'],'active_model':None,'sensitivity':1.,'created_at':time.time()}
    result=STORE.put('task',key,task,expected=0);STORE.audit(actor,'task_create',key)
    return result

@app.post('/api/gpu-ml/v1/tasks/{key}/validate')
def validate_task(key:str,request:Request):
    user(request);task=STORE.get('task',key)
    if not task:raise HTTPException(404,'任务不存在')
    entity=STORE.get('entity',task['entity']) or {'quality':{}}
    required=TEMPLATES[task['template']]['required']
    fresh=bool(entity.get('seen_at') and time.time()-entity['seen_at']<=FRESHNESS)
    quality={name:entity['quality'].get(name,'missing') if fresh else 'missing' for name in required}
    return {'compatible_input':all(v=='valid' for v in quality.values()),'required':quality,
            'production_admitted':False,'source_type':task['scope'],
            'compatible_models':[m['id'] for m in STORE.list('model') if (m['entity'],m['template'],m['source_type'])==(task['entity'],task['template'],task['scope'])]}


@app.patch('/api/gpu-ml/v1/tasks/{key}')
async def update_task(key:str,request:Request):
    actor=user(request,'operator');body=await request.json();task=STORE.get('task',key)
    if not task:raise HTTPException(404,'任务不存在')
    expected=int(request.headers.get('if-match','-1'))
    if expected<1:raise HTTPException(428,'需要If-Match版本')
    allowed={'name','enabled','sensitivity'}
    if set(body)-allowed:raise ValueError('不允许修改该字段；输入变更请创建新任务')
    if 'name' in body:required_body_value(body,'name')
    if 'enabled' in body and not isinstance(body['enabled'],bool):raise ValueError('enabled需要布尔值')
    if 'sensitivity' in body and (isinstance(body['sensitivity'],bool) or not isinstance(body['sensitivity'],(int,float)) or not .8<=body['sensitivity']<=2):raise ValueError('阈值倍率范围0.8～2')
    if task.get('deleted'):raise ValueError('任务已退役，请创建新任务')
    task.update(body);result=STORE.put('task',key,task,expected=expected)
    if not task['enabled']:STORE.administrative_close(key,'task_paused_by_operator')
    STORE.audit(actor,'task_update',key,body);return result

@app.delete('/api/gpu-ml/v1/tasks/{key}')
def delete_task(key:str,request:Request):
    actor=user(request,'operator');task=STORE.get('task',key)
    if not task:raise HTTPException(404,'任务不存在')
    expected=int(request.headers.get('if-match','-1'))
    if expected<1:raise HTTPException(428,'需要If-Match版本')
    task.update(enabled=False,deleted=True)
    STORE.put('task',key,task,expected=expected);STORE.administrative_close(key,'task_deleted_by_operator')
    STORE.audit(actor,'task_delete',key)
    return {'deleted':True,'history_preserved':True}


@app.post('/api/gpu-ml/v1/training-jobs')
async def train(request:Request):
    actor=user(request,'operator');body=await request.json()
    result=ENGINE.queue_training(required_body_value(body,'task'),body.get('algorithm','ridge_iforest'),float(body['start']),float(body['end']),int(body.get('step',2)),config=body.get('pipeline'),labels=body.get('labels'))
    STORE.audit(actor,'training_create',result['id']);return result

@app.post('/api/gpu-ml/v1/jobs/{key}/cancel')
def cancel(key:str,request:Request):
    actor=user(request,'operator');result=ENGINE.training.cancel(key)
    STORE.audit(actor,'training_cancel',key);return result

@app.post('/api/gpu-ml/v1/models/{key}/postprocess')
async def postprocess_model(key:str,request:Request):
    actor=user(request,'operator');body=await request.json()
    if set(body)-{'calibration','factor'}:raise ValueError('后处理仅接受calibration和factor，不改变模型输入')
    result=await run_in_threadpool(ENGINE.reconfigure,key,body.get('calibration'),body.get('factor'))
    STORE.audit(actor,'postprocess_version',result['id'],{'parent':key,'detector_retrained':False})
    return result

@app.post('/api/gpu-ml/v1/ensembles')
async def ensemble(request:Request):
    actor=user(request,'operator');body=await request.json()
    result=await run_in_threadpool(ENGINE.create_ensemble,required_body_value(body,'task'),body.get('models'),body.get('factor',1.))
    STORE.audit(actor,'ensemble_create',result['id'],{'members':body.get('models')});return result

@app.post('/api/gpu-ml/v1/comparisons')
async def comparison(request:Request):
    actor=user(request,'operator');body=await request.json()
    result=ENGINE.queue_comparison(required_body_value(body,'task'),body.get('algorithms'),float(body['start']),float(body['end']),int(body.get('step',2)),body.get('pipeline'),body.get('labels'))
    STORE.audit(actor,'comparison_create',result['id']);return result

@app.get('/api/gpu-ml/v1/comparisons/{key}')
def comparison_detail(key:str,request:Request):
    user(request);result=STORE.get('comparison',key)
    if result is None:raise HTTPException(404,'比较尚未完成')
    return result

@app.post('/api/gpu-ml/v1/tasks/{key}/publish')
async def publish(key:str,request:Request):
    actor=user(request,'operator');body=await request.json();await run_in_threadpool(ENGINE.publish,key,required_body_value(body,'model'),actor)
    return STORE.get('task',key)

@app.post('/api/gpu-ml/v1/tasks/{key}/shadow')
async def shadow_model(key:str,request:Request):
    actor=user(request,'operator');body=await request.json();task=STORE.get('task',key)
    if not task or task.get('deleted'):raise ValueError('任务不存在或已退役')
    model_id=body.get('model')
    if model_id:
        model=STORE.get('model',model_id)
        if not model or (model['entity'],model['template'],model['source_type'])!=(task['entity'],task['template'],task['scope']):
            raise ValueError('影子模型不兼容')
        ENGINE.load(model_id)
    task['shadow_model']=model_id
    result=STORE.put('task',key,task,expected=task['revision']);STORE.audit(actor,'shadow_model',key,{'model':model_id})
    return result


@app.post('/api/gpu-ml/v1/tasks/{key}/rollback')
def rollback(key:str,request:Request):
    actor=user(request,'operator');task=STORE.get('task',key)
    if not task or not task.get('previous_model'):raise ValueError('没有可回滚版本')
    ENGINE.publish(key,task['previous_model'],actor);return STORE.get('task',key)

@app.get('/api/gpu-ml/v1/series/{key}')
def series(key:str,request:Request,start:float=0,end:float=0):
    user(request);task=STORE.get('task',key)
    if not task:raise HTTPException(404,'任务不存在')
    end=end or time.time();start=start or end-1800
    if end-start>86400*7 or end<=start:raise ValueError('展示窗口无效或超过7天')
    points=STORE.history(key,start,end)
    return {'task':task,'points':points,'point_limit':12000,'truncated':len(points)>=12000,'source':'persisted-online-prometheus-input',
            'state':STORE.get('state',key),'capabilities':capabilities_for(ENGINE.load(task['active_model'])) if task.get('active_model') else None}

@app.get('/api/gpu-ml/v1/raw-series')
def raw_series(request:Request,entity:str,start:float,end:float,step:int=10,metric:str='gpu_temp'):
    user(request)
    if not STORE.get('entity',entity) or step<2:raise ValueError('实体或采样步长无效')
    if metric not in METRICS:raise ValueError('未知指标')
    keys=[metric] if STORE.get('entity',entity)['quality'].get(metric)=='valid' else []
    if not keys:return {'points':[],'quality':'missing'}
    return {'points':ENGINE.source.history(entity,start,end,step,keys),'source':'existing-prometheus-readonly'}

@app.post('/api/gpu-ml/v1/replays')
async def replay(request:Request):
    actor=user(request,'operator');body=await request.json()
    result=ENGINE.replay(body['task'],body['model'],float(body['start']),float(body['end']),int(body.get('step',2)),labels=body.get('labels'))
    STORE.audit(actor,'replay_create',result['id']);return result

@app.get('/api/gpu-ml/v1/replays/{key}')
def replay_detail(key:str,request:Request):
    user(request);result=STORE.get('replay',key)
    if result is None:raise HTTPException(404,'回放尚未完成')
    return result

@app.post('/api/gpu-ml/v1/feedback')
async def feedback(request:Request):
    actor=user(request,'operator');body=await request.json()
    if body.get('kind') not in ('fault','normal_change','collection_problem','unconfirmed'):raise ValueError('反馈类型无效')
    if not STORE.get('task',body.get('task','')):raise ValueError('任务不存在')
    start=float(body.get('start',time.time()-300));end=float(body.get('end',time.time()))
    if not 0<end-start<=86400*31 or end>time.time()+2:raise ValueError('反馈时间窗口无效')
    note=str(body.get('note',''))[:2000];key=uuid.uuid4().hex
    result=STORE.put('feedback',key,{'task':body['task'],'kind':body['kind'],'note':note,'at':time.time(),'actor':actor,'start':start,'end':end})
    STORE.audit(actor,'feedback',key);return result

@app.get('/api/gpu-ml/v1/audit')
def audits(request:Request):user(request,'admin');return STORE.audits()

@app.post('/api/gpu-ml/v1/simulation')
async def simulation(request:Request):
    actor=user(request,'operator')
    if not SIMULATION:raise HTTPException(404,'真实模式没有模拟控制')
    body=await request.json();SIM.set(body['uuid'],body['scenario']);STORE.put('simulation',body['uuid'],dict(SIM.modes[body['uuid']]));STORE.audit(actor,'simulation',body['uuid'],{'scenario':body['scenario']})
    return {'applied':True}

@app.get('/simulation/metrics')
def simulation_metrics():
    from fastapi.responses import PlainTextResponse
    if not SIMULATION:raise HTTPException(404,'模拟未启用')
    return PlainTextResponse(SIM.metrics(),media_type='text/plain; version=0.0.4')

@app.post('/api/gpu-ml/v1/integrations/nightingale/sync')
def sync(request:Request):
    actor=user(request,'admin');result=N9E.sync();STORE.audit(actor,'nightingale_sync','all',{'count':len(result)});return result

@app.post('/api/gpu-ml/v1/system/inference')
async def inference(request:Request):
    actor=user(request,'admin');body=await request.json()
    if not isinstance(body.get('enabled'),bool):raise ValueError('enabled需要布尔值')
    STORE.put('system','inference',{'enabled':body['enabled']});STORE.audit(actor,'inference_control','all',body);return body

@app.post('/api/gpu-ml/v1/backups')
def backup(request:Request):
    actor=user(request,'admin');key=uuid.uuid4().hex
    folder=DATA/'backups'/key;folder.mkdir(parents=True)
    STORE.backup(folder/'gpu-ml.sqlite')
    archive=DATA/'backups'/f'{key}.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        tar.add(folder/'gpu-ml.sqlite',arcname='gpu-ml.sqlite')
        tar.add(DATA/'models',arcname='models');tar.add(DATA/'snapshots',arcname='snapshots')
    STORE.audit(actor,'backup',key)
    return {'id':key,'download':'/api/gpu-ml/v1/backups/'+key,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'remote_model_refs':[m['backend'] for m in STORE.list('model') if m.get('backend')],
            'scope':'monitor configuration, snapshots and legacy local artifacts; remote weights need platform backup'}

@app.get('/api/gpu-ml/v1/backups/{key}')
def backup_download(key:str,request:Request):
    user(request,'admin')
    if not re.fullmatch('[a-f0-9]{32}',key):raise HTTPException(404)
    path=DATA/'backups'/f'{key}.tar.gz'
    if not path.exists():raise HTTPException(404)
    return FileResponse(path,filename='gpu-ml-backup-'+key+'.tar.gz')


def gateway(expression):
    if expression=='1+1':return {'status':'success','data':{'resultType':'scalar','result':[time.time(),'2']}}
    if expression=='gpu_ml_input_unhealthy':
        unhealthy={}
        for task in STORE.list('task'):
            state=STORE.get('state',task['id'])
            if task['enabled'] and task.get('notification_mode','alert')=='alert' and task.get('active_model') and state and state['quality'] not in ('valid','context_inactive','paused'):
                unhealthy[task['entity']]=True
        result=[]
        if 0<=time.time()-ENGINE.last_poll<=15 and ENGINE.error is None:
            for entity in unhealthy:
                cluster,uid=entity.split('|',1)
                result.append({'metric':{'cluster_id':cluster,'UUID':uid,'managed_by':'gpu-monitoring-ml'},'value':[time.time(),'1']})
    elif expression=='gpu_ml_platform_unhealthy':
        unhealthy=not 0<=time.time()-ENGINE.last_poll<=15 or ENGINE.error is not None
        result=[{'metric':{'managed_by':'gpu-monitoring-ml'},'value':[time.time(),'1']}] if unhealthy else []
    else:
        match=re.fullmatch(r'gpu_ml_active\{detector_id="([a-zA-Z0-9_-]{1,80})"\}\s*==\s*1',expression)
        if not match:raise HTTPException(422,'该网关仅支持文档中的固定查询契约')
        if not 0<=time.time()-ENGINE.last_poll<=15:raise HTTPException(503,'推理心跳过期；不返回成功空结果')
        task=STORE.get('task',match[1]);state=STORE.get('state',match[1])
        if not task or not state:raise HTTPException(503,'检测任务尚未就绪')
        cluster,uid=task['entity'].split('|',1)
        result=[{'metric':{'detector_id':task['id'],'cluster_id':cluster,'UUID':uid,'managed_by':'gpu-monitoring-ml','detector_kind':TEMPLATES[task['template']].get('kind','legacy'),'metric_group':','.join(TEMPLATES[task['template']]['targets'])},
                 'value':[time.time(),'1']}] if state['active'] and task.get('notification_mode','alert')=='alert' else []
    return {'status':'success','data':{'resultType':'vector','result':result}}

@app.get('/api/v1/query')
def query(query:str):return gateway(query)

@app.post('/api/v1/query')
async def query_post(request:Request):
    # Prometheus clients POST application/x-www-form-urlencoded. No multipart dependency.
    from urllib.parse import parse_qs
    raw=await request.body()
    if len(raw)>4096:raise HTTPException(413)
    return gateway(parse_qs(raw.decode()).get('query',[''])[0])

@app.get('/api/v1/status/buildinfo')
def buildinfo():return {'status':'success','data':{'version':'gpu-ml-fixed-query-v1'}}


if __name__=='__main__':
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app,host='0.0.0.0',port=9460,access_log=False)
