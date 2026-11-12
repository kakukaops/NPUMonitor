"""Post-image-replacement checks, extra relation injection and offline restore."""
from gpu_ml.cli import request,wait,restore
from gpu_ml.pipeline import load_artifact
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path
import json,time,tempfile,sqlite3

uid='GPU-ML-SIM-0001';entity='gpu-ml-simulation|'+uid
before=json.loads(Path('/data/evidence/v4-before.json').read_text())
def scene_tasks(s):return {t['scenario_id']:t for t in s['tasks'] if t.get('scenario_profile')=='laboratory' and t['entity']==entity}
def good(s):
 tasks=scene_tasks(s)
 return len(tasks)==4 and all(any(x['id']==t['id'] and x['quality']=='valid' and not x.get('active') for x in s['states']) for t in tasks.values())
s=wait(good,'v4 normal windows after image/container replacement',180)
for t in s['tasks']:
 if t['id'] in before['tasks']:
  old=before['tasks'][t['id']];assert t.get('active_model')==old['model'] and t['notification_mode']==old['mode'] and t['scenario_profile']==old['profile']
health=json.load(urlopen('http://localhost:9460/health'));assert health['version']=='0.4.0'
try:request('/tasks',{'name':'bypass-test','entity':entity,'template':'dcgm_thermal_relation_laboratory','algorithm':'dcgm_conditional'});raise AssertionError('advanced route bypass')
except HTTPError as e:assert e.code==400
print('Restart, profile/configuration persistence, advanced-route guard passed',flush=True)
tasks=scene_tasks(s);power=tasks['power_clock_relation']
try:
 started=time.time();request('/simulation',{'uuid':uid,'scenario':'power_clock'})
 active=wait(lambda s:any(x['id']==power['id'] and x['quality']=='valid' and x.get('active') for x in s['states']),'DCGM conditional power/clock deviation',60)
 power_case={'passed':True,'detection_seconds':round(time.time()-started,2),'task':power['id']}
 print('Additional power/clock online injection passed',flush=True)
finally:request('/simulation',{'uuid':uid,'scenario':'normal'})
s=wait(good,'fresh comparable source windows after power/clock restoration',180)
for task in scene_tasks(s).values():
 points=request('/series/'+task['id']+'?start='+str(time.time()-180)+'&end='+str(time.time()))['points']
 assert points and 'job_running' not in points[-1]['values']
proof=json.loads(Path('/data/evidence/v4.json').read_text());h=next(c['hash'] for c in proof['cases'] if c['name']=='manual-admission-native-event-and-missing-hold')
notifications=[]
for row in json.load(urlopen('http://notification-receiver:9080/events'))['events']:
 p=row['payload'];entries=p if isinstance(p,list) else p.get('events',[]) if isinstance(p,dict) else []
 for e in entries:
  if e.get('hash')==h:notifications.append({k:e.get(k) for k in ('id','rule_id','hash','trigger_time','is_recovered')})
assert any(e['is_recovered'] for e in notifications) and any(not e['is_recovered'] for e in notifications)
backup=request('/backups',{});count=0
with tempfile.TemporaryDirectory(prefix='gpu-ml-v4-restore-') as tmp:
 root=Path(tmp)/'restored';restore(Path('/data/backups')/(backup['id']+'.tar.gz'),root)
 db=sqlite3.connect(root/'gpu-ml.sqlite');records=[json.loads(r[0]) for r in db.execute("SELECT payload FROM documents WHERE kind='model'")];db.close()
 for record in records:
  if not record.get('feature_schema',{}).get('scenario'):continue
  model=load_artifact(root/'models'/record['artifact'],record['sha256'])
  rows=json.loads((root/'snapshots'/record['snapshot']).read_text());assert model.predict(rows[-200:]);count+=1
assert count>=4
final={'passed':True,'version':'0.4.0','scenario_tasks_preserved':len(before['tasks']),'lab_models_restored_and_scored':count,'advanced_route_guard':'passed','dcgm_only_online_values':'passed',
 'additional_power_clock_injection':power_case,'notifications':notifications,'new_scenarios_final_mode':'evidence','new_scenarios_final_active':0,'ready':urlopen('http://localhost:9460/ready').status,
 'real_hardware_degradation':'not_run','production_admitted':False,'recorded_at':time.time()}
Path('/data/evidence/v4-final.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n')
task=tasks['thermal_degradation'];fixture={'state':s,'series':request('/series/'+task['id']+'?start='+str(time.time()-900)+'&end='+str(time.time()))}
Path('/data/evidence/v4-ui-fixture.json').write_text(json.dumps(fixture))
print(json.dumps({k:v for k,v in final.items() if k!='notifications'},ensure_ascii=False),flush=True)
