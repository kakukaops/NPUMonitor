"""Postflight audit against raw native trigger timestamps and safe exit contract."""
from datetime import datetime
import json
from pathlib import Path
from suite import request

path=Path('/results/batch1-all.json')
report=json.loads(path.read_text())
assert report['passed'],'full suite has not passed'
records=request('http://notification-receiver:9080/events')['events']

def raw_record(evidence):
    found=[]
    for record in records:
        if abs(datetime.fromisoformat(record['received_at']).timestamp()-evidence['received_at'])>.01:
            continue
        for event in record['payload'] if isinstance(record['payload'],list) else []:
            if event.get('hash')==evidence['hash'] and not event.get('is_recovered'):
                found.append(event)
    assert len(found)==1,'native firing evidence unavailable'
    return found[0]

checked=[]
for case in report['cases']:
    if case['scenario'] in ('sram','remap','transient_invalid','sram_then_field_missing'):
        continue
    for evidence in case['firing']:
        event=raw_record(evidence)
        latency=event['trigger_time']-case['started_at']
        assert latency>=58,(case['scenario'],latency,'native trigger before desired hold time')
        assert event['prom_for_duration']==90 and event['prom_eval_interval']==30
        checked.append({'scenario':case['scenario'],'hash':event['hash'],
                        'native_trigger_after_seconds':round(latency,3)})
case=next(c for c in report['cases'] if c['scenario']=='sram_then_field_missing')
ex=case['raw_exit'];normalized=[]
for record in records:
    if abs(datetime.fromisoformat(record['received_at']).timestamp()-ex['received_at'])>.01:continue
    normalized += [n for n in record.get('interpretations',[]) if n.get('hash')==ex['hash'] and n['raw_nightingale_is_recovered']]
assert len(normalized)==1,'safe exit notification evidence unavailable'
n=normalized[0]
assert n['state']=='condition_exited' and n['end_reason']=='unverified_condition_exit'
assert n['hardware_recovery_confirmed'] is False
assert '不能据此判断硬件修复' in n['message']
report['postflight_audit']={'passed':True,'native_trigger_timings':checked,
                           'hardware_input_loss_exit_notification':n}
path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('PASS: native trigger timestamps meet >=60s target (2s tolerance); input-loss exit does not claim repair')
