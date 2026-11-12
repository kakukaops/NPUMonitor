"""Run inside the service: gateway error semantics and native platform/quality events."""
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import urlopen
from gpu_ml.cli import request,wait

result={'scope':'native-platform-and-quality-alerts','cases':[],'production_admitted':False}

def task(s):return next(x for x in s['states'] if x['id']=='sim-0-thermal')

def event(s,rid):return next((e for e in s['nightingale'].get('events',[]) if e['rule_id']==rid),None)

try:
    bindings=request('/state')['bindings'];rid=next(b['rule_id'] for b in bindings if b['id']=='sim-0-thermal')
    platform=next(b['rule_id'] for b in bindings if b['id']=='platform');quality=next(b['rule_id'] for b in bindings if b['id']=='quality')
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'temperature_spike'})
    active=wait(lambda s:task(s)['active'] and event(s,rid),'模型异常及夜莺事件',75)
    original=event(active,rid)
    request('/system/inference',{'enabled':False})
    time.sleep(18)
    expression='gpu_ml_active{detector_id="sim-0-thermal"} == 1'
    from urllib.parse import urlencode
    try:urlopen('http://localhost:9460/api/v1/query?'+urlencode({'query':expression}));raise AssertionError('stale gateway returned success')
    except HTTPError as exc:assert exc.code==503
    stopped=wait(lambda s:event(s,platform) is not None,'平台停滞夜莺告警',75)
    assert event(stopped,rid)['id']==original['id'] and task(stopped)['active']
    result['cases'].append({'name':'inference-stall-503-and-native-platform-alert','passed':True,'business_event_preserved':original['id']})
    request('/system/inference',{'enabled':True})
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
    wait(lambda s:not task(s)['active'] and event(s,rid) is None and event(s,platform) is None,'恢复业务与平台状态',75)
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'missing'})
    missing=wait(lambda s:task(s)['quality']=='missing' and event(s,quality) is not None,'输入质量原生事件',75)
    assert not task(missing)['active']
    result['cases'].append({'name':'input-missing-native-quality-alert','passed':True,'event_id':event(missing,quality)['id']})
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
    wait(lambda s:task(s)['quality']=='valid' and event(s,quality) is None,'输入质量恢复',75)
    result.update(passed=True,recorded_at=time.time())
    Path('/data/evidence/platform.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
finally:
    request('/system/inference',{'enabled':True})
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
