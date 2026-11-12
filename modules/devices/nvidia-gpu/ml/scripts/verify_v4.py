"""DCGM-only scenarios: actual Prometheus history and native Nightingale, lab only."""
import json,time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from gpu_ml.cli import request,wait

uid='GPU-ML-SIM-0001';entity='gpu-ml-simulation|'+uid
out={'scope':'DCGM-only / real Prometheus and Nightingale / accelerated simulated drift','production_admitted':False,'cases':[]}

def record(name,**values):
 c={'name':name,'passed':True,**values};out['cases'].append(c);print(json.dumps(c,ensure_ascii=False),flush=True)
def switch(mode):request('/simulation',{'uuid':uid,'scenario':mode})
def done(job):
 s=wait(lambda s:any(j['id']==job['id'] and j['status'] in ('completed','failed') for j in s['jobs']),'scenario training',120)
 j=next(j for j in s['jobs'] if j['id']==job['id']);assert j['status']=='completed',j;return j

def state(s,scene):return next(x for x in s['states'] if x['id']==tasks[scene]['id'])
def normal_all(s):return all(state(s,k)['quality']=='valid' and not state(s,k).get('active') for k in tasks)

s=request('/state');assert s['simulation'];catalog=s['dcgm_scenarios'];scenes=list(catalog['scenarios']);switch('normal')
request('/scenario-policies',{'entities':[entity],'scenarios':scenes,'profile':'production'})
created=request('/scenario-policies',{'entities':[entity],'scenarios':scenes,'profile':'laboratory'})
repeat=request('/scenario-policies',{'entities':[entity],'scenarios':scenes,'profile':'laboratory'});assert not repeat['created'] and len(repeat['skipped'])==4
s=request('/state');tasks={t['scenario_id']:t for t in s['tasks'] if t.get('scenario_profile')=='laboratory' and t['entity']==entity}
assert len(tasks)==4 and all(t['notification_mode']=='evidence' for t in tasks.values())
production=next(t for t in s['tasks'] if t.get('scenario_profile')=='production' and t.get('scenario_id')=='thermal_degradation' and t['entity']==entity)
end=time.time()-4
try:request('/training-jobs',{'task':production['id'],'algorithm':production['algorithm'],'start':end-3600,'end':end,'step':2});raise AssertionError('short production history accepted')
except HTTPError as e:assert e.code==400
try:request('/scenario-policies',{'entities':[entity],'scenarios':scenes,'profile':'laboratory'},role='viewer');raise AssertionError('viewer write')
except HTTPError as e:assert e.code==403
other=next((e for e in s['entities'] if e['source_type']!='simulated'),None)
if other:
 try:request('/scenario-policies',{'entities':[other['id']],'scenarios':scenes,'profile':'laboratory'});raise AssertionError('real GPU laboratory allowed')
 except HTTPError as e:assert e.code==400
record('catalog-idempotence-role-and-profile-guards',scenarios=scenes)
for scene,t in tasks.items():
 end=time.time()-4
 j=done(request('/training-jobs',{'task':t['id'],'algorithm':t['algorithm'],'start':end-3600,'end':end,'step':2}))
 model=next(m for m in request('/state')['models'] if m['id']==j['model_id'])
 assert model['status']=='validated',model['report']
 request('/tasks/'+t['id']+'/publish',{'model':model['id']});tasks[scene]['active_model']=model['id']
 record('train-publish-'+scene,model=model['id'],samples=model['report']['samples'])
wait(normal_all,'fresh normal scenario results',120)
bindings=request('/integrations/nightingale/sync',{})
thermal=tasks['thermal_relation'];rid=next(b['rule_id'] for b in bindings if b['id']==thermal['id'])
try:
 switch('temperature_spike')
 wait(lambda s:state(s,'thermal_relation').get('active'),'conditional temperature deviation',60)
 query='gpu_ml_active{detector_id="'+thermal['id']+'"} == 1'
 gateway=json.load(urlopen('http://localhost:9460/api/v1/query?'+urlencode({'query':query})))
 assert gateway['data']['result']==[]
 assert not any(e['rule_id']==rid for e in request('/state')['nightingale'].get('events',[]))
 record('evidence-only-does-not-notify')
 try:request('/tasks/'+thermal['id']+'/admission',{'mode':'alert','evidence_ref':'test','owner':'lab','action':'inspect'},role='operator');raise AssertionError('operator admission allowed')
 except HTTPError as e:assert e.code==403
 request('/tasks/'+thermal['id']+'/admission',{'mode':'alert','evidence_ref':'accelerated laboratory acceptance only','owner':'local test','action':'inspect conditional DCGM residual, not a hardware diagnosis'})
 request('/integrations/nightingale/sync',{})
 s=wait(lambda s:any(e['rule_id']==rid for e in s['nightingale'].get('events',[])),'admitted native event',90)
 event=next(e for e in s['nightingale']['events'] if e['rule_id']==rid)
 switch('missing');time.sleep(8)
 s=request('/state');assert state(s,'thermal_relation')['active'] and state(s,'thermal_relation')['quality']=='missing'
 record('manual-admission-native-event-and-missing-hold',event_id=event['id'],rule_id=rid,hash=event['hash'])
 switch('normal')
 wait(lambda s:normal_all(s) and not any(e['rule_id']==rid for e in s['nightingale'].get('events',[])),'normal comparable history recovery',180)
 request('/tasks/'+thermal['id']+'/admission',{'mode':'evidence'});request('/integrations/nightingale/sync',{})
 switch('high_load');time.sleep(30)
 s=request('/state');assert not state(s,'thermal_relation')['active'] and state(s,'thermal_relation')['quality']=='valid',state(s,'thermal_relation')
 record('normal-high-load-counterexample')
 switch('normal');wait(normal_all,'restore baseline after high load',150)
 for injection,scene in [('thermal_aging','thermal_degradation'),('clock_aging','clock_degradation')]:
  started=time.time();switch(injection)
  s=wait(lambda s:state(s,scene).get('active') and state(s,scene)['quality']=='valid','accelerated '+scene,120)
  evidence=state(s,scene)['evidence'];assert evidence['profile']=='laboratory' and evidence['window_seconds']==60
  record('accelerated-'+scene,detection_seconds=round(time.time()-started,2),evidence=evidence)
  switch('normal');wait(normal_all,'remove accelerated drift and rebuild window',180)
 switch('idle');time.sleep(28)
 s=request('/state');assert all(state(s,k)['quality'] in ('outside_reference','reference_window_incomplete') for k in tasks)
 record('unseen-load-abstains-instead-of-healthy-or-fault')
finally:
 switch('normal')
 request('/tasks/'+thermal['id']+'/admission',{'mode':'evidence'})
wait(normal_all,'final normal evidence',180)
out.update(passed=True,recorded_at=time.time())
Path('/data/evidence/v4.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)
