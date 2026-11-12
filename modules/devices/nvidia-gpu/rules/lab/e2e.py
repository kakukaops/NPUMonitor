"""Temperature firing/recovery integration test via real receiver observations."""
import json
from datetime import datetime
from pathlib import Path
import sys
import time
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
changed_scenario = False
report = {'test': 'temperature-firing-recovery', 'started_at': time.time(), 'steps': [], 'passed': False}


def request(url, body=None):
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=raw, headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=10) as response:
        return json.load(response)


def scenario(name):
    state = request('http://gpu-simulator:9400/scenario', {'name': name})
    report['steps'].append({'scenario': name, 'at': time.time(), 'generation': state['generation']})
    print('场景：' + name, flush=True)


def events():
    records = request('http://notification-receiver:9080/events')['events']
    output = []
    for record in records:
        payload = record['payload']
        if isinstance(payload, list):
            for event in payload:
                if isinstance(event, dict):
                    event = dict(event)
                    event['_received_at'] = datetime.fromisoformat(record['received_at']).timestamp()
                    output.append(event)
    return output


def wait_event(recovered, since, timeout=150):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in events():
            if (event.get('rule_name') == 'GPU实验-温度超限示范' and
                event.get('_received_at', 0) >= since and
                event.get('is_recovered') is recovered):
                tags = event.get('tags_map', {})
                if not tags:
                    tags = dict(tag.split('=', 1) for tag in event.get('tags', []) if '=' in tag)
                if tags.get('UUID') != 'GPU-SIM-0000' or tags.get('simulated') != 'true':
                    raise ValueError('通知的GPU身份或模拟标记不符')
                result = {key: event.get(key) for key in
                          ('rule_id', 'rule_name', 'trigger_time', 'first_trigger_time', 'is_recovered', 'hash')}
                report['steps'].append(result)
                print('收到夜莺恢复通知' if recovered else '收到夜莺触发通知', flush=True)
                return event
        time.sleep(3)
    raise TimeoutError('未收到预期的夜莺通知；请检查规则状态和通知日志')


try:
    state = request('http://gpu-simulator:9400/state')
    if state['scenario'] != 'normal':
        raise ValueError('测试需要先恢复normal，避免覆盖其他正在进行的场景')
    # Start with fresh time bounds so historical notifications cannot satisfy this test.
    # Allow the previous normal samples to clear any earlier firing instance.
    time.sleep(12)
    started = int(time.time())
    hot_started = time.monotonic()
    scenario('hot')
    changed_scenario = True
    fired = wait_event(False, started)
    # first_trigger_time is first FIRING time, not the pending start.
    elapsed = time.monotonic() - hot_started
    report['firing_observed_after_seconds'] = round(elapsed, 3)
    if fired['trigger_time'] - started < 25:
        raise ValueError('相对于本次场景开始，触发时间过早')
    recovered_since = int(time.time())
    scenario('normal')
    recovered = wait_event(True, recovered_since)
    if fired.get('hash') != recovered.get('hash'):
        raise ValueError('触发与恢复未关联到同一告警实例')
    report['passed'] = True
except Exception as error:
    report['error'] = str(error)
    print('FAIL: ' + str(error), file=sys.stderr, flush=True)
finally:
    if changed_scenario:
        try:
            scenario('normal')
        except Exception:
            report['cleanup_failed'] = True
    report['finished_at'] = time.time()
    path = Path('/results/e2e-temperature.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('报告：.local/reports/e2e-temperature.json', flush=True)
sys.exit(0 if report['passed'] and not report.get('cleanup_failed') else 1)
