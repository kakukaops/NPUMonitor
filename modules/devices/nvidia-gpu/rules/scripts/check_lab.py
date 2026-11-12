#!/usr/bin/env python3
"""Read-only infrastructure and normal-fixture checks; does not configure rules."""
import json
import os
import sys
from pathlib import Path
import tomllib
import time
import urllib.parse
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url):
    with opener.open(url, timeout=10) as response:
        return response.read()


def main():
    failed = False
    # In-container verification checks the config actually mounted into n9e.
    config_path = Path('/app/etc/config.toml')
    if config_path.exists():
        try:
            auth = tomllib.loads(config_path.read_text())['HTTP']['JWTAuth']
            access = auth['AccessExpired']
            refresh = auth['RefreshExpired']
            if access <= 0 or refresh <= access or not auth['RedisKeyPrefix']:
                raise ValueError('JWT 有效期必须为正，刷新有效期须大于访问有效期，Redis 前缀不能为空')
            print('PASS: 挂载配置包含有效的 JWT 会话参数（不代表运行进程已重新加载）')
        except (OSError, ValueError, KeyError, TypeError) as error:
            failed = True
            print(f'FAIL: JWT 会话配置: {error}', file=sys.stderr)
    n9e = os.environ.get("NIGHTINGALE_URL", "http://127.0.0.1:17000").rstrip("/")
    prom = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:19090").rstrip("/")
    checks = (
        ('夜莺 HTTP 页面', n9e + '/', False),
        ('Prometheus 就绪', prom + '/-/ready', False),
        ('Prometheus 自采集',
         prom + '/api/v1/query?query=up%7Bjob%3D%22prometheus%22%7D', True),
    )
    for label, url, is_query in checks:
        try:
            body = get(url)
            if is_query:
                payload = json.loads(body)
                results = payload.get('data', {}).get('result', [])
                if payload.get('status') != 'success' or len(results) != 1 or results[0]['value'][1] != '1':
                    raise ValueError('预期恰好一个自采集 target 且 up=1')
            elif not body:
                raise ValueError('响应为空')
            print(f'PASS: {label}')
        except (OSError, ValueError, KeyError, IndexError) as error:
            failed = True
            print(f'FAIL: {label}: {error}', file=sys.stderr)
    sim = os.environ.get('SIMULATOR_URL', 'http://gpu-simulator:9400').rstrip('/')
    receiver = os.environ.get('RECEIVER_URL', 'http://notification-receiver:9080').rstrip('/')
    try:
        state = json.loads(get(sim + '/state'))
        if state['scenario'] != 'normal':
            raise ValueError('请先执行 bash scripts/lab.sh scenario normal，再验证正常基线')
        get(receiver + '/health')
        # Allow two scrapes for a new target. Never change simulator state here.
        deadline = time.monotonic() + 25
        while True:
            def query(expr):
                result = json.loads(get(prom + '/api/v1/query?' + urllib.parse.urlencode({'query': expr})))
                if result.get('status') != 'success':
                    raise ValueError('Prometheus query failed')
                return result['data']['result']
            up = query('up{job="gpu-simulator"}')
            temps = query('DCGM_FI_DEV_GPU_TEMP{job="gpu-simulator",cluster_id="gpu-sim-lab",simulated="true"}')
            values = {r['metric']['UUID']: r['value'][1] for r in temps}
            if len(up) == 1 and up[0]['value'][1] == '1' and len(temps) == 2 and values == {'GPU-SIM-0000': '55', 'GPU-SIM-0001': '56'}:
                break
            if time.monotonic() >= deadline:
                raise ValueError('正常基线不匹配：需要采集 up=1 及两张模拟卡温度 55/56')
            time.sleep(2)
        print('PASS: 模拟器正常基线已进入 Prometheus（两张 GPU，温度 55/56）')
        print('PASS: 测试通知接收器可达（尚未验证夜莺发送）')
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        failed = True
        print(f'FAIL: 阶段 2 模拟链路: {error}', file=sys.stderr)
    if not failed:
        print('阶段 2 基础链路检查通过；夜莺规则和告警通知尚需单独验证。')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
