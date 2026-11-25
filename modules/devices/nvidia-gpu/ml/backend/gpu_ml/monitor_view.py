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


def replay_input(rows, required, task, start=None):
    """Score each new source sample at most once and retain invalid evaluation slots."""
    inputs, last = [], -math.inf
    for row in rows:
        if 'quality' in row:
            continue
        if any(key not in row['values'] for key in required):
            row['quality'] = 'missing'
            continue
        if task and task['template'] == 'activity' and row['values'].get('job_running') != 1:
            row['quality'] = 'context_inactive'
            continue
        stamp = row.get('source_time', row['t'])
        if stamp <= last or (start is not None and stamp < start):
            row['quality'] = 'held_sample'
            continue
        last = stamp
        inputs.append({'t': stamp, 'values': {key: row['values'][key] for key in required}})
    return inputs


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
        quality = row.get('quality')
        if quality == 'held_sample':
            continue
        prediction = by_time.get(row.get('source_time', stamp)) if not quality else None
        was_active = state['active']
        if prediction:
            quality = 'valid'
            result = {**prediction, 'model': model_id, 'cadence_seconds': step}
        else:
            quality = quality or ('missing' if any(metric not in row['values'] for metric in required)
                                  else 'reference_window_incomplete' if model_id else 'untrained')
            result = None
        advance_detector_state(state, result, quality, stamp, confirmation, recovery)
        if state['active'] and not was_active:
            episodes.append({'start': result['t'], 'end': None})
        elif was_active and not state['active']:
            episodes[-1]['end'] = result['t']
        out.append({
            **(result or row), 'values': row['values'], 'quality': quality,
            'active': state['active'], 'pending': state['pending'], 'cadence_seconds': step,
            'input_issues': row.get('input_issues', {}),
        })
    return sorted(out, key=lambda point: point['t']), state, episodes


def recorded_episodes(points):
    episodes = []
    last_id = None
    for point in points:
        if point.get('active'):
            episode_id = point.get('episode_id')
            if last_id and episode_id and last_id != episode_id and episodes[-1]['end'] is None:
                episodes[-1]['end'] = point['t']
            if not episodes or episodes[-1]['end'] is not None:
                episodes.append({'start': point['t'], 'end': None})
            last_id = episode_id
        elif episodes and episodes[-1]['end'] is None:
            episodes[-1]['end'] = point['t']
    return episodes


def association_snapshot(points, episodes, online_state=None):
    """Explain one historical decision without inventing per-feature attribution."""
    scored = [point for point in points if math.isfinite(point.get('score', math.nan))
              and math.isfinite(point.get('threshold', math.nan)) and point['threshold'] > 0]
    if not scored:
        return None
    if online_state is not None:
        point = scored[-1]
        current = (online_state.get('quality') == 'valid' and point['t'] == online_state.get('last_source')
                   and point.get('model') == online_state.get('model_id'))
        selection = 'current' if current else 'last_valid'
        return evidence_snapshot(point, selection)
    event = episodes[-1] if episodes else None
    event_points = [point for point in scored if event and point.get('anomaly')
                    and point['t'] >= event['start'] and (event['end'] is None or point['t'] < event['end'])]
    candidates = event_points or [point for point in scored if point.get('anomaly')]
    point = max(candidates, key=lambda row: row['score'] / row['threshold']) if candidates else scored[-1]
    return evidence_snapshot(point, 'confirmed_peak' if event_points else 'candidate_peak' if candidates else 'latest')


def evidence_snapshot(point, selection):
    keys = ('t', 'model', 'score', 'threshold', 'values', 'expected', 'contributions',
            'joint_distance_score', 'evidence', 'reference_kind')
    return {**{key: point[key] for key in keys if key in point}, 'selection': selection}


def summarize_confirmations(replay, episodes, labels):
    """Event metrics for the applied confirmation policy, using explicit annotations."""
    opening_times = [episode['start'] for episode in episodes]
    score_times = sorted(point['t'] for point in replay if point['quality'] == 'valid')
    fault, normal = [], []
    for label in labels:
        kind, start, end = label['kind'], label['start'], label['end']
        if kind not in ('fault', 'normal_change'):
            continue
        openings = [opened for opened in opening_times if start <= opened < end]
        scored = sum(start <= stamp < end for stamp in score_times)
        record = {'start': start, 'end': end, 'scored_points': scored, 'confirmed': len(openings)}
        if kind == 'fault':
            record['delay_seconds'] = openings[0] - start if openings else None
            fault.append(record)
        else:
            normal.append(record)
    fault_hits = sum(bool(row['confirmed']) for row in fault)
    normal_hits = sum(bool(row['confirmed']) for row in normal)
    normal_days = sum(row['end'] - row['start'] for row in normal) / 86400
    delays = [row['delay_seconds'] for row in fault if row['delay_seconds'] is not None]
    return {
        'confirmed_episodes': len(episodes), 'fault_windows': len(fault), 'fault_hits': fault_hits,
        'unscored_fault_windows': sum(not row['scored_points'] for row in fault),
        'event_recall': fault_hits / len(fault) if fault else None,
        'normal_windows': len(normal), 'normal_alert_windows': normal_hits,
        'normal_window_false_alarm_rate': normal_hits / len(normal) if normal else None,
        'normal_days': normal_days,
        'false_episodes_per_100_normal_days': 100 * sum(row['confirmed'] for row in normal) / normal_days if normal_days else None,
        'median_detection_delay_seconds': float(np.median(delays)) if delays else None,
        'unscored_fraction': 1 - len(score_times) / len(replay) if replay else None,
        'fault_details': fault,
    }


def monitor_view(engine, entity_id, task_id, metric, source, mode, span, scenario, start=None, end=None,
                 include_inputs=False, replay_model=None):
    if source not in ('prometheus', 'sample') or mode not in ('online', 'recorded', 'replay'):
        raise ValueError('数据来源或显示方式无效')
    if source == 'sample' and (not SIMULATION or mode != 'replay' or scenario not in SAMPLES):
        raise ValueError('内置样例仅用于模拟环境的回放')
    if metric not in METRICS or not 300 <= span <= 3600:
        raise ValueError('时间范围或指标无效')
    now = time.time()
    if start is None and end is None and mode != 'recorded':
        end = int(now) - (4 if mode == 'replay' else 0)
        start = end - span
    elif (start is None or end is None or source != 'prometheus' or mode == 'online'
          or not now - 7 * 86400 <= start < end <= now or end - start > 3 * 3600):
        raise ValueError('历史视图支持最近 7 天内最长 3 小时的固定区间')
    entity = engine.store.get('entity', entity_id)
    if not entity:
        raise ValueError('GPU 不存在')
    task = engine.store.get('task', task_id) if task_id else None
    if task_id and (not task or task['entity'] != entity_id or (task.get('deleted') and mode != 'recorded')):
        raise ValueError('任务与 GPU 不匹配')
    spec = TEMPLATES[task['template']] if task else None
    if spec and metric not in spec['targets'] and (not include_inputs or metric not in spec['required']):
        raise ValueError('指标不属于当前任务')
    if replay_model and (not task or mode != 'replay'):
        raise ValueError('指定模型仅支持任务的历史回放')
    model_id = replay_model or (task.get('active_model') if task else None)
    record = engine.store.get('model', model_id) if model_id else None
    if replay_model and (not record or record['status'] not in ('validated', 'published')
                         or (record['entity'], record['template'], record['source_type']) !=
                         (task['entity'], task['template'], task['scope'])):
        raise ValueError('此模型版本不可用于该任务的回放')
    state, episodes = {}, []
    observation_error = False
    required = spec['required'] if spec and (model_id or include_inputs) else [metric]
    show = list(dict.fromkeys([*spec['targets'], *required, metric])) if spec and include_inputs else [metric]
    if mode in ('online', 'recorded'):
        points = engine.store.history(task_id, start, end) if task else []
        episodes = recorded_episodes(points)
        step = max(2, int(points[-1].get('cadence_seconds', 2))) if points else 10
        observations = {key: [] for key in show}
        frames = []
        try:
            frames, observations = engine.source.monitor_history(entity_id, start, end, step, required, show)
        except (ValueError, RuntimeError, OSError):
            observation_error = True
        for key, series in observations.items():
            observed = {point['t']: point for point in series}
            for point in points:
                if key in point['values']:
                    observed[point['t']] = {'t': point['t'], 'values': {key: point['values'][key]},
                                           'cadence_seconds': point.get('cadence_seconds', step)}
            observations[key] = [observed[t] for t in sorted(observed)]
        if mode == 'online' and task:
            state = engine.store.get('state', task_id) or {}
            if not task.get('enabled') or not (engine.store.get('system', 'inference') or {'enabled': True})['enabled']:
                state['quality'] = 'paused'
            elif state.get('quality') == 'valid' and state.get('model_id') != model_id:
                state['quality'] = 'model_changed'
            elif state.get('quality') == 'valid' and not engine.observation_is_fresh(state.get('last_source', 0)):
                state['quality'] = 'inference_stale'
    else:
        model = engine.load(model_id) if model_id else None
        step = max(2, int(getattr(model, 'cadence', 10)))
        if source == 'sample':
            frames = sample_rows(start, end, step, metric, scenario)
            observations = {key: [{'t': row['t'], 'values': {key: row['values'][key]}, 'cadence_seconds': step}
                                  for row in frames if key in row['values']] for key in show}
        else:
            frames, observations = engine.source.monitor_history(entity_id, start, end, step, required, show)
        usable = replay_input(frames, required, task, start)
        scored = engine.score(model, usable, task.get('sensitivity', 1.)) if model and usable else []
        points, state, episodes = replay_results(frames, scored, task, model_id, step, required)
        frames = points
    intervals = quality_intervals(frames, step, end)
    points = [point for point in points if start <= point['t'] <= end]
    snapshot = association_snapshot(points, episodes, state if mode == 'online' else None) if include_inputs else None
    keys = ('t', 'values', 'expected', 'bounds', 'score', 'threshold', 'anomaly', 'active',
            'quality', 'cadence_seconds', 'model', 'pipeline_id', 'decision_config_revision',
            'reference_kind', 'effective_task_factor', 'confirmation_samples', 'recovery_samples')
    points = [{key: point[key] for key in keys if key in point} for point in points]
    versions = {}
    decisions = {}
    for point in points:
        used = point.get('model')
        if used and used not in versions:
            saved = engine.store.get('model', used) or {}
            versions[used] = saved.get('algorithm')
        revision = point.get('decision_config_revision')
        if used and revision is not None:
            decisions[(used, revision)] = {'model': used, 'revision': revision, 'factor': point.get('effective_task_factor'),
                                          'confirmation': point.get('confirmation_samples'), 'recovery': point.get('recovery_samples')}
    return {
        'source': source, 'mode': mode, 'start': start, 'end': end, 'metric': metric,
        'model': {'id': model_id, 'algorithm': record['algorithm']} if record else None,
        'confirmation': task.get('confirmation_samples', 3) if task else None,
        'recovery': task.get('recovery_samples', 3) if task else None,
        'sensitivity': task.get('sensitivity', 1.) if task else None,
        'points': points, 'observations': observations[metric], 'input_observations': observations if include_inputs else {},
        'observation_error': observation_error,
        'state': state, 'episodes': episodes, 'quality_intervals': intervals, 'versions': versions,
        'association_evidence': snapshot,
        'recorded_decisions': list(decisions.values()) if mode == 'recorded' else [],
    }


def quality_intervals(frames, step, end):
    intervals = []
    for frame in sorted(frames, key=lambda row: row['t']):
        quality = frame.get('quality')
        if not quality or quality in ('valid', 'untrained', 'held_sample') or frame['t'] >= end:
            continue
        issues = frame.get('input_issues', {})
        previous = intervals[-1] if intervals else None
        stop = min(end, frame['t'] + step)
        if previous and previous['quality'] == quality and previous['inputs'] == issues and previous['end'] == frame['t']:
            previous['end'] = stop
        else:
            intervals.append({'start': frame['t'], 'end': stop, 'quality': quality, 'inputs': issues})
    return intervals
