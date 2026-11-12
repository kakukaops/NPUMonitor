"""Streaming fixtures for isolated Prometheus review; temperatures are test values."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time

FIELDS = {
    'DCGM_FI_DEV_ROW_REMAP_PENDING': 0,
    'DCGM_FI_DEV_GPU_TEMP': 55,
    'DCGM_FI_DEV_GPU_MAX_OP_TEMP': 95,
    'DCGM_FI_DEV_MEMORY_TEMP': 60,
    'DCGM_FI_DEV_MEM_MAX_OP_TEMP': 110,
    'DCGM_FI_DEV_CLOCKS_EVENT_REASONS': 0,
    'DCGM_FI_DEV_THERMAL_VIOLATION': 0,
    'DCGM_FI_DEV_PCIE_REPLAY_COUNTER': 0,
    'DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL': 0,
    'DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL': 0,
    'DCGM_FI_DEV_NVLINK_REPLAY_TOTAL': 0,
}
COUNTERS = set(list(FIELDS)[6:])
MODES = ('normal', 'stress', 'duplicate', 'invalid_limit', 'unknown_mask', 'unknown_with_thermal', 'stale', 'scrape_error')


class Model:
    def __init__(self):
        self.lock = threading.Lock()
        self.mode = 'normal'
        self.started = time.time()
        self.counter = 0

    def select(self, mode):
        if mode not in MODES:
            raise ValueError('unknown scenario')
        with self.lock:
            if self.mode == 'stress':
                self.counter += int(time.time() - self.started)
            self.mode = mode
            self.started = time.time()

    def snapshot(self):
        with self.lock:
            if self.mode == 'scrape_error':
                return 503, 'synthetic scrape failure\n'
            counter = self.counter + (int(time.time() - self.started) if self.mode == 'stress' else 0)
            rows = []
            for field, initial in FIELDS.items():
                kind = 'counter' if field in COUNTERS else 'gauge'
                rows.extend([f'# HELP {field} Isolated synthetic review input.', f'# TYPE {field} {kind}'])
                for gpu in range(2):
                    value = initial
                    if field in ('DCGM_FI_DEV_GPU_TEMP', 'DCGM_FI_DEV_MEMORY_TEMP'):
                        value += gpu
                    if gpu == 0:
                        if field in COUNTERS:
                            value = counter * (1000000000 if field == 'DCGM_FI_DEV_THERMAL_VIOLATION' else 1)
                        if self.mode == 'stress':
                            value = {'DCGM_FI_DEV_GPU_TEMP': 95, 'DCGM_FI_DEV_MEMORY_TEMP': 111,
                                     'DCGM_FI_DEV_CLOCKS_EVENT_REASONS': 96,
                                     'DCGM_FI_DEV_ROW_REMAP_PENDING': 1}.get(field, value)
                        if self.mode == 'invalid_limit' and field.endswith('MAX_OP_TEMP'):
                            value = 'NaN'
                        if self.mode in ('unknown_mask', 'unknown_with_thermal') and field == 'DCGM_FI_DEV_CLOCKS_EVENT_REASONS':
                            value = 512 if self.mode == 'unknown_mask' else 544
                    labels = f'UUID="GPU-FIXTURE-{gpu:04d}",modelName="SIMULATED-GPU",simulated="true"'
                    stamp = ''
                    if self.mode == 'stale' and gpu == 0:
                        labels += ',fixture_age="old"'
                        stamp = f' {int((self.started - 120) * 1000)}'
                    rows.append(f'{field}{{{labels}}} {value}{stamp}')
                    if self.mode == 'duplicate' and gpu == 0:
                        rows.append(f'{field}{{{labels},replica="other"}} {value}')
            return 200, '\n'.join(rows) + '\n'


MODEL = Model()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type='application/json'):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, '{"ok":true}')
        elif self.path == '/metrics':
            status, body = MODEL.snapshot()
            self.reply(status, body, 'text/plain; version=0.0.4')
        else:
            self.reply(404, '{}')

    def do_POST(self):
        if self.path != '/scenario':
            self.reply(404, '{}')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                raise ValueError('bounded body required')
            body = json.loads(self.rfile.read(length))
            MODEL.select(body['name'])
            self.reply(200, json.dumps({'scenario': body['name']}))
        except (ValueError, KeyError, TypeError):
            self.reply(400, '{"error":"invalid scenario request"}')

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 9412), Handler).serve_forever()
