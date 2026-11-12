#!/usr/bin/env python3
"""Host-side test of persisted active incident identity across a real service restart."""
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[5]
COMPOSE=['docker','compose','-f',str(ROOT/'deploy/nvidia-gpu/ml/compose.yaml')]
TOKEN=(ROOT/'.local/gpu-ml-admin-token').read_text().strip()
BASE='http://127.0.0.1:19460/api/gpu-ml/v1'

def request(path,payload=None):
    req=Request(BASE+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN})
    with urlopen(req,timeout=10) as response:return json.load(response)

def wait(fn,title,timeout=90):
    end=time.time()+timeout
    while time.time()<end:
        try:
            s=request('/state')
            if fn(s):return s
        except OSError:pass
        time.sleep(2)
    raise AssertionError(title)

def state(s):return next(x for x in s['states'] if x['id']=='sim-0-thermal')

def event(s,rid):return next((e for e in s['nightingale'].get('events',[]) if e['rule_id']==rid),None)

try:
    before=request('/state');rid=next(b['rule_id'] for b in before['bindings'] if b['id']=='sim-0-thermal')
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'temperature_spike'})
    active=wait(lambda s:state(s)['active'] and event(s,rid),'实际夜莺告警未产生')
    original=event(active,rid);episode=state(active)['episode_id'];models={t['id']:t['active_model'] for t in active['tasks']}
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'missing'})
    wait(lambda s:state(s)['active'] and state(s)['quality']=='missing','缺失未保持')
    subprocess.run(COMPOSE+['restart','gpu-ml'],check=True)
    subprocess.run(COMPOSE+['up','-d','--no-deps','--wait','--wait-timeout','120','gpu-ml'],check=True,env={**__import__('os').environ,'GPU_ML_SIMULATION':'true'})
    restored=wait(lambda s:state(s)['active'] and state(s)['quality']=='missing' and event(s,rid),'重启后状态或事件未保留')
    after=event(restored,rid)
    assert after['id']==original['id'] and after['hash']==original['hash'] and state(restored)['episode_id']==episode
    assert all(t['active_model']==models[t['id']] for t in restored['tasks'])
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
    recovered=wait(lambda s:not state(s)['active'] and event(s,rid) is None,'重启后有效恢复未完成')
    result={'passed':True,'scope':'real container restart / simulated GPU / existing Nightingale',
            'active_event_id':original['id'],'hash':original['hash'],'episode_preserved':True,'models_preserved':True,
            'unknown_preserved_across_restart':True,'recovered_after_fresh_normal':True,'production_admitted':False,'recorded_at':time.time()}
    out=ROOT/'modules/devices/nvidia-gpu/ml/evidence/gpu/restart.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
finally:
    try:request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
    except OSError:pass
