"""A causal, read-only node review over bundled, generated and collected DCGM."""

import json
import time

import joblib
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

from .dcgm_detection import (PUBLIC, STEP, TRAINING_LOCK, WINDOW, alarm_evidence, features,
                             input_available, public_capture, public_catalog, public_model, scores, transform, unpack)
from .dcgm_sources import model_paths, source_capture, validate_scope
from .monitor_view import SAMPLES
from .settings import SIMULATION
from .simulation import CLUSTER as DEMO_CLUSTER

REVIEW_MINUTES = 30
REFERENCE_MINUTES = 720
TREND_FIELDS = {
    'DCGM_FI_DEV_GPU_TEMP': 2., 'DCGM_FI_DEV_MEMORY_TEMP': 2., 'DCGM_FI_DEV_POWER_USAGE': 15.,
    'DCGM_FI_DEV_GPU_UTIL': 10., 'DCGM_FI_DEV_MEM_COPY_UTIL': 10., 'DCGM_FI_DEV_SM_CLOCK': 100.,
}


def review_target(engine, source, cluster, node, gpu):
    if source == 'synthetic' and SIMULATION:
        return ()
    if source not in ('simulated', 'real_unverified'):
        raise ValueError('请选择有效的检测数据源')
    if not gpu and node:
        validate_scope(engine, source, cluster, node)
        return ()
    entries = [entity for entity in engine.store.list('entity')
               if entity.get('source_type') == source and entity.get('cluster') == cluster and not entity.get('node')]
    if source == 'simulated' and cluster == DEMO_CLUSTER and not gpu and not node:
        cards = sorted({e['uuid'] for e in entries})
    else:
        cards = sorted({e['uuid'] for e in entries if e['uuid'] == gpu}) if gpu and not node else []
    if not cards:
        raise ValueError('请选择已发现的节点或 GPU')
    return tuple(cards)


def public_review_capture(collection, at):
    row = next((r for r in public_catalog()['collections'] if r['id'] == collection), None)
    if not row:
        raise ValueError('采集区间不存在')
    end = row['end'] if at is None else int(at)
    if not row['start'] <= end <= row['end']:
        raise ValueError('复核时刻不在采集区间内')
    i = (end - row['start']) // STEP
    payload = json.loads((PUBLIC / (collection + '.json')).read_text())
    cap = public_capture(collection)
    cards = {}
    for item in payload['gpus']:
        card = item['id']
        columns = [payload['native'][key]['gpus'].get(card) for key in public_catalog()['metrics']]
        series = np.column_stack([unpack(value)[:i + 1] if value else np.full(i + 1, np.nan)
                                  for value in [*columns, None]])
        if np.isfinite(series).any():
            cards[card] = series
    return cap, cards, i, row['node'], row['fold']


def minute_series(values, start):
    if not len(values):
        return np.empty(0), np.empty(0)
    times = start + STEP * np.arange(len(values))
    # Aggregate elapsed bins. The full minute ending at t includes samples t-60 through t-10.
    begin = (times[0] + 59) // 60 * 60
    end = times[-1] // 60 * 60
    if end <= begin:
        return np.empty(0), np.empty(0)
    left = (begin - start + STEP - 1) // STEP
    n = (end - begin) // 60
    matrix = values[left:left + n * 6].reshape(-1, 6)
    valid = np.isfinite(matrix)
    count = valid.sum(axis=1)
    means = np.divide(np.where(valid, matrix, 0).sum(axis=1), count,
                      out=np.full(n, np.nan), where=count >= 3)
    return begin + 60 * np.arange(1, n + 1), means


def _finite(value):
    return float(value) if np.isfinite(value) else None


def card_trend(epochs, y, floor, excluded):
    cutoff = max(0, len(y) - REVIEW_MINUTES)
    history_start = max(0, cutoff - REFERENCE_MINUTES)
    # Short collector histories get their own chronological fit/calibration using only seen reference minutes.
    scope = np.flatnonzero(np.isfinite(y[history_start:cutoff]) & ~excluded[history_start:cutoff]) + history_start
    result = {'state': 'insufficient_history', 'points': [
        {'t': int(epochs[i]), 'value': _finite(y[i]), 'lower': None, 'upper': None, 'alarm': False}
        for i in range(cutoff, len(y))
    ]}
    if len(scope) < 85 or len(y) <= 12:
        return result
    split = scope[min(len(scope) - 25, len(scope) * 4 // 5)]
    seq = sliding_window_view(y, 13)
    t = np.arange(12, len(y))
    valid = np.isfinite(seq).all(axis=1)
    eligible = valid & ~sliding_window_view(excluded, 13).any(axis=1)
    fit = eligible & (t >= history_start + 12) & (t < split)
    cal = eligible & (t >= split) & (t < cutoff)
    if fit.sum() < 60 or cal.sum() < 25:
        return result
    prior = seq[:, :-1]
    x = np.column_stack((prior[:, [-1, -2, -3, -6, -12]], prior[:, -5:].mean(axis=1)))
    inside = valid & (t >= split)
    lower = np.full(len(y), np.nan)
    upper = lower.copy()
    bounds = []
    for q in (.05, .95):
        mdl = HistGradientBoostingRegressor(loss='quantile', quantile=q, max_iter=28, max_leaf_nodes=7,
                                            min_samples_leaf=16, early_stopping=False, random_state=1857)
        mdl.fit(x[fit], seq[fit, -1])
        bounds.append(mdl.predict(x[inside]))
    lower[t[inside]], upper[t[inside]] = np.sort(bounds, axis=0)
    error = np.maximum(lower - y, y - upper)
    pad = max(floor / 4., float(np.quantile(error[t[cal]], .995)))
    lower -= pad
    upper += pad
    anomaly = np.maximum(lower - y, y - upper) > 0
    consecutive = np.r_[False, False, sliding_window_view(anomaly, 3).all(axis=1)]
    duration = 0
    for flag in anomaly[::-1]:
        if not flag:
            break
        duration += 1
    strength = max(0., float(max(lower[-1] - y[-1], y[-1] - upper[-1])) / floor) if consecutive[-1] else 0.
    return {'state': 'alarm' if consecutive[-1] else 'scored' if np.isfinite(lower[-1]) else 'missing',
            'duration': duration if consecutive[-1] else 0, 'strength': strength,
            'fit': int(fit.sum()), 'calibration': int(cal.sum()),
            'points': [{'t': int(epochs[i]), 'value': _finite(y[i]), 'lower': _finite(lower[i]),
                        'upper': _finite(upper[i]), 'alarm': bool(consecutive[i])} for i in range(cutoff, len(y))]}


def condition_evidence(rows, excluded):
    util = rows['DCGM_FI_DEV_GPU_UTIL']
    memory = rows['DCGM_FI_DEV_MEM_COPY_UTIL']
    x = np.column_stack((util, memory)) / 100.
    cutoff = len(x) - REVIEW_MINUTES
    if cutoff < 85 or not np.isfinite(x[-3:]).all():
        return []
    first = max(0, cutoff - REFERENCE_MINUTES)
    candidates = np.flatnonzero(np.isfinite(x[first:cutoff]).all(axis=1) & ~excluded[first:cutoff]) + first
    if len(candidates) < 85:
        return []
    split = candidates[min(len(candidates) - 25, len(candidates) * 4 // 5)]
    fit_x = candidates[candidates < split]
    cal_x = candidates[candidates >= split]
    inside = (x[-3:] >= x[fit_x].min(axis=0) - .1) & (x[-3:] <= x[fit_x].max(axis=0) + .1)
    if not inside.all():
        return []
    out = []
    for field in ('DCGM_FI_DEV_GPU_TEMP', 'DCGM_FI_DEV_POWER_USAGE', 'DCGM_FI_DEV_SM_CLOCK'):
        y = rows[field]
        fit = fit_x[np.isfinite(y[fit_x])]
        cal = cal_x[np.isfinite(y[cal_x])]
        if len(fit) < 60 or len(cal) < 25 or not np.isfinite(y[-3:]).all():
            continue
        model = Ridge(alpha=1.).fit(x[fit], y[fit])
        largest = max(TREND_FIELDS[field], np.quantile(np.abs(y[cal] - model.predict(x[cal])), .995))
        predicted = model.predict(x[-3:])
        ratio = np.abs(y[-3:] - predicted) / largest
        if ratio.min() > 1.:
            out.append({'metric': field, 'ratio': float(ratio[-1]), 'expected': float(predicted[-1]),
                        'observed': float(y[-1])})
    return sorted(out, key=lambda item: -item['ratio'])


def review_cards(cards, start, end):
    fields = public_catalog()['metrics']
    results = []
    # Limit nested OpenMP during local quantile fitting. This handler runs on explicit review requests.
    with TRAINING_LOCK, threadpool_limits(limits=1):
        for uuid, card in cards.items():
            xid = _finite(card[end, -1])
            unavailable = [field for i, field in enumerate(fields) if field in TREND_FIELDS
                           and not np.isfinite(card[end, i]) and np.isfinite(card[:end + 1, i]).any()]
            trends = {}
            # Even a single nonzero scrape removes its minute from the normal reference.
            evidence = (card[:end + 1, -1] > 0).astype(float)
            epochs, code = minute_series(evidence, start)
            excluded = code > 0
            series_by_field = {}
            for field, floor in TREND_FIELDS.items():
                _, series = minute_series(card[:end + 1, fields.index(field)], start)
                series_by_field[field] = series
                trends[field] = card_trend(epochs, series, floor, excluded)
            results.append({'gpu': uuid, 'xid': xid, 'missing': unavailable, 'trends': trends,
                            'condition': condition_evidence(series_by_field, excluded),
                            'observed': bool(np.isfinite(card[end, :-1]).any())})
    return sorted(results, key=lambda card: (
        -int(card['xid'] is not None and card['xid'] > 0),
        -max((t.get('strength', 0.) for t in card['trends'].values()), default=0.),
        -max((t['ratio'] for t in card['condition']), default=0.), card['gpu']))


def node_model(engine, source, cluster, node, at, fold, fallback):
    if source in ('simulated', 'real_unverified') and node and not fallback:
        _, active = model_paths(engine, source, cluster, node, 'core', 'shallow_tree', 'supervised')
        with TRAINING_LOCK:
            if active.is_file():
                local = joblib.load(active)
                if at >= local['trained_through'] + WINDOW * STEP:
                    return local, '本节点已启用版本'
    with TRAINING_LOCK, threadpool_limits(limits=1):
        model = public_model(fold, 'core', 'shallow_tree', 'supervised')
    return model, 'GWDG 留出节点版本' if source == 'public' else 'GWDG 参考版本 · 跨源影子评分'


def review_node(cap, i, model_loader):
    out = {'state': 'warmup' if i < WINDOW - 1 else 'missing', 'evidence': []}
    if i < WINDOW - 1 or not input_available(cap, 'core')[i]:
        return out
    try:
        model, version = model_loader()
    except ValueError as exc:
        return {'state': 'untrained', 'detail': str(exc), 'evidence': []}
    available = input_available(cap, 'core')
    idx = np.arange(max(WINDOW - 1, i - REVIEW_MINUTES * 6 + 1), i + 1)
    idx = idx[available[idx]]
    raw = features(cap, 'core', idx)
    normalized = transform(model, raw)
    result = scores(model, normalized)
    alarm = result > model['threshold']
    xid = cap.xid[idx]
    return {'state': 'alarm' if alarm[-1] else 'scored', 'score': float(result[-1]),
            'threshold': model['threshold'], 'version': version,
            'evidence': alarm_evidence(model, raw[-1], normalized[-1]) if alarm[-1] else [],
            'summary': {'scored_points': len(idx), 'model_points': int(alarm.sum()),
                        'xid_zero_points': int(np.sum(alarm & (xid == 0))),
                        'xid_unknown_points': int(np.sum(alarm & ~np.isfinite(xid)))}}


def node_review(engine, source, cluster='', node='', gpu='', collection='', at=None, scenario='normal'):
    fallback, fold = (), None
    if source == 'public':
        cap, cards, i, node, fold = public_review_capture(collection, at)
    else:
        fallback = review_target(engine, source, cluster, node, gpu)
        now = int(time.time())
        if at is not None and not 0 < at <= now:
            raise ValueError('请选择有效的历史复核时间')
        end = ((now if at is None else at) // STEP) * STEP
        start = max(0, end - (REFERENCE_MINUTES + REVIEW_MINUTES + 14) * 60)
        if scenario not in SAMPLES:
            raise ValueError('未知人工构造场景')
        # Gap samples end at a point inside the constructed interruption.
        changed = end - (120 if scenario == 'gap' else 12 * 60) if source == 'synthetic' else None
        cap, cards = source_capture(engine.source, source, cluster, node, start, end, scenario,
                                    fallback_cards=fallback, change_at=changed)
        i = len(cap.xid) - 1
    timestamp = cap.start + i * STEP
    node_evidence = review_node(cap, i, lambda: node_model(engine, source, cluster, node, timestamp, fold, fallback))
    card_evidence = review_cards(cards, cap.start, i)
    return {'source': source, 'cluster': cluster, 'node': node or (DEMO_CLUSTER if source == 'simulated'
            else gpu or '人工构造节点'), 'identity': 'gpu' if gpu else 'simulation' if fallback else 'node',
            'at': timestamp, 'xid': _finite(cap.xid[i]), 'node_detection': node_evidence, 'cards': card_evidence,
            'source_unavailable': not cards}
