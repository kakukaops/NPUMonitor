"""Run inside gpu-ml: real historical training, replay, versioning and permissions."""
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from gpu_ml.cli import request,wait,restore

result={'scope':'live-management-and-Prometheus-history','cases':[]}

def check(name,fn):
    value=fn();result['cases'].append({'name':name,'passed':True,'result':value});print('PASS '+name,flush=True);return value


def roles():
    try:urlopen('http://localhost:9460/api/gpu-ml/v1/state');raise AssertionError('anonymous state allowed')
    except HTTPError as exc:assert exc.code==401
    for role in ('viewer','operator','admin'):assert request('/state',role=role)['role']==role
    try:request('/system/inference',{'enabled':False},role='viewer');raise AssertionError('viewer mutation')
    except HTTPError as exc:assert exc.code==403
    try:request('/feedback',{'task':'sim-0-thermal','kind':'unconfirmed'},headers={'Origin':'https://foreign.invalid'});raise AssertionError('CSRF')
    except HTTPError as exc:assert exc.code==403
    token=Path(os.environ['GPU_ML_VIEWER_TOKEN_FILE']).read_text().strip()
    req=Request('http://localhost:9460/api/gpu-ml/v1/session',data=json.dumps({'token':token}).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req) as response:
        assert 'HttpOnly' in response.headers['Set-Cookie'] and 'SameSite=strict' in response.headers['Set-Cookie']
    return 'anonymous denied / roles / CSRF / HttpOnly session'

check('access-control',roles)

def normal_workloads():
    def states(s):return [v for v in s['states'] if v['id'] in ('sim-0-thermal','sim-0-relation')]
    for scenario in ('high_load','idle'):
        request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':scenario});time.sleep(10)
        state=request('/state');assert all(not v['active'] and v['quality']=='valid' for v in states(state)),states(state)
        if scenario=='idle':assert next(v for v in state['states'] if v['id']=='sim-0-activity')['quality']=='context_inactive'
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
    return 'normal high load and idle are not hardware faults'

check('normal-workload-counterexamples',normal_workloads)

state=request('/state');task=next(t for t in state['tasks'] if t['id']=='sim-0-thermal');old_model=task['active_model']
points=request('/series/sim-0-thermal?start=0')['points']
start=points[0]['t']+2;end=time.time()-6
if end-start<420:raise AssertionError('历史尚不足7分钟，请让模拟采集继续积累后运行本验收')
job=request('/training-jobs',{'task':task['id'],'algorithm':'robust_mad','start':start,'end':end,'step':2})
finished=wait(lambda s:any(j['id']==job['id'] and j['status'] in ('completed','failed','cancelled') for j in s['jobs']),'真实历史训练完成',90)
job=next(j for j in finished['jobs'] if j['id']==job['id']);assert job['status']=='completed',job
version=job['model_id'];model=next(m for m in finished['models'] if m['id']==version)
assert model['source']=='prometheus-history' and model['report']['samples']>=180
result['cases'].append({'name':'train-from-actual-prometheus-history','passed':True,'model':version,'samples':model['report']['samples'],'excluded_known_fault_samples':job.get('excluded_known_fault_samples',0)})
print('PASS train-from-actual-prometheus-history',flush=True)
request('/tasks/'+task['id']+'/shadow',{'model':version});time.sleep(5)
shadow=request('/state');assert next(t for t in shadow['tasks'] if t['id']==task['id'])['active_model']==old_model
assert any(s['id']==task['id'] and s['model']==version for s in shadow['shadow'])
result['cases'].append({'name':'shadow-without-online-switch','passed':True})
request('/tasks/'+task['id']+'/publish',{'model':version});assert next(t for t in request('/state')['tasks'] if t['id']==task['id'])['active_model']==version
request('/tasks/'+task['id']+'/rollback',{},method='POST');assert next(t for t in request('/state')['tasks'] if t['id']==task['id'])['active_model']==old_model
request('/tasks/'+task['id']+'/shadow',{'model':None})
result['cases'].append({'name':'publish-and-rollback','passed':True})
replay=request('/replays',{'task':task['id'],'model':version,'start':time.time()-180,'end':time.time()-4,'step':2})
finished=wait(lambda s:any(j['id']==replay['id'] and j['status'] in ('completed','failed') for j in s['jobs']),'回放完成',60)
r=next(j for j in finished['jobs'] if j['id']==replay['id']);assert r['status']=='completed',r
assert len(request('/replays/'+r['id'])['points'])>3
result['cases'].append({'name':'isolated-history-replay','passed':True,'points':r['point_count']})

# A second task reuses an existing compatible version; retirement preserves history.
new=request('/tasks',{'name':'管理验收临时任务 '+str(int(time.time())),'entity':task['entity'],'template':'thermal','algorithm':'ridge_iforest'})
request('/tasks/'+new['id']+'/publish',{'model':old_model})
request('/integrations/nightingale/sync',{})
first=next(b for b in request('/state')['bindings'] if b['id']==new['id'])
current=next(t for t in request('/state')['tasks'] if t['id']==new['id'])
try:request('/tasks/'+new['id'],{'enabled':False},method='PATCH',headers={'If-Match':'0'});raise AssertionError('missing revision')
except HTTPError as exc:assert exc.code==428
renamed=request('/tasks/'+new['id'],{'name':new['name']+' renamed'},method='PATCH',headers={'If-Match':str(current['revision'])})
request('/integrations/nightingale/sync',{})
assert next(b for b in request('/state')['bindings'] if b['id']==new['id'])['rule_id']==first['rule_id']
request('/tasks/'+new['id'],{'enabled':False},method='PATCH',headers={'If-Match':str(renamed['revision'])})
current=next(t for t in request('/state')['tasks'] if t['id']==new['id'])
request('/tasks/'+new['id'],{},method='DELETE',headers={'If-Match':str(current['revision'])})
request('/integrations/nightingale/sync',{})
assert next(t for t in request('/state')['tasks'] if t['id']==new['id'])['deleted']
result['cases'].append({'name':'reuse-model-rename-stable-rule-and-retire','passed':True,'stable_rule_id':first['rule_id']})

request('/feedback',{'task':task['id'],'kind':'normal_change','note':'自动验收：正常高负载/空闲反例；不自动重训练'})
backup=request('/backups',{})
archive=Path('/data/backups')/(backup['id']+'.tar.gz')
with tempfile.TemporaryDirectory() as tmp:
    restored=restore(archive,Path(tmp)/'restored')
    assert (Path(restored['restored_to'])/'gpu-ml.sqlite').exists()
result['cases'].append({'name':'consistent-backup-and-offline-restore','passed':True,'sha256':backup['sha256']})
result.update(passed=True,recorded_at=time.time(),production_admitted=False)
p=Path('/data/evidence/management.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
