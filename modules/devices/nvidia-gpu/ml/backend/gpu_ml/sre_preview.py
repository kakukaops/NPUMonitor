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
