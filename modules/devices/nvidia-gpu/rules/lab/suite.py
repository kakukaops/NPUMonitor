"""Sequential real-Prometheus/Nightingale/receiver scenario acceptance tests."""
import json
import argparse
from datetime import datetime
from pathlib import Path
import sys
import signal
import time
import urllib.parse
import urllib.request
from n9e import API, GROUP, unique

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
REPORT = {'started_at': time.time(), 'cases': [], 'passed': False}
UUID0 = 'GPU-SIM-0000'
UUID1 = 'GPU-SIM-0001'


def request(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=10) as response:
        return json.load(response)


def scenario(name):
    result = request('http://gpu-simulator:9400/scenario', {'name': name})
    print('场景：' + name, flush=True)
    return result


def tags(event):
    return event.get('tags_map') or dict(t.split('=', 1) for t in event.get('tags', []) if '=' in t)


def notifications(since):
    result = []
    for record in request('http://notification-receiver:9080/events')['events']:
        received = datetime.fromisoformat(record['received_at']).timestamp()
        if received < since or not isinstance(record['payload'], list):
            continue
        for event in record['payload']:
            if isinstance(event, dict):
                result.append((received, event))
    return result


class Runner:
    def __init__(self):
        self.api = API()
        bg = unique(self.api.call('GET', '/busi-groups?all=true&limit=1000'), GROUP)
        if not bg:
            raise ValueError('请先导入实验规则')
        self.gid = bg['id']
        rows = self.api.call('GET', f'/busi-group/{self.gid}/alert-rules')
        self.rules = {tag.split('=', 1)[1]: row for row in rows
                      for tag in row.get('append_tags', []) if tag.startswith('rule_id=gpu_lab_')}
        for key in ('temperature', 'xid79', 'ecc_dbe', 'scrape_down', 'missing', 'invalid_temp'):
            row = self.rules.get('gpu_lab_' + key)
            if not row or row['disabled']:
                raise ValueError('规则缺失或禁用：' + key)
        self.ids = {row['id'] for row in self.rules.values()}

    def active(self):
        data = self.api.call('GET', f'/alert-cur-events/list?bgid={self.gid}&hours=24&limit=100')
        return [e for e in data['list'] if e['rule_id'] in self.ids]

    def wait_clear(self, timeout=90):
        deadline = time.monotonic() + timeout
        while self.active():
            if time.monotonic() >= deadline:
                raise TimeoutError('实验告警未恢复，停止后续场景')
            time.sleep(2)

    def assert_expected(self, since, expected):
        """Fail on collateral firing; expected is (catalog key, UUID or None)."""
        for _, event in notifications(since):
            if event.get('is_recovered') or event.get('rule_id') not in self.ids:
                continue
            pair = (tags(event).get('rule_id'), tags(event).get('UUID'))
            if pair not in expected:
                raise ValueError('出现非预期告警：' + str(pair))

    def wait_notifications(self, since, expected, recovered, timeout=100):
        deadline = time.monotonic() + timeout
        found = {}
        while time.monotonic() < deadline:
            self.assert_expected(since, expected)
            for received, event in notifications(since):
                pair = (tags(event).get('rule_id'), tags(event).get('UUID'))
                if pair in expected and event.get('is_recovered') is recovered:
                    found[pair] = {'rule_id': event['rule_id'], 'uuid': pair[1],
                                   'hash': event['hash'], 'received_at': received,
                                   'is_recovered': recovered}
            if set(found) == expected:
                return found
            time.sleep(2)
        raise TimeoutError('缺少' + ('恢复' if recovered else '触发') + '通知：' + str(expected - set(found)))

    def fault(self, name, expected, recovery_timeout=100):
        self.wait_clear()
        started = time.time()
        case = {'scenario': name, 'started_at': started, 'passed': False}
        REPORT['cases'].append(case)
        scenario(name)
        fired = self.wait_notifications(started, expected, False)
        case['firing_after_seconds'] = round(time.time() - started, 3)
        since_recover = time.time()
        scenario('normal')
        recovered = self.wait_notifications(since_recover, expected, True, recovery_timeout)
        for pair in expected:
            if fired[pair]['hash'] != recovered[pair]['hash']:
                raise ValueError('触发和恢复hash不一致')
        self.wait_clear()
        case.update(passed=True, recovered_after_seconds=round(time.time() - since_recover, 3),
                    firing=list(fired.values()), recovery=list(recovered.values()))
        print('PASS: ' + name + ' 触发/恢复/身份/无旁路误报', flush=True)

    def quiet(self, name, seconds, observe_temperature=False):
        self.wait_clear()
        started = time.time()
        case = {'scenario': name, 'started_at': started, 'passed': False}
        REPORT['cases'].append(case)
        scenario(name)
        saw_hot = False
        while time.time() - started < seconds:
            self.assert_expected(started, set())
            if self.active():
                raise ValueError(name + ' 不应产生活动告警')
            if observe_temperature:
                url = 'http://prometheus:9090/api/v1/query?' + urllib.parse.urlencode({
                    'query': 'DCGM_FI_DEV_GPU_TEMP{UUID="GPU-SIM-0000",job="gpu-simulator"}'})
                values = request(url)['data']['result']
                saw_hot |= any(row['value'][1] == '95' for row in values)
            time.sleep(2)
        if observe_temperature and not saw_hot:
            raise ValueError('未实际采到短暂高温，不能判定抑制成功')
        self.assert_expected(started, set())
        case.update(passed=True, observed_seconds=round(time.time() - started, 3),
                    saw_hot=saw_hot if observe_temperature else None)
        scenario('normal')
        print('PASS: ' + name + ' 未误报', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['all', 'invalid'], default='all')
    args = parser.parse_args()
    REPORT['selection'] = args.case
    changed = False
    try:
        state = request('http://gpu-simulator:9400/state')
        if state['scenario'] != 'normal':
            raise ValueError('请先恢复normal；不要与其他手工/自动测试同时运行')
        runner = Runner()
        runner.wait_clear()
        # Ensure the current zero counter baseline and discovery series were scraped.
        time.sleep(12)
        changed = True
        if args.case == 'all':
            runner.quiet('transient', 40, observe_temperature=True)
            runner.fault('xid', {('gpu_lab_xid79', UUID0)})
            runner.fault('ecc', {('gpu_lab_ecc_dbe', UUID0)})
            # ECC has already left the 1-minute window; resetting should not create a new increase.
            runner.quiet('counter_reset', 25)
            runner.fault('scrape_error', {('gpu_lab_scrape_down', None)})
            runner.fault('missing', {('gpu_lab_missing', UUID1)})
            runner.fault('empty', {('gpu_lab_missing', UUID0), ('gpu_lab_missing', UUID1)})
        runner.fault('invalid', {('gpu_lab_invalid_temp', UUID0)})
        REPORT['passed'] = True
    except Exception as error:
        REPORT['error'] = str(error)
        print('FAIL: ' + str(error), flush=True)
    finally:
        if changed:
            try:
                scenario('normal')
            except Exception as error:
                REPORT['cleanup_error'] = str(error)
        REPORT['finished_at'] = time.time()
        Path('/results/e2e-scenarios' + ('' if args.case == 'all' else '-' + args.case) + '.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2))
        print('报告：.local/reports/e2e-scenarios' + ('' if args.case == 'all' else '-' + args.case) + '.json', flush=True)
    return 0 if REPORT['passed'] and not REPORT.get('cleanup_error') else 1


if __name__ == '__main__':
    def terminate(signum, frame):
        raise RuntimeError('测试收到终止信号')
    signal.signal(signal.SIGTERM, terminate)
    sys.exit(main())
