#!/usr/bin/env python3
"""Host test of actual service isolation. Prints no credentials."""
import json,os,subprocess,sys,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
ROOT=Path(__file__).resolve().parents[5];MODULE=ROOT/'modules/devices/nvidia-gpu/ml'
sys.path[:0]=[str(ROOT/'modules/model-services/contracts'),str(ROOT/'modules/model-services/adapters')]
from model_adapters.http import HttpModelBackend
from model_contracts import dataset_hash
COMPOSE=['docker','compose','-f',str(MODULE.parents[3]/'deploy/nvidia-gpu/ml/compose.yaml')]
backend=HttpModelBackend(url='http://localhost:19461',token_file=str(ROOT/'.local/gpu-ml-model-platform-token'))
admin=(ROOT/'.local/gpu-ml-admin-token').read_text().strip()
def request(path,body=None):
 req=Request('http://localhost:19460/api/gpu-ml/v1'+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+admin,'Content-Type':'application/json'})
 with urlopen(req,timeout=30) as r:return json.load(r)
def command(*args):subprocess.run(COMPOSE+list(args),check=True,stdout=subprocess.DEVNULL,env={**os.environ,'GPU_ML_SIMULATION':'true'})
def wait(predicate,label,timeout=150):
 end=time.time()+timeout
 while time.time()<end:
  try:
   s=request('/state')
   if predicate(s):return s
  except (URLError,TimeoutError):pass
  time.sleep(2)
 raise AssertionError(label)

s=request('/state');task=next(t for t in s['tasks'] if t.get('scenario_id')=='thermal_relation' and t.get('scenario_profile')=='laboratory' and next(m for m in s['models'] if m['id']==t['active_model']).get('backend'))
model=next(m for m in s['models'] if m['id']==task['active_model']);uid=task['entity'].split('|',1)[1]
def state(s):return next(x for x in s['states'] if x['id']==task['id'])
info=backend.info();out={'scope':'actual separate container stop/restart and offline training','company_platform_integrated':False,'cases':[]}
try:
 request('/simulation',{'uuid':uid,'scenario':'temperature_spike'})
 active=wait(lambda s:state(s).get('active') and state(s)['quality']=='valid','HTTP model condition opens');episode=state(active)['episode_id']
 command('stop','model-platform')
 failed=wait(lambda s:state(s)['quality']=='model_error' and state(s).get('active'),'backend outage preserves anomaly',45)
 watermark=state(failed)['last_source'];time.sleep(4);held=request('/state')
 assert state(held)['episode_id']==episode and state(held)['last_source']==watermark and state(held)['active']
 out['cases'].append({'name':'model-platform-outage-preserves-active-and-source-watermark','passed':True})
 command('up','-d','--no-deps','--wait','model-platform')
 assert backend.info()['platform_id']==info['platform_id']
 wait(lambda s:state(s)['quality']=='valid' and state(s).get('active'),'deployed model returns after restart',60)
 request('/simulation',{'uuid':uid,'scenario':'normal'})
 wait(lambda s:not state(s).get('active') and state(s)['quality']=='valid','fresh normal recovers',90)
 out['cases'].append({'name':'platform-restart-keeps-deployment-identity-and-recovers','passed':True})
 raw=subprocess.check_output(COMPOSE+['exec','-T','gpu-ml','cat','/data/snapshots/'+model['snapshot']]);rows=json.loads(raw)
 ident=uuid.uuid4().hex;body={'training_spec':{'template':model['template'],'algorithm':model['algorithm'],'feature_schema':model['feature_schema'],'source_type':model['source_type'],'pipeline':{},'labels':[]},'dataset':{'sha256':dataset_hash(rows),'rows':rows}}
 command('stop','gpu-ml')
 # Entire training and preview takes place while no monitoring API process is running.
 backend.submit(ident,'fit',body);deadline=time.time()+90
 while time.time()<deadline:
  job=backend.job(ident)
  if job['status'] in ('completed','failed','cancelled'):break
  time.sleep(.5)
 assert job['status']=='completed',job
 deployed=backend.deploy(job['result']['model_ref'],job['platform_id'])
 batch=backend.predict({'backend_id':backend.backend_id,'platform_id':job['platform_id'],'model_ref':job['result']['model_ref'],'deployment_ref':deployed['deployment_ref']},rows[-80:],1.)
 assert batch.quality=='valid'
 out['cases'].append({'name':'training-deployment-prediction-with-monitor-stopped','passed':True,'platform_job':ident})
finally:
 command('up','-d','--no-deps','--wait','model-platform','gpu-ml')
 try:request('/simulation',{'uuid':uid,'scenario':'normal'})
 except URLError:pass
wait(lambda s:state(s)['quality']=='valid' and not state(s).get('active'),'monitor resumes HTTP inference after own restart',150)
out.update(passed=True,recorded_at=time.time());folder=MODULE/'evidence/gpu-v5';folder.mkdir(exist_ok=True);(folder/'isolation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
