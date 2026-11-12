"""Deterministic GPU/switch/port fixtures. All identities and values are simulated."""
import json
import math
from pathlib import Path
import threading
import time

CATALOG = Path('/rules/comprehensive-catalog.json')

SCALAR_FAULTS = {
    'sram': ('DCGM_FI_DEV_SRAM_EXCEEDED', 1),
    'remap_failed': ('DCGM_FI_DEV_ROW_REMAP_FAILURE', 1),
    'remap_pending': ('DCGM_FI_DEV_ROW_REMAP_PENDING', 1),
    'gpu_thermal': ('DCGM_FI_DEV_GPU_TEMP', 96),
    'memory_thermal': ('DCGM_FI_DEV_MEMORY_TEMP', 111),
    'switch_thermal': ('DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT', 96),
    'sw_thermal': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 32),
    'hw_thermal': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 64),
    'power_cap': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 4),
    'power_brake': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 128),
    'hw_slowdown': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 8),
    'sync_boost': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 16),
    'clock_unknown': ('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 512),
    'xid_node': ('DCGM_FI_DEV_XID_ERRORS', 79),
    'xid_reset': ('DCGM_FI_DEV_XID_ERRORS', 64),
    'xid_app': ('DCGM_FI_DEV_XID_ERRORS', 13),
    'xid_unknown': ('DCGM_FI_DEV_XID_ERRORS', 999),
    'xid_scope': ('DCGM_FI_DEV_XID_ERRORS', 151),
    'xid_context': ('DCGM_FI_DEV_XID_ERRORS', 45),
    'sxid_fatal': ('DCGM_FI_DEV_NVSWITCH_FATAL_ERRORS', 10001),
    'sxid_nonfatal': ('DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS', 10002),
    'gpu_link_down': ('DCGM_FI_DEV_NVLINK_GET_STATE', 0),
    'switch_link_down': ('DCGM_FI_DEV_NVSWITCH_LINK_STATUS', 3),
    'pcie_degraded': ('DCGM_FI_DEV_PCIE_LINK_WIDTH', 8),
    'fabric_manager': ('DCGM_FI_DEV_FABRIC_MANAGER_STATUS', 4),
    'fabric_capability': ('DCGM_FI_DEV_FABRIC_MANAGER_STATUS', 0),
    'fabric_health': ('DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY', 2),
}
COUNTER_FAULTS = {
    'ecc_new': 'DCGM_FI_DEV_ECC_DBE_VOL_TOTAL',
    'thermal_time': 'DCGM_FI_DEV_THERMAL_VIOLATION',
    'pcie_replay': 'DCGM_FI_DEV_PCIE_REPLAY_COUNTER',
    'nvlink_crc': 'DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL',
    'nvlink_recovery': 'DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL',
    'nvlink_replay': 'DCGM_FI_DEV_NVLINK_REPLAY_TOTAL',
    'switch_replay': 'DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERROR_TOTAL',
    'switch_recovery': 'DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERROR_TOTAL',
}
EXTRA_MODES = ['normal', 'recover', 'field_missing', 'entity_missing', 'input_invalid',
               'input_stale', 'input_duplicate', 'collector_down', 'query_failure',
               'evaluation_stall', 'notification_failure', 'engine_metrics_failure', 'unused_port', 'missing_link',
               'thermal_transient', 'thermal_pending_missing', 'thermal_hysteresis', 'hbm_limit_missing', 'idle_pcie', 'switch_unknown', 'switch_missing']


class Model:
    def __init__(self, catalog=None):
        self.catalog = catalog or json.loads(CATALOG.read_text())
        self.fields = self.catalog['fields']
        self.entities = self.catalog['entities']
        self.lock = threading.Lock()
        self.mode = 'normal'
        self.started = time.time()
        self.verified = 1
        self.counts = {name: 0 for name in COUNTER_FAULTS.values()}
        self.generation = 0

    def modes(self):
        return list(SCALAR_FAULTS) + list(COUNTER_FAULTS) + EXTRA_MODES

    def select(self, mode):
        if mode not in self.modes():
            raise ValueError('unknown scenario')
        with self.lock:
            if self.mode in COUNTER_FAULTS:
                field = COUNTER_FAULTS[self.mode]
                self.counts[field] += max(1, int((time.time() - self.started) / 2))
            self.mode = mode
            self.started = time.time()
            self.generation += 1
            if mode == 'recover':
                self.verified = 1
            elif mode != 'normal':
                self.verified = 0
            return self.state_unlocked()

    def state_unlocked(self):
        return {'scenario': self.mode, 'elapsed_seconds': round(time.time()-self.started,2),
                'generation': self.generation, 'recovery_verified': bool(self.verified), 'simulated': True}

    def state(self):
        with self.lock:
            return self.state_unlocked()

    def snapshot(self, counters):
        with self.lock:
            mode = self.mode
            elapsed = time.time()-self.started
            if mode == 'collector_down':
                return 503, 'synthetic collector failure\n'
            lines = []
            for name, spec in self.fields.items():
                kind = 'counter' if spec['kind'] == 'counter' else 'gauge'
                lines += [f'# HELP {name} Synthetic H100 training acceptance input.', f'# TYPE {name} {kind}']
                for entity in spec['entity_ids']:
                    is_first = entity in ('GPU-DEMO-0000','SWITCH-DEMO-0000','GPU-DEMO-0000/0','SWITCH-DEMO-0000/0')
                    physical = name.startswith('DCGM_')
                    labels = dict(self.entities[entity], entity_id=entity, simulated='true')
                    labels['modelName'] = 'SIMULATED-SWITCH' if 'SWITCH' in entity else 'SIMULATED-GPU'
                    # Expected measurements survive disappearance of the device data.
                    if physical:
                        expected_labels = dict(labels, metric_name=name)
                        lines.append('DEMO_EXPECTED_INPUT{' + self.labels(expected_labels) + '} 1')
                    if physical and entity == 'GPU-DEMO-0000' and (mode == 'entity_missing' or mode == 'thermal_pending_missing' and elapsed >= 4):
                        continue
                    if physical and entity == 'SWITCH-DEMO-0000' and mode == 'switch_missing':
                        continue
                    if entity == 'GPU-DEMO-0000' and mode == 'field_missing' and name == 'DCGM_FI_DEV_SRAM_EXCEEDED':
                        continue
                    if entity == 'GPU-DEMO-0000' and mode == 'hbm_limit_missing' and name == 'DCGM_FI_DEV_MEM_MAX_OP_TEMP':
                        continue
                    if entity == 'GPU-DEMO-0000/0' and mode == 'missing_link' and name == 'DCGM_FI_DEV_NVLINK_GET_STATE':
                        continue
                    value = spec['normal']
                    if name == 'DEMO_RECOVERY_VERIFIED':
                        value = self.verified
                    if name in self.counts and is_first:
                        count = self.counts[name]
                        if COUNTER_FAULTS.get(mode) == name:
                            count += max(1, int(elapsed / 2))
                        value = count * (1000000000 if spec['unit']=='nanoseconds' else 1)
                    if mode in SCALAR_FAULTS and is_first:
                        fault_name, fault_value = SCALAR_FAULTS[mode]
                        if name == fault_name:
                            value = fault_value
                    if entity == 'GPU-DEMO-0000' and name == 'DCGM_FI_DEV_GPU_TEMP':
                        if mode in ('thermal_transient','thermal_pending_missing') and elapsed < 4:
                            value = 96
                        if mode == 'thermal_hysteresis':
                            value = 92
                    if entity == 'GPU-DEMO-0000' and mode == 'input_invalid' and name == 'DCGM_FI_DEV_SRAM_EXCEEDED':
                        value = 'NaN'
                    if mode == 'idle_pcie' and entity == 'GPU-DEMO-0000':
                        if name == 'DCGM_FI_DEV_PCIE_LINK_WIDTH':value=8
                        if name == 'DEMO_JOB_RUNNING':value=0
                    if mode == 'switch_unknown' and entity == 'SWITCH-DEMO-0000/0' and name == 'DCGM_FI_DEV_NVSWITCH_LINK_STATUS':
                        value=-1
                    stamp = ''
                    if entity == 'GPU-DEMO-0000' and mode == 'input_stale' and name == 'DCGM_FI_DEV_SRAM_EXCEEDED':
                        labels['fixture_age'] = 'old'
                        stamp = f' {int((self.started - 30)*1000)}'
                    lines.append(f'{name}{{{self.labels(labels)}}} {value}{stamp}')
                    if entity == 'GPU-DEMO-0000' and mode == 'input_duplicate' and name == 'DCGM_FI_DEV_SRAM_EXCEEDED':
                        lines.append(f'{name}{{{self.labels(dict(labels,replica="other"))}}} 1')
            # An unused GPU port is intentionally inactive. It is outside expected entities.
            unused = dict(self.entities['GPU-DEMO-0000'],entity_type='gpu_link',entity_id='GPU-DEMO-0000/1',link_id='1',simulated='true')
            lines.append('DCGM_FI_DEV_NVLINK_GET_STATE{' + self.labels(unused) + '} 0')
            lines.append('DEMO_EXPECTED_LINK{' + self.labels(unused) + '} 0')
            lines.append('DEMO_PROBE_INPUT 2' if mode == 'notification_failure' else 'DEMO_PROBE_INPUT 0')
            lines.append('# TYPE DEMO_NOTIFY_FAILURES_TOTAL counter')
            lines.append('# TYPE DEMO_NOTIFY_SUCCESSES_TOTAL counter')
            lines.append(f'DEMO_NOTIFY_FAILURES_TOTAL {counters["failed"]}')
            lines.append(f'DEMO_NOTIFY_SUCCESSES_TOTAL {counters["delivered"]}')
            return 200, '\n'.join(lines)+'\n'

    @staticmethod
    def labels(values):
        return ','.join(key+'='+json.dumps(str(value)) for key,value in sorted(values.items()))
