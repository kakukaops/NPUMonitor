#!/usr/bin/env python3
"""Whole-stack synthetic acceptance. No existing-system credentials or targets."""
import argparse,json,subprocess,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[5];PRIVATE=ROOT/'.local/npumonitor-rules-contract';MODULE=ROOT/'modules/devices/nvidia-gpu/rules'
ADMIN=(PRIVATE/'admin-token').read_text().strip();N9E=(PRIVATE/'n9e-token').read_text().strip();CFG=json.loads((PRIVATE/'config.json').read_text());GROUP=CFG['nightingale']['group_id']
COMPOSE=['docker','compose','-f',str(ROOT/'deploy/nvidia-gpu/rules/reference/compose.yaml')]
REPORT={'scope':'isolated synthetic input; actual Prometheus, runtime, Nightingale and receiver','started_at':time.time(),'cases':[],'passed':False}

def request(base,path,body=None,method=None,token=ADMIN):
    headers={'Content-Type':'application/json','Authorization':'Bearer '+token}
    if base==17001:headers={'Content-Type':'application/json','X-User-Token':N9E}
    req=Request('http://127.0.0.1:'+str(base)+path,data=None if body is None else json.dumps(body).encode(),method=method or ('POST' if body is not None else 'GET'),headers=headers)
    with urlopen(req,timeout=20) as f:payload=json.load(f)
    if base==17001 and isinstance(payload,dict):
        if payload.get('err') or payload.get('error'):raise ValueError('isolated Nightingale API error')
        return payload.get('dat',payload.get('data',payload))
    return payload

def wait(predicate,label,timeout=60):
    end=time.monotonic()+timeout;last=None
    while time.monotonic()<end:
        try:
            value=predicate()
            if value:return value
        except (HTTPError,TimeoutError,ConnectionError,OSError) as exc:last=type(exc).__name__
        time.sleep(1)
    raise AssertionError(label+(' ('+str(last)+')' if last else ''))
def scenario(name,**extra):request(19471,'/control',{'scenario':name,**extra})
def states():
    result=[]
    for offset in range(0,300000,1000):
        page=request(19470,'/state?limit=1000&offset='+str(offset))['states'];result.extend(page)
        if len(page)<1000:return result
    raise AssertionError('state pagination quota exceeded')
def state(key):return next((r for r in states() if r['rule_id']=='os_sre.'+key and r['identity'].get('UUID')=='GPU-CONTRACT-0000'),None)
def active(key):
    row=state(key);return row if row and row['active'] else None

def receipts():return request(19473,'/state')['receipts']
def events():
    out=[]
    for receipt in receipts():
        body=receipt['body']
        if isinstance(body,list):
            for e in body:
                if isinstance(e,dict):out.append(dict(e,_received_at=receipt['at']))
    return out

def notice(key,recovered,since):
    for e in events():
        tags=e.get('tags_map') or dict(t.split('=',1) for t in e.get('tags',[]) if '=' in t)
        if tags.get('sre_rule_id')=='os_sre.'+key and e.get('is_recovered') is recovered and e['_received_at']>=since and tags.get('UUID')=='GPU-CONTRACT-0000':return e
    return None

def passed(name,**details):
    REPORT['cases'].append({'name':name,'passed':True,**details});print('PASS: '+name,flush=True)

def command(*args):subprocess.run(COMPOSE+list(args),check=True,stdout=subprocess.DEVNULL)
def baseline():
    scenario('baseline');wait(lambda:request(19470,'/ready').get('ready'),'baseline runtime ready')

def basic():
    baseline();since=time.time();scenario('hot')
    row=wait(lambda:active('gpu_thermal'),'temperature source duration confirmation')
    fired=wait(lambda:notice('gpu_thermal',False,since),'actual Nightingale firing notification')
    assert not any(r['active'] for r in states() if r['rule_id']=='os_sre.gpu_thermal' and r['identity'].get('UUID')=='GPU-CONTRACT-0001')
    passed('thermal_firing_and_device_isolation',episode=row['episode'],nightingale_hash=fired['hash'])
    scenario('missing');wait(lambda:active('entity_missing'),'expected missing card notification')
    retained=state('gpu_thermal');assert retained['active'] and retained['episode']==row['episode']
    assert not notice('gpu_thermal',True,since)
    passed('missing_data_preserves_same_active_episode',episode=retained['episode'])
    command('restart','sre-runtime');wait(lambda:request(19470,'/health').get('alive'),'runtime restart')
    retained=state('gpu_thermal');assert retained['active'] and retained['episode']==row['episode']
    passed('actual_runtime_restart_preserves_active_incident')
    recovery_since=time.time();scenario('baseline');wait(lambda:not active('gpu_thermal'),'valid thermal clear')
    recovered=wait(lambda:notice('gpu_thermal',True,recovery_since),'actual Nightingale recovery notification')
    assert recovered['hash']==fired['hash'];passed('valid_recovery_correlates_same_nightingale_hash')
    since=time.time();scenario('xid');row=wait(lambda:active('xid_node'),'XID firing')
    wait(lambda:notice('xid_node',False,since),'XID Nightingale event')
    scenario('baseline');time.sleep(5);assert active('xid_node')
    for attempt in range(8):
        row=active('xid_node')
        try:
            receipt=request(19470,'/admin/recovery',{'rule_id':row['rule_id'],'identity':row['identity'],'expected_revision':row['revision'],'reason':'isolated synthetic OS recovery review'})
            break
        except HTTPError as exc:
            if exc.code!=409:raise
    assert receipt['forced_clear'] is False
    wait(lambda:not active('xid_node'),'XID code zero plus explicit operation evidence')
    passed('xid_requires_episode_scoped_operator_evidence')
    result=command('exec','-T','sre-runtime','python','-m','npumonitor_rules.cli','sync')
    result=json.loads(subprocess.check_output(COMPOSE+['exec','-T','sre-runtime','python','-m','npumonitor_rules.cli','sync-plan']))
    assert all(i['action']=='unchanged' for i in result['items']);passed('actual_nightingale_sync_is_idempotent',managed_objects=len(result['items']))


def any_active(key):return [r for r in states() if r['rule_id']=='os_sre.'+key and r['active']]
def expect(keys,enabled=True,timeout=65):
    for key in keys:wait(lambda key=key:bool(any_active(key))==enabled,key+(' firing' if enabled else ' clear'),timeout)
def matrix():
    baseline()
    def override(metric,value):return {'metric':metric,'value':value}
    flags=['sram','remap_failed','remap_pending','gpu_thermal','memory_thermal','switch_thermal','sw_thermal','hw_thermal','power_cap','power_brake','hw_slowdown','sync_boost','clock_unknown']
    scenario('baseline',overrides=[override(k,v) for k,v in {
      'DCGM_FI_DEV_SRAM_EXCEEDED':1,'DCGM_FI_DEV_ROW_REMAP_FAILURE':1,'DCGM_FI_DEV_ROW_REMAP_PENDING':1,
      'DCGM_FI_DEV_GPU_TEMP':100,'DCGM_FI_DEV_MEMORY_TEMP':120,'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT':100,
      'DCGM_FI_DEV_CLOCKS_EVENT_REASONS':764}.items()])
    expect(flags);passed('hardware_flags_thermal_and_clock_bits',rules=flags)
    scenario('baseline');expect(flags,False)
    passed('hardware_flags_valid_clear')
    counters={'ecc_new':'DCGM_FI_DEV_ECC_DBE_VOL_TOTAL','thermal_time':'DCGM_FI_DEV_THERMAL_VIOLATION',
      'pcie_replay':'DCGM_FI_DEV_PCIE_REPLAY_COUNTER','nvlink_crc':'DCGM_FI_DEV_NVLINK_CRC_ERROR_COUNT_TOTAL',
      'nvlink_recovery':'DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL','nvlink_replay':'DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL',
      'switch_replay':'DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERRORS','switch_recovery':'DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERRORS'}
    # Names are taken from the deployed contract rather than fabricated aliases.
    catalog=json.loads((MODULE/'monitoring/os-sre/catalog.json').read_text())
    for key in counters:
        rule=next(r for r in catalog['rules'] if r['rule_id']=='os_sre.'+key)
        candidates=[m for m in catalog['metric_contracts'] if m in rule.get('expression',rule.get('expr','')) and catalog['metric_contracts'][m]['kind']=='counter']
        if candidates:counters[key]=candidates[0]
    scenario('baseline',counter_activity=[{'metric':m,'delta':1} for m in counters.values()]);expect(list(counters))
    passed('counter_activity_window_firing',rules=list(counters))
    scenario('baseline');expect(list(counters),False,80);passed('counter_activity_window_quiet_clear')
    links=['gpu_link_down','switch_link_down','fabric_manager','fabric_health']
    scenario('baseline',overrides=[override(k,v) for k,v in {'DCGM_FI_DEV_NVLINK_GET_STATE':0,'DCGM_FI_DEV_NVSWITCH_LINK_STATUS':0,'DCGM_FI_DEV_FABRIC_MANAGER_STATUS':4,'DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY':2}.items()]);expect(links)
    passed('link_and_fabric_failure_states',rules=links)
    scenario('baseline');expect(links,False)
    for name,key in [('invalid','input_invalid'),('duplicate','input_duplicate'),('scrape_error','collector_down'),('nightingale_metrics_error','platform_nightingale_metrics_missing'),('evaluation_stall','platform_evaluation_stall')]:
        scenario(name);expect([key],timeout=90);passed(name+'_native_detection');scenario('baseline');expect([key],False,80)
    scenario('baseline',omit=[{'metric':'DCGM_FI_DEV_GPU_TEMP','identity':{'UUID':'GPU-CONTRACT-0000'}}]);expect(['field_missing']);passed('partial_field_missing');scenario('baseline');expect(['field_missing'],False)
    scenario('pcie');started=time.monotonic();time.sleep(10);assert not any_active('pcie_degraded')
    expect(['pcie_degraded'],timeout=145);elapsed=time.monotonic()-started
    passed('pcie_120_second_confirmation',observed_seconds=round(elapsed,2))
    scenario('pcie_idle');time.sleep(5);assert any_active('pcie_degraded');passed('idle_link_downshift_does_not_claim_recovery')
    scenario('pcie_active_normal');expect(['pcie_degraded'],False);scenario('baseline')
    passed('active_normal_pcie_clears')

def operations():
    baseline()
    def watcher(target,status,since):
        return next((r['body'] for r in receipts() if r['at']>=since and isinstance(r['body'],dict) and r['body'].get('kind')=='npumonitor_watchdog' and r['body'].get('target')==target and r['body'].get('status')==status),None)
    since=time.time()
    try:
        request(19473,'/control',{'fail':True});command('stop','sre-runtime')
        wait(lambda:request(19472,'/health').get('pending_deliveries',0)>0,'independent watcher persisted pending firing',60)
        command('restart','sre-watchdog');time.sleep(5)
        assert request(19472,'/health')['pending_deliveries']>0
        request(19473,'/control',{'fail':False})
        firing=wait(lambda:watcher('rule-gateway','firing',since),'watcher retried firing after receiver recovery')
        command('start','sre-runtime');wait(lambda:request(19470,'/ready').get('ready'),'runtime ready after stop')
        resolved=wait(lambda:watcher('rule-gateway','resolved',since),'watcher corresponding component recovery')
        assert firing['episode']==resolved['episode'];passed('actual_watchdog_restart_persistent_retry_and_correlated_recovery')
        since=time.time();command('stop','sre-nightingale')
        firing=wait(lambda:watcher('nightingale','firing',since),'watcher independent of stopped Nightingale',75)
        command('start','sre-nightingale');resolved=wait(lambda:watcher('nightingale','resolved',since),'Nightingale component restored',90)
        assert firing['episode']==resolved['episode'];passed('independent_notice_when_nightingale_is_stopped')
        wait(lambda:request(19470,'/ready').get('ready'),'runtime recovered preflight',90)
        request(19473,'/control',{'fail':True});scenario('hot')
        expect(['gpu_thermal']);time.sleep(8);scenario('baseline');expect(['gpu_thermal'],False);time.sleep(8);scenario('hot')
        time.sleep(12)
        capability=request(19470,'/status')['coverage']['rules']['os_sre.platform_notify_failure']['status']
        attempts=request(19473,'/state')['attempts'];failed=sum(a['status']==503 and a['at']>=since for a in attempts)
        assert failed>0
        if capability=='ready':
            expect(['platform_notify_failure'],timeout=45);passed('native_nightingale_failed_notification_counter_detection')
        else:
            REPORT['coverage_gaps']=[{'rule':'os_sre.platform_notify_failure','status':capability,'failed_http_deliveries':failed,'reason':'tested native notification path did not expose the expected counter; rule must remain disabled'}]
            passed('notification_failure_input_gap_detected_without_fabricating_health',failed_deliveries=failed,capability=capability)
    finally:
        request(19473,'/control',{'fail':False});command('start','sre-runtime','sre-nightingale');scenario('baseline')

def release():
    baseline();scenario('hot');row=wait(lambda:active('gpu_thermal'),'active incident before release')
    old_status=request(19470,'/status')['state'];oldsha=old_status['bundle_sha'];generation=old_status['generation']
    candidate=PRIVATE/'bundle.json';original=candidate.read_bytes();config=PRIVATE/'release-test.json'
    def cli(*args):return json.loads(subprocess.check_output(COMPOSE+['exec','-T','sre-runtime','python','-m','npumonitor_rules.cli',*args]))
    try:
        candidate.write_text('{}');candidate.chmod(0o600)
        try:request(19470,'/plan');raise AssertionError('invalid candidate accepted')
        except HTTPError as exc:assert exc.code==422
        assert request(19470,'/ready')['ready'];assert active('gpu_thermal')['episode']==row['episode']
        passed('invalid_candidate_does_not_replace_active_release')
        cfg=json.loads(json.dumps(CFG));cfg.setdefault('rule_overrides',{})['os_sre.gpu_thermal']={'severity':3}
        config.write_text(json.dumps(cfg));config.chmod(0o600)
        import os
        env=dict(os.environ,PYTHONPATH=str(MODULE/'runtime/src'))
        subprocess.run(['python','-m','npumonitor_rules.cli','compile','--config',str(config),'--output',str(candidate)],env=env,check=True,stdout=subprocess.DEVNULL)
        plan=request(19470,'/plan');assert plan['current_sha']==oldsha
        result=request(19470,'/admin/activate',{'expected_generation':generation,'reason':'isolated synthetic release validation'})
        assert result['generation']==generation+1
        try:request(19470,'/admin/activate',{'expected_generation':generation,'reason':'stale revision validation'});raise AssertionError('stale revision accepted')
        except HTTPError as exc:assert exc.code==409
        assert active('gpu_thermal')['episode']==row['episode']
        cli('sync');passed('actual_release_activation_cas_and_incident_preservation')
        request(19470,'/admin/rollback',{'sha256':oldsha,'expected_generation':generation+1,'reason':'isolated rollback validation'});cli('sync')
        assert request(19470,'/status')['state']['bundle_sha']==oldsha
        assert active('gpu_thermal')['episode']==row['episode'];passed('actual_release_rollback_preserves_incident')
        backup=request(19470,'/admin/backup',{})
        restored=cli('restore','--archive',backup['file'],'--sha256',backup['sha256'],'--target','/tmp/restore-acceptance-'+str(int(time.time())))
        assert restored['restored'];passed('online_backup_checksum_verified_empty_target_restore',sha256=backup['sha256'])
    finally:
        candidate.write_bytes(original);candidate.chmod(0o600);config.unlink(missing_ok=True);scenario('baseline')

def capacity():
    baseline();scenario('baseline',gpu_count=100)
    wait(lambda:len({r['identity'].get('UUID') for r in states() if r['identity'].get('UUID')})>=100,'100 GPU state population',90)
    samples=[]
    for _ in range(15):
        value=request(19470,'/status');samples.append({'at':time.time(),'ready':value['ready'],'cycle_seconds':value['last_cycle_seconds'],'source_stats':value['source_stats'],'errors':value['state']['errors']});time.sleep(2)
    resources=subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}','npumonitor-rules-contract-sre-runtime-1']).decode().strip()
    assert all(s['ready'] and not s['errors'] for s in samples)
    elapsed=samples[-1]['at']-samples[0]['at'];qps=(samples[-1]['source_stats']['requests']-samples[0]['source_stats']['requests'])/elapsed
    passed('100_gpu_synthetic_capacity',duration_seconds=round(elapsed,2),query_requests_per_second=round(qps,2),max_cycle_seconds=max(s['cycle_seconds'] for s in samples),asset_inventory_scope='two GPUs with PCIe/fabric/link inventory; raw metrics and inventory-independent detection for 100 GPUs',status_samples=samples,container_resources=json.loads(resources))
    scenario('baseline',gpu_count=2)

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=['basic','matrix','operations','release','capacity'],default='basic');args=p.parse_args()
    try:globals()[args.case]();REPORT['passed']=True
    except Exception as exc:
        REPORT['failure_reason']=type(exc).__name__+': '+str(exc);raise
    finally:
        REPORT['finished_at']=time.time();folder=MODULE/'runtime/evidence';folder.mkdir(exist_ok=True);(folder/(args.case+'.json')).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
