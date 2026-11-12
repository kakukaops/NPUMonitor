"""Explicit opt-in GPU telemetry fixture; never used as a fallback for missing data."""
import math
import threading
import time
import numpy as np
from .settings import METRICS

UUIDS = tuple(f'GPU-ML-SIM-{i:04d}' for i in range(3))
CLUSTER = 'gpu-ml-simulation'
SCENARIOS = ('normal', 'temperature_spike', 'thermal_drift', 'power_clock', 'activity_drop',
             'thermal_aging', 'clock_aging', 'idle', 'high_load', 'missing', 'invalid', 'duplicate', 'stale')


def healthy(times, index=0, seed=71):
    t = np.asarray(times, dtype=float)
    rng = np.random.default_rng(seed)
    u = 72 + 17*np.sin(t*2*np.pi/180+index*.3) + rng.normal(0, .8, len(t))
    p = 70 + 3.5*u + index*4 + rng.normal(0, 1.3, len(t))
    return {'util': u, 'power': p,
            'gpu_temp': 30 + .055*p + .10*u + index + rng.normal(0, .25, len(t)),
            'memory_temp': 37 + .055*p + .12*u + index + rng.normal(0, .35, len(t)),
            'sm_clock': 550 + 13*u + rng.normal(0, 4, len(t)),
            'mem_clock': np.full(len(t), 1593.) + rng.normal(0, 1, len(t)),
            'mem_util': np.clip(.65*u+rng.normal(0,.6,len(t)), 0, 100),
            'fb_used': 42000 + u*170 + rng.normal(0, 30, len(t)),
            'gpu_limit': np.full(len(t), 95.), 'memory_limit': np.full(len(t), 110.),
            'job_running': np.ones(len(t))}


class Simulator:
    def __init__(self):
        self.lock = threading.RLock()
        self.modes = {u: {'scenario': 'normal', 'since': time.time()} for u in UUIDS}

    def set(self, uuid, scenario):
        if uuid not in UUIDS or scenario not in SCENARIOS:
            raise ValueError('未知GPU或模拟场景')
        with self.lock:
            self.modes[uuid] = {'scenario': scenario, 'since': time.time()}

    def metrics(self, now=None):
        now = time.time() if now is None else now
        ts = math.floor(now/2)*2
        lines = [f'# TYPE {m["name"]} gauge' for m in METRICS.values()]
        with self.lock:
            modes = {u: dict(v) for u, v in self.modes.items()}
        for i, uuid in enumerate(UUIDS):
            config = modes[uuid]; mode = config['scenario']; age = now-config['since']
            if mode not in ('normal','idle','high_load','missing','invalid','duplicate','stale','thermal_aging','clock_aging') and age > 90:
                mode = 'normal'
            if mode == 'missing':
                continue
            values = {k: float(v[0]) for k,v in healthy([ts], i, int(ts)+i).items()}
            if mode in ('idle', 'high_load'):
                util = 4. if mode=='idle' else 97.
                power = 70+3.5*util+i*4
                values.update(util=util,power=power,gpu_temp=30+.055*power+.1*util+i,
                              memory_temp=37+.055*power+.12*util+i,sm_clock=550+13*util,
                              mem_util=util*.65,job_running=0. if mode=='idle' else 1.)
            if mode=='temperature_spike': values['gpu_temp']+=18; values['memory_temp']+=16
            if mode=='thermal_drift': values['gpu_temp']+=min(23,age*.9); values['memory_temp']+=min(20,age*.8)
            if mode=='power_clock': values['power']+=95; values['sm_clock']-=240
            if mode=='activity_drop': values['util']=5.; values['power']=90.; values['sm_clock']=650.
            if mode=='thermal_aging':
                values['gpu_temp']+=min(16,age*.08);values['memory_temp']+=min(14,age*.07)
            if mode=='clock_aging':values['sm_clock']-=min(220,age*1.5)
            if mode=='invalid': values['gpu_temp']=float('nan')
            label=f'cluster_id="{CLUSTER}",UUID="{uuid}",gpu="{i}",modelName="SIMULATED-H100",simulated="true"'
            suffix = f' {int((ts-120)*1000)}' if mode=='stale' else ''
            for key,value in values.items():
                lines.append(f'{METRICS[key]["name"]}{{{label}}} {value}{suffix}')
                if mode=='duplicate':
                    lines.append(f'{METRICS[key]["name"]}{{{label},replica="duplicate"}} {value}{suffix}')
        return '\n'.join(lines)+'\n'
