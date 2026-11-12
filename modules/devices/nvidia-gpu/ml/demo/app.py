"""Local-only ML demo. Prometheus is the sole live timeseries source/storage."""
import json
import logging
import math
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

import numpy as np
from model import Detector, SERVICES, SIGNALS, UNITS, SCENARIOS, healthy, inject

PROMETHEUS = os.environ.get('PROMETHEUS_URL', 'http://prometheus:9090').rstrip('/')
PORT = int(os.environ.get('PORT', '9450'))
LOCK = threading.RLock()
MODELS = {}
START = time.time()
MODES = {s: {'mode': 'auto' if i == 0 else 'normal', 'since': START} for i, s in enumerate(SERVICES)}
STATE = {'status': 'warming', 'error': None, 'services': [], 'updated_at': None}
LATEST = {}
CODES = {'normal': 0, 'spike': 1, 'drop': 2, 'drift': 3, 'correlation': 4}


def current_scenario(service, now):
    with LOCK:
        config = MODES[service].copy()
    age = now - config['since']
    mode = config['mode']
    if mode == 'auto':
        phase = age % 240
        for duration, scenario in ((30, 'normal'), (20, 'spike'), (25, 'normal'), (20, 'drop'),
                                   (25, 'normal'), (30, 'drift'), (25, 'normal'), (25, 'correlation'), (40, 'normal')):
            if phase < duration:
                return scenario, phase
            phase -= duration
    if mode != 'normal' and age >= 45:
        return 'normal', age
    return mode, age


def metrics():
    now = time.time()
    sample_time = math.floor(now / 2) * 2
    lines = ['# HELP ml_demo_value Synthetic input gauges; only the demo namespace is simulated.',
             '# TYPE ml_demo_value gauge', '# TYPE ml_demo_sample_time gauge',
             '# TYPE ml_demo_truth gauge', '# TYPE ml_demo_anomaly_score gauge',
             '# TYPE ml_demo_anomaly_threshold gauge', '# TYPE ml_demo_alert_active gauge',
             '# TYPE ml_demo_last_success_timestamp_seconds gauge']
    for i, service in enumerate(SERVICES):
        scenario, age = current_scenario(service, now)
        raw = healthy([sample_time], i, int(sample_time) + i)
        values = inject(raw, scenario, age)[0]
        for signal, value in zip(SIGNALS, values):
            lines.append(f'ml_demo_value{{service="{service}",signal="{signal}"}} {value:.6f}')
        lines.extend([f'ml_demo_sample_time{{service="{service}"}} {sample_time}',
                      f'ml_demo_truth{{service="{service}"}} {CODES[scenario]}'])
        with LOCK:
            latest = LATEST.get(service, {}).copy()
        if latest:
            for metric, field in [('anomaly_score', 'score'), ('anomaly_threshold', 'threshold'), ('alert_active', 'alert')]:
                lines.append(f'ml_demo_{metric}{{service="{service}"}} {latest[field]}')
            lines.append(f'ml_demo_last_success_timestamp_seconds{{service="{service}"}} {latest["sample_time"]}')
    return '\n'.join(lines) + '\n'


def query_history(now):
    end = int(now // 2) * 2
    params = {'query': '{job="ml-anomaly-demo",__name__=~"ml_demo_value|ml_demo_sample_time|ml_demo_truth"}',
              'start': end - 1800, 'end': end, 'step': 2, 'timeout': '5s'}
    with urlopen(PROMETHEUS + '/api/v1/query_range?' + urlencode(params), timeout=7) as response:
        payload = json.load(response)
    if payload.get('status') != 'success':
        raise RuntimeError('Prometheus 查询失败: ' + str(payload.get('error', 'unknown')))
    if payload.get('warnings'):
        raise RuntimeError('Prometheus 返回不完整结果: ' + str(payload['warnings']))
    return payload['data']['result']


def assemble(rows, now):
    """Join by query evaluation timestamp; dedupe held samples using source timestamp.

    An old lookback value cannot advance the state machine. Missing samples create
    gaps, and scoring windows reset after gaps rather than interpolating zeros.
    """
    grouped = {s: {} for s in SERVICES}
    for row in rows:
        labels = row['metric']
        service = labels.get('service')
        if service not in grouped:
            continue
        key = labels.get('signal') if labels['__name__'] == 'ml_demo_value' else labels['__name__']
        if key in grouped[service]:
            raise RuntimeError('同一服务出现重复采集源，请检查 Prometheus target')
        grouped[service][key] = {float(t): float(v) for t, v in row['values'] if math.isfinite(float(v))}
    output = []
    for service in SERVICES:
        tables = grouped[service]
        observed = {}
        for evaluation_t, source_t in sorted(tables.get('ml_demo_sample_time', {}).items()):
            if evaluation_t-source_t > 8 or source_t > evaluation_t+2:
                continue
            values = [tables.get(signal, {}).get(evaluation_t) for signal in SIGNALS]
            if any(v is None for v in values):
                continue
            # Truth is for display/evaluation only; never passed to the model.
            observed[source_t] = (values, tables.get('ml_demo_truth', {}).get(evaluation_t, 0))
        ts = sorted(observed)
        model = MODELS[service]
        points = []
        for offset in range(0, len(ts)):
            # Segment boundaries reset causal feature and alert windows.
            if offset and ts[offset]-ts[offset-1] <= 6:
                continue
            segment_end = offset+1
            while segment_end < len(ts) and ts[segment_end]-ts[segment_end-1] <= 6:
                segment_end += 1
            segment = ts[offset:segment_end]
            expected, scores, residuals = model.evaluate(segment, [observed[t][0] for t in segment])
            history = []
            for index, t in enumerate(segment):
                abnormal = bool(scores[index] > model.threshold)
                history.append(abnormal)
                active = sum(history[-5:]) >= 3
                points.append({'t': t, 'values': observed[t][0], 'expected': expected[index].tolist(),
                               'score': float(scores[index]), 'anomaly': abnormal, 'alert': active,
                               'truth': int(observed[t][1]), 'reason_signal': SIGNALS[int(np.argmax(residuals[index]))]})
        fresh = bool(points and now - points[-1]['t'] <= 10)
        events = []
        for p in points:
            if p['alert'] and (not events or p['t']-events[-1]['end'] > 6):
                events.append({'start': p['t'], 'end': p['t'], 'peak': p['score'], 'signal': p['reason_signal']})
            elif p['alert']:
                events[-1]['end'] = p['t']
                events[-1]['peak'] = max(events[-1]['peak'], p['score'])
        output.append({'name': service, 'fresh': fresh, 'points': points, 'events': events[-30:],
                       'threshold': model.threshold, 'scale': model.scale.tolist(),
                       'status': ('alert' if points[-1]['alert'] else 'pending' if points[-1]['anomaly'] else 'normal') if fresh else 'no_data'})
    return output


def worker():
    while True:
        try:
            now = time.time()
            services = assemble(query_history(now), now)
            with LOCK:
                for service in services:
                    if service['points'] and service['fresh']:
                        p = service['points'][-1]
                        LATEST[service['name']] = {'score': p['score'], 'threshold': service['threshold'],
                                                   'alert': int(p['alert']), 'sample_time': p['t']}
                ready = all(s['fresh'] for s in services)
                STATE.update(status='ready' if ready else 'warming', services=services,
                             error=None, updated_at=time.time())
        except Exception as exc:
            logging.exception('Detection refresh failed')
            with LOCK:
                STATE.update(status='error', error=str(exc),
                             services=[dict(s, fresh=False, status='no_data') for s in STATE['services']])
        time.sleep(2)


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, content_type='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self.send(200, Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
        if path == '/metrics':
            return self.send(200, metrics(), 'text/plain; version=0.0.4; charset=utf-8')
        if path == '/health':
            return self.send(200, {'status': 'alive', 'model_loaded': len(MODELS) == 3})
        if path == '/ready':
            with LOCK:
                ready = STATE['status'] == 'ready' and bool(STATE['updated_at']) and time.time()-STATE['updated_at'] < 10
            return self.send(200 if ready else 503, {'ready': ready})
        if path == '/api/state':
            with LOCK:
                result = dict(STATE, modes={s: dict(c) for s, c in MODES.items()})
            now = time.time()
            result.update(server_time=now, source='Prometheus HTTP query_range', prometheus=PROMETHEUS,
                          model={'name': 'Isolation Forest + Ridge', 'version': 'demo-v2 / sklearn-1.6.1',
                                 'training_source': '独立健康模拟数据（启动时训练）', 'training_samples': 3600,
                                 'calibration_samples': 1200, 'threshold_quantile': .995,
                                 'features': '周期残差 / 一阶差分 / 后向三点均值 / 跨指标关系',
                                 'live_source': '页面所有观测曲线均从当前夜莺 Prometheus 读取'},
                          signals=SIGNALS, units=UNITS)
            return self.send(200, result)
        return self.send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path != '/api/scenario':
            return self.send(404, {'error': 'not found'})
        # The demo has local-only binding; reject browser cross-origin mutation.
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.send(403, {'error': 'cross-origin request denied'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError('请求大小无效')
            payload = json.loads(self.rfile.read(length))
            service, scenario = payload['service'], payload['scenario']
            if service not in SERVICES or scenario not in SCENARIOS:
                raise ValueError('服务或场景无效')
            with LOCK:
                MODES[service] = {'mode': scenario, 'since': time.time()}
            return self.send(200, {'service': service, 'scenario': scenario, 'duration': 45})
        except (ValueError, KeyError, TypeError) as exc:
            return self.send(400, {'error': str(exc)})

    def log_message(self, fmt, *args):
        if self.path not in ('/health', '/metrics', '/api/state'):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    MODELS.update({s: Detector(i) for i, s in enumerate(SERVICES)})
    threading.Thread(target=worker, daemon=True).start()
    print(f'ML demo listening on :{PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
