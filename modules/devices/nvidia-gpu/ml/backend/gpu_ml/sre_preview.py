"""Deterministic, read-only simulated replays for the SRE workbench preview."""

from functools import lru_cache

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .settings import METRICS
from .simulation import healthy

STEP = 30
REFERENCE = 360
FIT = 240
POINTS = 60
CONFIRM = 3
WINDOW = 5
START = 1795500000  # 2026-11-24 14:00 Asia/Shanghai

FEATURES = ('util', 'power', 'gpu_temp', 'memory_temp', 'sm_clock', 'mem_util')
UNITS = {'util': '%', 'power': 'W', 'gpu_temp': '°C', 'memory_temp': '°C',
         'sm_clock': 'MHz', 'mem_util': '%'}
TREND_METHODS = ('local_trend', 'rolling_median', 'historical_level')
FLOORS = {'util': 4, 'power': 14, 'gpu_temp': 1.5, 'memory_temp': 1.5,
          'sm_clock': 55, 'mem_util': 3}
SCENARIOS = {
    'fleet': ('drift', 'rule', 'joint', 'gap'),
    'drift': ('drift',),
    'rule': ('rule',),
    'joint': ('joint',),
    'gap': ('gap',),
    'normal': ('normal',),
}
DEVICES = {
    'drift': ('train-07', 2, 'GPU 温度持续偏离动态基线', 'trend', 'gpu_temp'),
    'rule': ('train-12', 0, '高利用率下功耗升高、SM 时钟下探', 'white', 'sm_clock'),
    'joint': ('infer-04', 1, '功耗、HBM 温度与显存活动失配', 'black', 'memory_temp'),
    'gap': ('train-09', 3, '功耗与显存活动采集缺口', 'quality', 'power'),
    'normal': ('train-07', 2, '正常波动回放', 'trend', 'gpu_temp'),
}


def numbers(values):
    """Preserve unavailable observations as JSON null."""
    return [round(float(value), 4) if np.isfinite(value) else None for value in values]


def confirmed_spans(scores):
    """Return contiguous periods and the first point at which each was actionable."""
    exceed = np.r_[False, np.isfinite(scores) & (scores >= 1), False]
    edges = np.flatnonzero(exceed[1:] != exceed[:-1])
    return [
        {'start': int(start), 'confirmed': int(start + CONFIRM - 1), 'end': int(stop - 1)}
        for start, stop in zip(edges[::2], edges[1::2]) if stop - start >= CONFIRM
    ]


def trend(history, values, metric, method):
    joined = np.r_[history, values]
    if method == 'historical_level':
        prediction = np.full(len(joined), np.median(history[:FIT]))
    else:
        # The row at index t contains only observations strictly earlier than t.
        lagged = sliding_window_view(joined, 10)[:-1]
        recent = np.median(lagged[:, -5:], axis=1)
        prediction = np.full(len(joined), np.nan)
        prediction[10:] = recent
        if method == 'local_trend':
            prediction[10:] = recent + .35 * (recent - np.median(lagged[:, :5], axis=1))
    errors = np.abs(joined - prediction)
    width = max(FLOORS[metric], np.nanquantile(errors[FIT:REFERENCE], .99))
    score = errors[REFERENCE:] / width
    reference = prediction[REFERENCE:]
    return {'expected': numbers(reference), 'lower': numbers(reference - width),
            'upper': numbers(reference + width), 'scores': numbers(score),
            'periods': confirmed_spans(score), 'bandWidth': float(width)}


def white_box(history, values):
    util = values['util']
    # Estimate comparable normal power and frequency at the observed load.
    expected_power = np.polyval(np.polyfit(history['util'][:FIT], history['power'][:FIT], 1), util)
    expected_clock = np.polyval(np.polyfit(history['util'][:FIT], history['sm_clock'][:FIT], 1), util)
    evidence = (
        ('util', 'GPU 利用率', '≥', 60, util),
        ('power', '功耗高于同负载参考', '≥', 40, values['power'] - expected_power),
        ('sm_clock', 'SM 时钟低于同负载参考', '≥', 120, expected_clock - values['sm_clock']),
    )
    valid = np.all(np.isfinite([row[4] for row in evidence]), axis=0)
    score = np.minimum.reduce([row[4] / row[3] for row in evidence])
    scores = np.where(valid, np.maximum(score, 0), np.nan)
    return {
        'scores': numbers(scores), 'periods': confirmed_spans(scores),
        'conditions': [{'metric': metric, 'name': name, 'op': op, 'threshold': limit,
                        'values': numbers(observed)}
                       for metric, name, op, limit, observed in evidence],
    }


def joint_pca(history, values):
    reference = np.column_stack([history[k] for k in FEATURES])
    test = np.column_stack([values[k] for k in FEATURES])
    center = reference[:FIT].mean(axis=0)
    scale = reference[:FIT].std(axis=0)
    standardized = (np.concatenate((reference, test)) - center) / scale
    windows = sliding_window_view(standardized, WINDOW, axis=0).reshape(-1, len(FEATURES) * WINDOW)
    # Training windows end before calibration. Calibration windows also begin after fitting.
    _, _, vectors = np.linalg.svd(windows[:FIT - WINDOW + 1], full_matrices=False)
    basis = vectors[:3]
    residual = (windows - (windows @ basis.T) @ basis) ** 2
    contributions = residual.reshape(-1, len(FEATURES), WINDOW).mean(axis=2)
    mse = contributions.mean(axis=1)
    threshold = max(float(np.quantile(mse[FIT:REFERENCE - WINDOW + 1], .99)), .01)
    contributions = contributions[REFERENCE - WINDOW + 1:]
    scores = contributions.mean(axis=1) / threshold
    totals = contributions.sum(axis=1, keepdims=True)
    shares = contributions / np.maximum(totals, 1e-9)
    return {'scores': numbers(scores), 'periods': confirmed_spans(scores),
            'contributions': {key: numbers(shares[:, i]) for i, key in enumerate(FEATURES)}}


def replay(kind):
    node, gpu, title, category, metric = DEVICES[kind]
    offset = tuple(DEVICES).index('drift' if kind == 'normal' else kind)
    # Use the same sensor generator as the exporter simulator, with independent noise
    # for the normal reference and replay. Slow the synthetic workload cycle.
    timeline = np.arange(-REFERENCE, POINTS) * STEP * .22
    history = healthy(timeline[:REFERENCE], gpu, 81 + offset)
    values = healthy(timeline[REFERENCE:], gpu, 173 + offset)
    if kind == 'drift':
        values['gpu_temp'][35:] += np.minimum(np.arange(1, POINTS - 34) * 3.4, 17)
    elif kind == 'rule':
        values['power'][36:] += 82
        values['sm_clock'][36:] -= 235
    elif kind == 'joint':
        values['memory_temp'][36:] += 4.8
        values['mem_util'][36:] -= 3.5
        values['power'][36:] += 18
    elif kind == 'gap':
        values['power'][39:] = np.nan
        values['mem_util'][39:] = np.nan

    trends = {
        field: {method: trend(history[field], values[field], field, method) for method in TREND_METHODS}
        for field in FEATURES
    }
    white = white_box(history, values)
    black = joint_pca(history, values)
    valid_counts = np.sum(np.isfinite([values[key] for key in FEATURES]), axis=0)

    return {
        'id': kind, 'title': title, 'category': category, 'node': node, 'gpu': gpu,
        'uuid': f'GPU-SRE-SIM-{offset:04d}', 'primaryMetric': metric,
        'series': {key: numbers(values[key]) for key in FEATURES},
        'standardized': {
            key: numbers((values[key] - history[key][:FIT].mean()) / history[key][:FIT].std())
            for key in FEATURES
        },
        'trends': trends, 'white': white, 'black': black,
        'quality': {
            'validFields': valid_counts.tolist(),
            'periods': confirmed_spans(np.where(valid_counts < len(FEATURES), 1., 0.)),
        },
    }


@lru_cache(maxsize=len(SCENARIOS))
def build_preview(scenario):
    if scenario not in SCENARIOS:
        raise ValueError('未知回放场景')
    return {
        'simulation': True, 'scenario': scenario, 'start': START, 'step': STEP, 'points': POINTS,
        'referencePoints': REFERENCE, 'confirmation': CONFIRM, 'jointWindow': WINDOW,
        'metrics': {key: {'name': METRICS[key]['name'], 'unit': UNITS[key]} for key in FEATURES},
        'devices': [replay(kind) for kind in SCENARIOS[scenario]],
    }


def build_incident_example(now):
    """Synthetic online-state examples for the incident queue, without mutating the store."""
    from .incident_queue import attach_incident_evidence, build_incident_queue

    cluster = '示例集群'
    entities = [
        {'id': f'{cluster}|GPU-QUEUE-EXAMPLE-{i}', 'cluster': cluster, 'uuid': f'GPU-QUEUE-EXAMPLE-{i}',
         'node': 'train-example-01' if i < 2 else 'infer-example-02', 'source_type': 'simulated',
         'fresh': i != 2, 'quality': {key: 'missing' if i == 2 else 'valid' for key in FEATURES}}
        for i in range(4)
    ]
    templates = {
        'trend': {'kind': 'univariate', 'targets': ['gpu_temp'], 'required': ['gpu_temp'], 'name': 'GPU 温度趋势'},
        'joint': {'kind': 'multivariate', 'targets': ['util', 'power', 'sm_clock'],
                  'required': ['util', 'power', 'sm_clock'], 'name': '功耗与时钟联合偏离'},
        'scene': {'kind': 'multivariate', 'targets': ['power', 'sm_clock'],
                  'required': ['util', 'power', 'sm_clock'], 'features': ['util'],
                  'directions': ['high', 'low'], 'name': '同负载下功耗与时钟偏离'},
    }
    tasks = [
        {'id': key, 'entity': entities[index]['id'], 'template': template, 'enabled': True, 'active_model': 'example',
         'notification_mode': policy}
        for key, index, template, policy in (
            ('trend', 0, 'trend', 'alert'), ('joint', 0, 'joint', 'evidence'), ('pending', 1, 'trend', 'alert'),
            ('held', 2, 'scene', 'alert'), ('recovered', 3, 'joint', 'alert'), ('condition', 0, 'scene', 'evidence'),
        )
    ]
    tasks[3]['scenario_id'] = 'power_clock_example'
    tasks[-1]['scenario_id'] = 'power_clock_example'
    end = int(now)
    states = [
        {'id': 'trend', 'active': True, 'opened_at': end - 11 * 60, 'pending': 4, 'score': 1.81,
         'threshold': 1.12, 'reason_metric': 'gpu_temp', 'contributions': {'gpu_temp': 1.81}},
        {'id': 'joint', 'active': True, 'opened_at': end - 9 * 60, 'pending': 3, 'score': 2.22,
         'threshold': 1.03, 'reason_metric': 'sm_clock', 'contributions': {'sm_clock': 2.22, 'power': 1.6}},
        {'id': 'pending', 'active': False, 'pending': 2, 'score': 1.22, 'threshold': 1.12,
         'reason_metric': 'gpu_temp'},
        {'id': 'held', 'active': True, 'opened_at': end - 6 * 60},
        {'id': 'recovered', 'active': False, 'opened_at': end - 50 * 60, 'closed_at': end - 25 * 60,
         'reason': 'fresh_normal_confirmed', 'clear_count': 3},
        {'id': 'condition', 'active': True, 'opened_at': end - 10 * 60, 'pending': 3,
         'score': 1.68, 'threshold': 1.04, 'reason_metric': 'power',
         'contributions': {'power': 1.68, 'sm_clock': 1.34}},
    ]
    for state in states:
        state.update(last_source=end - 2, quality='valid', model_id='example')
    states[3].update(last_source=end - 130, quality='missing')
    bindings = [{'id': key, 'rule_id': i} for i, key in enumerate(('trend', 'held', 'recovered'), 100)]
    nightingale = {
        'connected': True, 'checked_at': end - 4,
        'events': [{'id': 412, 'rule_id': 100, 'trigger_time': end - 11 * 60 + 8, 'hash': 'example-a'}],
        'history': [{'id': 410, 'rule_id': 102, 'trigger_time': end - 49 * 60,
                     'hash': 'example-b', 'is_recovered': True}],
    }
    queue = build_incident_queue(entities, tasks, states, templates, bindings, nightingale, now)
    queue['traces'] = {
        signal['id']: incident_example_trace(signal, end)
        for group in queue['groups'] for signal in group['members']
    }
    methods = {'univariate': 'rolling_median', 'multivariate': 'joint_pca', 'scenario': 'dcgm_conditional'}

    def read_points(members):
        return {(member['id'], member['start'], member['episode_id']): point
                for member in members for point in queue['traces'][member['id']] if point['t'] == member['start']}

    attach_incident_evidence(queue, read_points, [{'id': key, 'algorithm': method} for key, method in methods.items()])
    return queue


def incident_example_trace(signal, now):
    """Synthetic curves aligned to the queue example's device and episode times."""
    start = int(signal['start'])
    last = int(min((signal['end'] or now) + 120, now, signal['last_sample']))
    cadence = 10
    times = np.arange(start - 120, last + 1, cadence)
    if times[-1] < last:
        times = np.r_[times, last]
    baseline = healthy((times - start) * .36)
    onset = start - cadence * (signal['confirmation'] - 1 if signal['phase'] != 'pending' else signal['pending'] - 1)
    active = (times >= onset) & (times < ((signal['end'] or now) - (20 if signal['end'] else 0)))
    threshold = signal['threshold'] or 1.08
    scores = np.where(active, signal['score'] or 1.7, .48 + .15 * np.sin((times-start)/45))
    shifts = {'gpu_temp': 9, 'power': 48, 'sm_clock': -165, 'util': 4}
    points = []
    for i, stamp in enumerate(times):
        reference = {key: round(float(baseline[key][i]), 2) for key in signal['metrics']}
        values = {key: round(float(baseline[key][i]) + (shifts[key] if active[i] else 0), 2)
                  for key in signal['inputs']}
        points.append({
            't': int(stamp), 'values': values, 'expected': reference,
            'bounds': {key: [value - 2, value + 2] for key, value in reference.items()} if signal['family'] == 'univariate' else {},
            'score': round(float(scores[i]), 3), 'threshold': threshold, 'anomaly': bool(scores[i] > threshold),
            'active': bool(signal['phase'] != 'pending' and start <= stamp < (signal['end'] or now)),
            'contributions': signal['contributions'] if active[i] else {},
            'cadence_seconds': cadence, 'model': signal['family'],
        })
    return points
