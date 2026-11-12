"""Empirically verify native no-data recovery option on the deployed Prom path."""
import hashlib
import json
from pathlib import Path
import time
import n9e
from suite import request, notifications

GROUP='H100恢复策略实验'
report={'scope':'isolated_native_capability_probe','passed':False}
api=n9e.API();n9e.GROUP=GROUP
source=next(r for r in json.loads(Path('/rules/batch1-lab-catalog.json').read_text())['rules'] if r['key']=='batch1_sram_threshold_exceeded')
item=dict(source,key='recovery_probe_sram',name='恢复能力实验-缺数不恢复',
          eval_interval_seconds=5,recover_config={'judge_type':1},
          note='临时能力探测；仅本地模拟，不代表生产配置。')
changed=False
try:
    assert request('http://gpu-simulator:9400/batch1/state')['scenario']=='normal'
    n9e.install(api,{'catalog_version':'recovery-probe-0.1.0','rules':[item]})
    bg=n9e.unique(api.call('GET','/busi-groups?all=true&limit=1000'),GROUP)
    row=n9e.unique(api.call('GET',f'/busi-group/{bg["id"]}/alert-rules'),item['name'])
    assert row['rule_config']['queries'][0]['recover_config']=={'judge_type':1}
    assert row.get('annotations',{}).get('managed_by')=='gpu-alert-lab'
    assert row['rule_config']['queries'][0]['prom_ql']==item['expression']
    if row['disabled']:
        row['disabled']=0
        api.call('PUT',f'/busi-group/{bg["id"]}/alert-rule/{row["id"]}',row)
        time.sleep(8)
    report.update(rule_id=row['id'],group_id=bg['id'],configured_recover_config={'judge_type':1},
                  expression_sha256=hashlib.sha256(item['expression'].encode()).hexdigest())
    def active():
        return [e for e in api.call('GET',f'/alert-cur-events/list?bgid={bg["id"]}&hours=24&limit=100')['list'] if e['rule_id']==row['id']]
    def select(name):
        request('http://gpu-simulator:9400/batch1/scenario',{'name':name});print('探测场景：'+name,flush=True)
    changed=True;started=time.time();select('sram')
    deadline=time.monotonic()+70
    while not active():
        if time.monotonic()>deadline:raise TimeoutError('probe did not fire')
        time.sleep(2)
    fired=active()[0];report['fired_hash']=fired['hash']
    since=time.time();select('field_missing')
    deadline=time.monotonic()+42
    while time.monotonic()<deadline:time.sleep(2)
    remaining=active()
    exits=[e for _,e in notifications(since) if e.get('rule_id')==row['id'] and e.get('is_recovered')]
    report.update(native_no_data_hold_supported=bool(remaining) and not exits,
                  active_after_missing=bool(remaining),raw_exit_count=len(exits),
                  raw_exit_hashes=[e['hash'] for e in exits],passed=True)
    print('能力结果：'+json.dumps({k:report[k] for k in ['native_no_data_hold_supported','raw_exit_count']}),flush=True)
finally:
    if changed:
        request('http://gpu-simulator:9400/batch1/scenario',{'name':'normal'})
    if 'row' in globals() and row.get('annotations',{}).get('managed_by')=='gpu-alert-lab':
        row['disabled']=1
        api.call('PUT',f'/busi-group/{bg["id"]}/alert-rule/{row["id"]}',row)
    Path('/results/recovery-native-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
