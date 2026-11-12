"""Evaluate all thermal/link review queries through the real Prometheus HTTP API."""
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
CATALOG = Path('/queries/thermal-links-review-queries.json')
QUERIES = json.loads(CATALOG.read_text())['queries']


def request(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=10) as response:
        return json.load(response)


def evaluate():
    results = {}
    evaluation_time = time.time()
    for query in QUERIES:
        response = request('http://review-prometheus:9090/api/v1/query?' +
                           urllib.parse.urlencode({'query': query['expression'], 'time': evaluation_time}))
        assert response['status'] == 'success' and not response.get('warnings'), query['query_id']
        values = {}
        for row in response['data']['result']:
            uuid = row['metric']['UUID']
            assert uuid not in values, (query['query_id'], 'duplicate output identity')
            values[uuid] = float(row['value'][1])
        results[query['query_id']] = values
    return results


def run():
    report = {'scope': 'isolated_prometheus_streaming', 'passed': False, 'cases': [],
              'catalog_sha256': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
              'real_h100_tests': 'not_run', 'nightingale_tests': 'not_run'}
    try:
        for mode in ['normal', 'stress', 'duplicate', 'invalid_limit', 'unknown_mask', 'unknown_with_thermal', 'stale', 'scrape_error']:
            request('http://review-simulator:9412/scenario', {'name': mode})
            time.sleep(8 if mode == 'stress' else 5)
            case = {'scenario': mode, 'passed': False}
            report['cases'].append(case)
            rows = evaluate()
            case['results'] = rows
            first = 'GPU-FIXTURE-0000'
            second = 'GPU-FIXTURE-0001'
            if mode == 'normal':
                assert rows['thermal.gpu_operating_margin'] == {first: 40, second: 39}
                assert rows['thermal.memory_operating_margin'] == {first: 50, second: 49}
                assert not rows['memory.remap_pending']
            elif mode == 'stress':
                assert rows['memory.remap_pending'] == {first: 1}
                assert rows['thermal.gpu_operating_margin'][first] == 0
                assert rows['thermal.memory_operating_margin'][first] == -1
                assert rows['clock.sw_thermal'] == rows['clock.hw_thermal'] == {first: 1}
                for query_id in ['clock.sw_power_cap', 'clock.hw_slowdown', 'clock.hw_power_brake', 'clock.sync_boost']:
                    assert not rows[query_id]
                seconds = rows['thermal.slowdown_seconds'][first]
                replay = rows['pcie.replay_increase'][first]
                assert seconds > 0 and abs(seconds - replay) < 1e-6
                for query_id in ['nvlink.crc_increase', 'nvlink.recovery_increase', 'nvlink.replay_increase']:
                    assert rows[query_id][first] > 0
            elif mode in ('duplicate', 'stale'):
                assert all(first not in values for values in rows.values())
                assert rows['thermal.gpu_operating_margin'][second] == 39
            elif mode == 'invalid_limit':
                assert first not in rows['thermal.gpu_operating_margin']
                assert first not in rows['thermal.memory_operating_margin']
                assert rows['thermal.gpu_operating_margin'][second] == 39
            elif mode == 'unknown_mask':
                assert rows['clock.unknown_bits'] == {first: 512}
                assert not rows['clock.sw_thermal'] and not rows['clock.hw_thermal']
            elif mode == 'unknown_with_thermal':
                assert rows['clock.unknown_bits'] == {first: 544}
                assert rows['clock.sw_thermal'] == {first: 1}
                assert not rows['clock.hw_thermal']
            elif mode == 'scrape_error':
                assert all(not values for values in rows.values())
            case['passed'] = True
            print('PASS: streaming ' + mode, flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        print('FAIL: ' + str(error), flush=True)
    finally:
        request('http://review-simulator:9412/scenario', {'name': 'normal'})
        Path('/results/thermal-links-live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(run())
