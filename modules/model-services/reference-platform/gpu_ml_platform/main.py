"""Independent reference platform HTTP API. Intentionally no monitor control-plane import."""
from contextlib import asynccontextmanager
import hashlib,hmac,os,tarfile,time,uuid
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse
from .runtime import Runtime,Conflict

RUNTIME=None
@asynccontextmanager
async def lifespan(app):
    global RUNTIME
    root=Path(os.environ.get('MODEL_PLATFORM_DATA','/platform-data'));root.mkdir(parents=True,exist_ok=True)
    import fcntl
    lease=(root/'writer.lock').open('w');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    RUNTIME=Runtime(root,os.environ.get('GPU_ML_SIMULATION','false').lower()=='true')
    try:yield
    finally:RUNTIME.close();lease.close()
app=FastAPI(title='Independent reference model platform',lifespan=lifespan,docs_url=None,redoc_url=None)
@app.middleware('http')
async def guard(request,call_next):
    if request.url.path!='/health':
        filename=os.environ.get('MODEL_PLATFORM_TOKEN_FILE','/run/secrets/model-platform-token')
        try:expected=Path(filename).read_text().strip()
        except OSError:expected=''
        token=request.headers.get('authorization','')
        if not expected or not hmac.compare_digest(hashlib.sha256(token.encode()).digest(),hashlib.sha256(('Bearer '+expected).encode()).digest()):return JSONResponse({'contract_version':1,'detail':'unauthorized'},401)
    if request.method=='POST' and len(await request.body())>16*1024*1024:return JSONResponse({'contract_version':1,'detail':'request quota'},413)
    return await call_next(request)
@app.exception_handler(ValueError)
async def invalid(request,exc):return JSONResponse({'contract_version':1,'detail':str(exc)},400)
@app.exception_handler(Conflict)
async def conflict(request,exc):return JSONResponse({'contract_version':1,'detail':str(exc)},409)
@app.exception_handler(KeyError)
async def missing(request,exc):return JSONResponse({'contract_version':1,'detail':'resource not found'},404)
@app.get('/health')
def health():return {'alive':RUNTIME is not None,'component':'model-platform','contract_version':1}
@app.get('/v1/info')
def info():return RUNTIME.info()
@app.post('/v1/jobs')
async def submit(request:Request):return RUNTIME.submit(await request.json())
@app.get('/v1/jobs/{key}')
def job(key:str):return RUNTIME.job(key)
@app.post('/v1/jobs/{key}/cancel')
def cancel(key:str):return RUNTIME.cancel(key)
@app.post('/v1/deployments')
async def deploy(request:Request):
    body=await request.json();return RUNTIME.deploy(body['model_ref'],body['platform_id'])
@app.post('/v1/models/{key}/predict')
async def preview(key:str,request:Request):
    body=await request.json();return RUNTIME.predict(key,body['rows'],body.get('decision_factor',1.),platform_id=body.get('platform_id'))
@app.post('/v1/deployments/{key}/predict')
async def predict(key:str,request:Request):
    body=await request.json();return RUNTIME.predict(key,body['rows'],body.get('decision_factor',1.),True,body.get('platform_id'))
@app.post('/v1/backups')
def backup():
    ident=uuid.uuid4().hex;folder=RUNTIME.root/'backups';folder.mkdir(exist_ok=True);dbfile=folder/(ident+'.sqlite');archive=folder/(ident+'.tar.gz')
    with RUNTIME.registry.lock:
        import sqlite3
        with RUNTIME.registry.connect() as source:
            target=sqlite3.connect(dbfile);source.backup(target);target.close()
        records=RUNTIME.registry.list('model')
        with tarfile.open(archive,'w:gz') as tar:
            tar.add(dbfile,arcname='registry.sqlite')
            for record in records:tar.add(RUNTIME.root/'models'/record['artifact'],arcname='models/'+record['artifact'])
            for digest in {r['dataset_sha256'] for r in records}:tar.add(RUNTIME.root/'datasets'/(digest+'.json'),arcname='datasets/'+digest+'.json')
    return RUNTIME.envelope(archive_name=archive.name,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),model_count=len(records),meaning='platform backup; copy archive from platform volume')
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=9470,access_log=False)
