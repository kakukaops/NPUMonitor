"""Real Prometheus roundtrip acceptance. Run inside the demo container."""
import json
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode

BASE = 'http://127.0.0.1:9450'


def request(path, payload=None):
    req = Request(BASE+path, data=json.dumps(payload).encode() if payload else None,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def scenario(name):
    return request('/api/scenario', {'service': 'checkout', 'scenario': name})


def wait_for(predicate, timeout=45):
    deadline = time.time()+timeout
    while time.time() < deadline:
        state = request('/api/state')
        row = next((s for s in state['services'] if s['name'] == 'checkout'), None)
        if row and predicate(row):
            return state, row
        time.sleep(2)
    raise AssertionError('Timed out waiting for expected real detection state')


result = {'source': 'existing Nightingale Prometheus', 'cases': [], 'started_at': time.time()}
try:
    scenario('normal')
    state, row = wait_for(lambda s: s['fresh'] and len(s['points']) >= 8 and s['status'] == 'normal')
    assert len(row['points']) > 0
    # Check the public page and the independent scrape target, not a fallback source.
    with urlopen(BASE+'/', timeout=5) as response:
        assert response.status == 200 and b'<canvas' in response.read()
    query = urlencode({'query': 'up{job="ml-anomaly-demo"}'})
    with urlopen(state['prometheus']+'/api/v1/query?'+query, timeout=10) as response:
        up = json.load(response)
    assert up['data']['result'][0]['value'][1] == '1'
    for name in ('spike', 'drop', 'drift', 'correlation'):
        since = time.time()
        scenario(name)
        state, row = wait_for(lambda s: s['fresh'] and s['status'] == 'alert'
                              and s['points'][-1]['t'] >= since
                              and s['points'][-1]['truth'] != 0, 44)
        result['cases'].append({'scenario': name, 'passed': True,
                                'delay_seconds': round(time.time()-since, 2),
                                'score': row['points'][-1]['score'], 'threshold': row['threshold']})
        print(json.dumps(result['cases'][-1]), flush=True)
        scenario('normal')
        wait_for(lambda s: s['fresh'] and s['status'] == 'normal' and s['points'][-1]['truth'] == 0, 30)
    # Confirm derived outputs also reached the same Prometheus.
    time.sleep(4)
    query = urlencode({'query': 'ml_demo_anomaly_score{job="ml-anomaly-demo"}'})
    with urlopen(state['prometheus']+'/api/v1/query?'+query, timeout=10) as response:
        scores = json.load(response)
    assert len(scores['data']['result']) == 3
    result.update(passed=True, output_series=3, completed_at=time.time())
finally:
    scenario('auto')
print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
