"""Run inside service via stdin. Mutates only simulated GPU and v2 detectors."""
import json,time
from pathlib import Path
from urllib.error import HTTPError
from gpu_ml.cli import request,wait

out={'scope':'v2 simulated GPU / actual Prometheus and Nightingale','production_admitted':False,'cases':[]}
entity='gpu-ml-simulation|GPU-ML-SIM-0000'
request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
uni={'entities':[entity],'metrics':['gpu_temp','power'],'kind':'univariate'}
joint={'entities':[entity],'metrics':['gpu_temp','power','sm_clock','util'],'kind':'multivariate'}
a=request('/policies',uni);b=request('/policies',joint)
again=request('/policies',uni);assert len(again['created'])==0 and len(again['skipped'])==2
state=request('/state');tasks=[t for t in state['tasks'] if t['entity']==entity and t.get('policy_kind')]
assert len(tasks)==3
out['cases'].append({'name':'batch-expand-and-idempotence','passed':True,'detectors':len(tasks)})
try:request('/policies',uni,role='viewer');raise AssertionError('viewer write allowed')
except HTTPError as e:assert e.code==403
try:request('/policies',{'entities':[entity],'metrics':['not_metric'],'kind':'univariate'});raise AssertionError('invalid metric allowed')
except HTTPError as e:assert e.code==400
for task in tasks:
 end=time.time()-5
 job=request('/training-jobs',{'task':task['id'],'algorithm':task['algorithm'],'start':end-1800,'end':end,'step':2})
 s=wait(lambda s:any(j['id']==job['id'] and j['status'] in ('completed','failed') for j in s['jobs']),'v2 training',90)
 job=next(j for j in s['jobs'] if j['id']==job['id']);assert job['status']=='completed',job
 model=next(m for m in s['models'] if m['id']==job['model_id'])
 assert model['status']=='validated',model['report']
 request('/tasks/'+task['id']+'/publish',{'model':model['id']})
 out['cases'].append({'name':'train-publish','task':task['id'],'algorithm':task['algorithm'],'samples':model['report']['samples'],'model':model['id'],'passed':True})
 s=wait(lambda s:any(x['id']==task['id'] and x['quality']=='valid' for x in s['states']),'v2 online result',60)
 series=request('/series/'+task['id']+'?start='+str(time.time()-90)+'&end='+str(time.time()))
 assert series['points'];p=series['points'][-1];assert 'contributions' in p and 'reference_kind' in p
 replay=request('/replays',{'task':task['id'],'model':model['id'],'start':end-120,'end':end,'step':2})
 rs=wait(lambda s:any(j['id']==replay['id'] and j['status'] in ('completed','failed') for j in s['jobs']),'v2 replay')
 rjob=next(j for j in rs['jobs'] if j['id']==replay['id']);assert rjob['status']=='completed',rjob
out['cases'].append({'name':'online-and-replay-result-contract','passed':True})
bindings=request('/integrations/nightingale/sync',{})
temp=next(t for t in tasks if t['template']=='uni_gpu_temp');rid=next(b['rule_id'] for b in bindings if b['id']==temp['id'])
try:
 request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'temperature_spike'})
 s=wait(lambda s:any(x['id']==temp['id'] and x.get('active') for x in s['states']) and any(e['rule_id']==rid for e in s['nightingale'].get('events',[])),'new detector native event',90)
 event=next(e for e in s['nightingale']['events'] if e['rule_id']==rid)
 out['cases'].append({'name':'v2-native-nightingale-event','passed':True,'event_id':event['id'],'rule_id':rid,'hash':event['hash']})
finally:request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
wait(lambda s:any(x['id']==temp['id'] and not x.get('active') and x['quality']=='valid' for x in s['states']) and not any(e['rule_id']==rid for e in s['nightingale'].get('events',[])),'normal recovery',120)
out.update(passed=True,recorded_at=time.time())
Path('/data/evidence/v2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
