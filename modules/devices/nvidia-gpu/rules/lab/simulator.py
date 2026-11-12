"""Deterministic, GPU-free DCGM-style fixtures. Never a hardware emulator."""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from batch1_simulator import BatchModel

BATCH_MODEL = BatchModel()

SCENARIOS = ('normal', 'hot', 'xid', 'ecc', 'missing', 'empty', 'invalid',
             'scrape_error', 'counter_reset', 'transient', 'sustained')
METRICS = {
    'DCGM_FI_DEV_GPU_TEMP': ('gauge', 'GPU temperature in Celsius.'),
    'DCGM_FI_DEV_GPU_UTIL': ('gauge', 'GPU utilization in percent.'),
    'DCGM_FI_DEV_XID_ERRORS': ('gauge', 'Last observed XID code, not an event counter.'),
    'DCGM_FI_DEV_ECC_DBE_VOL_TOTAL': ('counter', 'Volatile double-bit ECC errors.'),
    'DCGM_FI_DEV_ROW_REMAP_FAILURE': ('gauge', 'Whether row remapping failed.'),
}


class Model:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.scenario = 'normal'
        self.started = clock()
        self.generation = 0
        self.ecc = 0

    def select(self, name):
        if name not in SCENARIOS:
            raise ValueError('unknown scenario; choose: ' + ', '.join(SCENARIOS))
        with self.lock:
            self.scenario = name
            self.started = self.clock()
            self.generation += 1
            if name == 'ecc':
                self.ecc += 1
            elif name == 'counter_reset':
                self.ecc = 0
            return self._state()

    def _state(self):
        return {'scenario': self.scenario, 'elapsed_seconds': round(self.clock() - self.started, 3),
                'generation': self.generation, 'cluster_id': 'gpu-sim-lab', 'simulated': True}

    def state(self):
        with self.lock:
            return self._state()

    def snapshot(self):
        with self.lock:
            state = self._state()
            mode = self.scenario
            elapsed = state['elapsed_seconds']
            if mode in ('transient', 'sustained'):
                duration = 10 if mode == 'transient' else 70
                mode = 'hot' if 10 <= elapsed < 10 + duration else 'normal'
            if mode == 'scrape_error':
                return 503, 'simulated scrape failure\n'
            lines = []
            for metric, (kind, help_text) in METRICS.items():
                lines += [f'# HELP {metric} {help_text}', f'# TYPE {metric} {kind}']
            for gpu in range(2):
                if mode == 'empty' or (mode == 'missing' and gpu == 1):
                    continue
                labels = (f'gpu="{gpu}",UUID="GPU-SIM-{gpu:04d}",'
                          f'modelName="SIMULATED-GPU",Hostname="gpu-sim-node",'
                          f'cluster_id="gpu-sim-lab",simulated="true"')
                values = [55 + gpu, 30, 0, self.ecc if gpu == 0 else 0, 0]
                if gpu == 0:
                    if mode == 'hot':
                        values[0] = 95
                    elif mode == 'xid':
                        values[2] = 79
                    elif mode == 'invalid':
                        values[0] = 'NaN'
                for metric, value in zip(METRICS, values):
                    lines.append(f'{metric}{{{labels}}} {value}')
            # Control-plane liveness is intentionally separate from GPU series.
            lines.append('gpu_simulator_info{cluster_id="gpu-sim-lab",simulated="true"} 1')
            return 200, '\n'.join(lines) + '\n'


MODEL = Model()


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, content_type='application/json'):
        data = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, '{"ok":true}')
        elif self.path == '/batch1/state':
            self.reply(200, json.dumps(BATCH_MODEL.state()))
        elif self.path == '/batch1/metrics':
            status, body = BATCH_MODEL.snapshot()
            self.reply(status, body, 'text/plain; version=0.0.4; charset=utf-8')
        elif self.path == '/state':
            self.reply(200, json.dumps(MODEL.state()))
        elif self.path == '/metrics':
            status, body = MODEL.snapshot()
            self.reply(status, body, 'text/plain; version=0.0.4; charset=utf-8')
        else:
            self.reply(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path not in ('/scenario', '/batch1/scenario'):
            self.reply(404, '{"error":"not found"}')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                raise ValueError('body must be 1..1024 bytes')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('JSON object required')
            self.reply(200, json.dumps((BATCH_MODEL if self.path.startswith('/batch1/') else MODEL).select(body.get('name'))))
        except (ValueError, TypeError) as error:
            self.reply(400, json.dumps({'error': str(error)}))

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9400)
    args = parser.parse_args()
    ThreadingHTTPServer(('0.0.0.0', args.port), Handler).serve_forever()
