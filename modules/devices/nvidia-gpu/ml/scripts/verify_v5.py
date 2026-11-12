"""Run inside monitor. Actual separate training/deployment/prediction HTTP, no company API assumptions."""
import json,time
from pathlib import Path
from gpu_ml.cli import request,wait
from gpu_ml.model_backends.http import HttpModelBackend

backend=HttpModelBackend();info=backend.info();out={'scope':'independent reference model service; actual Prometheus; simulated GPU','company_platform_integrated':False,'cases':[]}
def note(name,**values):
 case={'name':name,'passed':True,**values};out['cases'].append(case);print(json.dumps(case),flush=True)
def done(job):
 s=wait(lambda s:any(j['id']==job['id'] and j['status'] in ('completed','failed','cancelled') for j in s['jobs']),'remote model job',120)
 j=next(j for j in s['jobs'] if j['id']==job['id']);assert j['status']=='completed',j;return j
s=request('/state');task=next(t for t in s['tasks'] if t.get('scenario_id')=='thermal_relation' and t.get('scenario_profile')=='laboratory');old=task['active_model']
end=time.time()-3600
job=done(request('/training-jobs',{'task':task['id'],'algorithm':task['algorithm'],'start':end-3600,'end':end,'step':2}))
s=request('/state');model=next(m for m in s['models'] if m['id']==job['model_id'])
assert model['backend']['platform_id']==info['platform_id'] and 'artifact' not in model and model['status']=='validated',model['report']
assert not (Path('/data/models')/(model['id']+'.joblib')).exists()
assert next(t for t in s['tasks'] if t['id']==task['id'])['active_model']==old
note('independent-training-and-platform-artifacts',model_id=model['id'],backend_request_id=job['backend_request_id'],samples=model['report']['samples'])
request('/tasks/'+task['id']+'/publish',{'model':model['id']})
s=wait(lambda s:any(x['id']==task['id'] and x['quality']=='valid' and x.get('model_id')==model['id'] for x in s['states']),'HTTP deployed inference',90)
current=next(m for m in s['models'] if m['id']==model['id']);assert current['backend']['deployment_ref']
points=request('/series/'+task['id']+'?start='+str(time.time()-120)+'&end='+str(time.time()))['points'];assert points[-1]['model']==model['id']
note('deploy-before-pointer-switch-and-http-inference',deployment=current['backend']['deployment_ref'])
post=request('/models/'+model['id']+'/postprocess',{'factor':1.2})
assert post['pipeline']['detector_id']==model['pipeline']['detector_id'] and post['pipeline']['decision_id']!=model['pipeline']['decision_id']
assert post['backend']['model_ref']!=model['backend']['model_ref']
ensemble=request('/ensembles',{'task':task['id'],'models':[model['id'],post['id']]});assert ensemble['status']=='validated'
end=time.time()-4
replay=done(request('/replays',{'task':task['id'],'model':ensemble['id'],'start':end-180,'end':end,'step':2}))
r=request('/replays/'+replay['id']);assert r['points'] and all(p['reference_kind']=='none' for p in r['points'])
note('platform-postprocess-ensemble-and-replay',postprocess=post['id'],ensemble=ensemble['id'])
if old:
 request('/tasks/'+task['id']+'/rollback',{});assert next(t for t in request('/state')['tasks'] if t['id']==task['id'])['active_model']==old
 request('/tasks/'+task['id']+'/publish',{'model':model['id']})
note('legacy-online-model-rollback-preserved')
out.update(passed=True,task=task['id'],model=model['id'],platform_id=info['platform_id'],recorded_at=time.time())
Path('/data/evidence/v5.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2),flush=True)
