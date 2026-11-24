"""A common read-only view of persisted live results and isolated replay results."""

import math
import time

import numpy as np

from .settings import METRICS, SIMULATION, TEMPLATES
from .simulation import healthy
from .store import advance_detector_state


SAMPLES = ('normal', 'drift', 'relation', 'gap')
SHIFTS = {'gpu_temp': 16, 'memory_temp': 14, 'power': 100, 'sm_clock': -265,
          'mem_clock': -100, 'util': -25, 'mem_util': -20, 'fb_used': 7500}


def sample_rows(start, end, step, metric, scenario):
    stamps = np.arange(math.ceil(start / step) * step, end + 1e-6, step)
    offsets = stamps - start
    values = healthy(offsets, seed=717)
    begin = (end - start) * .42
    changed = offsets >= begin
    if scenario == 'drift':
        values[metric] = values[metric] + SHIFTS.get(metric, 2) * np.clip((offsets - begin) / 20, 0, 1)
    elif scenario == 'relation':
        for key, delta in {'power': 82, 'sm_clock': -235, 'memory_temp': 5, 'mem_util': -6}.items():
            values[key][changed] += delta
    values = {key: np.clip(series, METRICS[key]['min'], METRICS[key]['max'])
              for key, series in values.items() if key in METRICS}
    return [
        {'t': float(stamp), 'values': {} if scenario == 'gap' and changed[i] and offsets[i] < begin * 1.5 else
         {key: float(series[i]) for key, series in values.items()}}
        for i, stamp in enumerate(stamps)
    ]


def history_with_metric(source, entity, start, end, step, required, metric):
    try:
        rows = source.history(entity, start, end, step, required)
    except ValueError as error:
        if str(error) != '历史缺少必需指标':
            raise
        rows = []
    if not rows and set(required) != {metric}:
        try:
            rows = source.history(entity, start, end, step, [metric])
        except ValueError as error:
            if str(error) != '历史缺少必需指标':
                raise
    return rows


def replay_results(rows, scored, task, model_id, step, required):
    state = {'id': task['id'] if task else '', 'active': False, 'quality': 'unverified',
             'last_source': 0, 'pending': 0, 'clear_count': 0, 'episode_id': None}
    confirmation = task.get('confirmation_samples', 3) if task else 3
    recovery = task.get('recovery_samples', 3) if task else 3
    by_time = {point['t']: point for point in scored}
    episodes = []
    out = []
    for row in rows:
        stamp = row['t']
        prediction = by_time.get(stamp)
        was_active = state['active']
        if prediction:
            quality = 'valid'
            result = {**prediction, 'model': model_id, 'cadence_seconds': step}
        else:
            quality = ('missing' if any(metric not in row['values'] for metric in required)
                       else 'reference_window_incomplete' if model_id else 'untrained')
            if task and task.get('template') == 'activity' and row['values'].get('job_running') == 0:
                quality = 'context_inactive'
            result = None
        advance_detector_state(state, result, quality, stamp, confirmation, recovery)
        if state['active'] and not was_active:
            episodes.append({'start': stamp, 'end': None})
        elif was_active and not state['active']:
            episodes[-1]['end'] = stamp
        out.append({
            **(result or row), 'values': row['values'], 'quality': quality,
            'active': state['active'], 'pending': state['pending'], 'cadence_seconds': step,
        })
    return out, state, episodes


def monitor_view(engine, entity_id, task_id, metric, source, mode, span, scenario):
    if source not in ('prometheus', 'sample') or mode not in ('online', 'replay'):
        raise ValueError('数据来源或显示方式无效')
    if source == 'sample' and (not SIMULATION or mode != 'replay' or scenario not in SAMPLES):
        raise ValueError('内置样例仅用于模拟环境的回放')
    if not 300 <= span <= 3600 or metric not in METRICS:
        raise ValueError('时间范围或指标无效')
    entity = engine.store.get('entity', entity_id)
    if not entity:
        raise ValueError('GPU 不存在')
    task = engine.store.get('task', task_id) if task_id else None
    if task_id and (not task or task['entity'] != entity_id or task.get('deleted')):
        raise ValueError('任务与 GPU 不匹配')
    if task and metric not in TEMPLATES[task['template']]['targets']:
        raise ValueError('指标不属于当前任务')
    model_id = task.get('active_model') if task else None
    record = engine.store.get('model', model_id) if model_id else None
    end = int(time.time()) - (4 if mode == 'replay' else 0)
    start = end - span
    state, episodes = {}, []
    required = TEMPLATES[task['template']]['required'] if model_id else [metric]
    if mode == 'online':
        points = engine.store.history(task_id, start, end) if model_id else []
        if not any(metric in point['values'] for point in points):
            points = history_with_metric(engine.source, entity_id, start, end, 10, [metric], metric)
            for point in points:
                point['cadence_seconds'] = 10
        state = (engine.store.get('state', task_id) or {}) if task else {}
        if task and not (engine.store.get('system', 'inference') or {'enabled': True})['enabled']:
            state['quality'] = 'paused'
        elif state.get('quality') == 'valid' and not engine.observation_is_fresh(state.get('last_source', 0)):
            state['quality'] = 'inference_stale'
    else:
        model = engine.load(model_id) if model_id else None
        step = max(2, int(getattr(model, 'cadence', 10)))
        rows = (sample_rows(start, end, step, metric, scenario) if source == 'sample'
                else history_with_metric(engine.source, entity_id, start, end, step, required, metric))
        usable = [row for row in rows if all(key in row['values'] for key in required)]
        if task and task['template'] == 'activity':
            usable = [row for row in usable if row['values'].get('job_running') == 1]
        scored = engine.score(model, usable, task.get('sensitivity', 1.)) if model and usable else []
        points, state, episodes = replay_results(rows, scored, task, model_id, step, required)
    keys = ('t', 'values', 'expected', 'bounds', 'score', 'threshold', 'anomaly', 'active',
            'quality', 'cadence_seconds', 'model', 'pipeline_id', 'decision_config_revision', 'reference_kind')
    points = [{key: point[key] for key in keys if key in point} for point in points]
    return {
        'source': source, 'mode': mode, 'start': start, 'end': end, 'metric': metric,
        'model': {'id': model_id, 'algorithm': record['algorithm']} if record else None,
        'confirmation': task.get('confirmation_samples', 3) if task else None,
        'recovery': task.get('recovery_samples', 3) if task else None,
        'sensitivity': task.get('sensitivity', 1.) if task else None,
        'points': points, 'state': state, 'episodes': episodes,
    }
