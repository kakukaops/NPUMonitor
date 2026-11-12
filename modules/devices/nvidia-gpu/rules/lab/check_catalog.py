"""Read-only parsing and normal-fixture evaluation using real Prometheus."""
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://gpu-simulator:9400/state', timeout=10) as response:
    if json.load(response)['scenario'] != 'normal':
        sys.exit('请先恢复 normal，再验证目录正常基线')
catalog = json.loads(Path('/rules/lab-catalog.json').read_text())
failed = False
for rule in catalog['rules']:
    url = 'http://prometheus:9090/api/v1/query?' + urllib.parse.urlencode({'query': rule['expression']})
    with opener.open(url, timeout=10) as response:
        payload = json.load(response)
    if payload.get('status') != 'success' or payload['data']['result']:
        print('FAIL: 正常基线不应命中：' + rule['key'])
        failed = True
    else:
        print('PASS: Prometheus解析及正常基线：' + rule['key'])
sys.exit(int(failed))
