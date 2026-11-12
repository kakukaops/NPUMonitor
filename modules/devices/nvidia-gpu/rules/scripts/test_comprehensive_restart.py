#!/usr/bin/env python3
"""Stop/restart only the dedicated adapter and verify durable live incident identity."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:19430'
COMPOSE=['docker','compose','-f',str(ROOT.parents[3]/'deploy/nvidia-gpu/lab/compose.yaml')]
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path,data=None):
    req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with OPENER.open(req,timeout=15) as response:return json.load(response)

def scenario(name):return request('/api/scenario',{'name':name})
def wait(predicate,title,timeout=100):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(1)
    raise TimeoutError(title)

def status():
    result=request('/api/status')
    if result.get('api_error'):raise RuntimeError(result['api_error'])
    return result

def current(rid):return next((r for r in status()['alerts'] if r['rule_id']==rid),None)
def backup(s,rid,recovered,incident):
    return any(e['rule_id']==rid and e['hash']==incident['hash'] and e['trigger_time']==incident['trigger_time'] and bool(e.get('is_recovered'))==recovered for r in s['backup_notifications'] for e in r['events'])

def main():
    report={'scope':'simulated_component_restart','passed':False,'cases':[]}
    ids=request('/api/status')['runtime'];hardware=ids['rule_ids']['training.sram'];component=ids['health_rule_ids']['platform_adapter_down'];derivative=ids['health_rule_ids']['platform_query_failure']
    try:
        scenario('recover');wait(lambda:not request('/api/status')['alerts'],'baseline')
        scenario('sram');original=wait(lambda:current(hardware),'SRAM firing')
        scenario('entity_missing')
        wait(lambda:any(s['rule_id']=='training.sram' and s['active'] and s['quality']!='valid' for s in request('/api/status')['lifecycle']['states']),'missing observation applied')
        subprocess.run(COMPOSE+['stop','comprehensive-lifecycle'],check=True)
        down=wait(lambda:current(component),'adapter outage alert')
        wait(lambda:backup(request('/api/status'),component,False,down),'backup firing notification')
        for _ in range(12):
            snapshot=status()
            live=next((e for e in snapshot['alerts'] if e['rule_id']==hardware),None)
            assert live and live['id']==original['id'] and live['hash']==original['hash']
            assert not any(e['rule_id']==derivative for e in snapshot['alerts']),'derivative query failure not suppressed'
            time.sleep(1)
        subprocess.run(COMPOSE+['start','comprehensive-lifecycle'],check=True)
        wait(lambda:not request('/api/status')['lifecycle'].get('unavailable'),'adapter restart')
        wait(lambda:not current(component),'adapter recovery')
        wait(lambda:backup(request('/api/status'),component,True,down),'backup recovery notification')
        live=current(hardware);assert live and live['id']==original['id']
        state=request('/api/status')['lifecycle'];assert any(s['rule_id']=='training.sram' and s['active'] for s in state['states'])
        scenario('recover');wait(lambda:not request('/api/status')['alerts'],'valid recovery')
        report.update(passed=True,hardware_event_id=original['id'],hardware_hash=original['hash'],component_event_id=down['id'],verified_rule_ids=['platform_adapter_down'])
        report['cases']=[{'scenario':'adapter_stop_restart_with_active_missing_input','passed':True,'derivative_query_alerts_suppressed':True,'same_event_identity':True,'backup_firing_and_recovery':True}]
        print('PASS: adapter outage / backup notification / derivative suppression / restart retains same incident / valid recovery')
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        raise
    finally:
        subprocess.run(COMPOSE+['start','comprehensive-lifecycle'],check=True)
        scenario('recover')
        path=ROOT.parents[3]/'.local/reports/comprehensive-restart.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
