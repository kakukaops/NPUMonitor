"""Isolated streaming fixtures for the batch1 draft rules; no GPU required."""
import threading
import time

FIELDS = ('DCGM_FI_DEV_GPU_TEMP', 'DCGM_FI_DEV_ECC_DBE_VOL_TOTAL',
          'DCGM_FI_DEV_SRAM_EXCEEDED', 'DCGM_FI_DEV_ROW_REMAP_FAILURE')
SCENARIOS = ('normal', 'sram', 'remap', 'field_missing', 'device_missing', 'empty',
             'invalid', 'duplicate', 'scrape_error', 'stale', 'transient_invalid')


class BatchModel:
    def __init__(self):
        self.lock = threading.Lock()
        self.scenario = 'normal'
        self.started = time.time()

    def state(self):
        with self.lock:
            return {'scenario': self.scenario, 'elapsed_seconds': time.time()-self.started,
                    'cluster_id': 'batch1-sim-lab', 'simulated': True}

    def select(self, name):
        if name not in SCENARIOS:
            raise ValueError('unknown batch1 scenario: ' + str(name))
        with self.lock:
            self.scenario, self.started = name, time.time()
        return self.state()

    def snapshot(self):
        state = self.state()
        mode = state['scenario']
        if mode == 'scrape_error':
            return 503, 'simulated batch1 scrape failure\n'
        if mode == 'transient_invalid':
            mode = 'invalid' if state['elapsed_seconds'] < 15 else 'normal'
        lines = []
        for field in FIELDS:
            kind = 'counter' if field == FIELDS[1] else 'gauge'
            lines += [f'# HELP {field} Synthetic batch1 input; not real H100.', f'# TYPE {field} {kind}']
        for gpu in range(2):
            if mode == 'empty' or (mode == 'device_missing' and gpu == 1):
                continue
            labels = (f'UUID="GPU-BATCH1-{gpu:04d}",gpu="{gpu}",modelName="SIMULATED-GPU",'
                      'cluster_id="batch1-sim-lab",simulated="true"')
            for i, field in enumerate(FIELDS):
                if gpu == 0 and mode == 'field_missing' and i == 2:
                    continue
                value = 55 + gpu if i == 0 else 0
                if gpu == 0:
                    if mode == 'sram' and i == 2 or mode == 'remap' and i == 3:
                        value = 1
                    if mode == 'invalid' and i == 2:
                        value = 'NaN'
                # New replica label avoids out-of-order conflicts with preceding normal samples.
                # Repeated fixed timestamps remain visible within lookback, but are >90s old.
                extra = ',fixture_age="old"' if mode == 'stale' and gpu == 0 and i == 2 else ''
                stamp = f' {int((self.started-120)*1000)}' if extra else ''
                lines.append(f'{field}{{{labels}{extra}}} {value}{stamp}')
                if mode == 'duplicate' and gpu == 0 and i == 2:
                    lines.append(f'{field}{{{labels},replica="second"}} 1')
        return 200, '\n'.join(lines)+'\n'
