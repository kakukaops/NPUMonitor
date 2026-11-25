"""Node capture adapters and source-bound detector candidates."""
from hashlib import sha256
import json
import math
import os
import re
import tempfile
import time
import uuid

import joblib
import numpy as np

from .dcgm_detection import (
    Capture, STEP, WINDOW, TRAINING_LOCK, XID, assess, example_rows, feature_metrics, fit_detector,
    joint_point, public_catalog, validate_selection,
)
from .monitor_view import sample_rows
from .settings import DATA, DEFAULT_CLUSTER, METRICS, SIMULATION

KEYS = {spec['name']: spec for spec in METRICS.values()}


def selector(source_type, cluster, node, fallback_cards=()):
    # Match all three supported node label aliases, retaining original UUIDs.
    names = '|'.join([*public_catalog()['metrics'], XID])
    cluster_match = ('cluster_id=~' + json.dumps(re.escape(cluster) + '|') if cluster == DEFAULT_CLUSTER
                     else 'cluster_id=' + json.dumps(cluster))
    source_match = 'simulated="true"' if source_type == 'simulated' else 'simulated!="true"'
    match = f'__name__=~{json.dumps(names)},UUID!="",{cluster_match},{source_match}'
    if fallback_cards:
        uuids = json.dumps('|'.join(map(re.escape, fallback_cards)))
        return f'last_over_time({{{match},UUID=~{uuids},Hostname="",hostname="",node=""}}[10s])'
    # A range selector on each raw series avoids Prometheus' instant lookback
    # carrying a reading forward across a telemetry gap.
    return ' or '.join(f'last_over_time({{{match},{label}={json.dumps(node)}}}[10s])'
                       for label in ('Hostname', 'hostname', 'node'))


def valid_reading(metric, value):
    if not math.isfinite(value) or abs(value) >= 9e18:
        return False
    if metric in KEYS:
        limits = KEYS[metric]
        return limits['min'] <= value <= limits['max']
    if metric in ('DCGM_FI_DEV_DEC_UTIL', 'DCGM_FI_DEV_ENC_UTIL'):
        return 0 <= value <= 100
    return value >= 0


def build_capture(start, count, cards, seen):
    metrics = public_catalog()['metrics']
    values = np.stack([cards[card] for card in cards], axis=1)
    known = np.maximum.accumulate(np.stack([seen[card] for card in cards], axis=1), axis=0)
    present = np.isfinite(values[:, :, :len(metrics)]) & known[:, :, None]
    size = present.sum(axis=1)
    observations = values[:, :, :len(metrics)]
    means = np.divide(np.where(present, observations, 0).sum(axis=1), size,
                      out=np.full(size.shape, np.nan), where=size > 0)
    maxima = np.where(present, observations, -np.inf).max(axis=1)
    maxima[size == 0] = np.nan
    fractions = 1 - size / np.maximum(known.sum(axis=1, keepdims=True), 1)
    xid_reads = values[:, :, -1]
    xid = np.full(count, np.nan)
    xid[(known & (xid_reads == 0)).sum(axis=1) == known.sum(axis=1)] = 0
    xid[~known.any(axis=1)] = np.nan
    xid[(known & np.isfinite(xid_reads) & (xid_reads != 0)).any(axis=1)] = 1
    return Capture(start, np.stack((means, maxima, fractions), axis=-1), xid)


def source_capture(source, source_type, cluster, node, start, end, scenario='normal', *,
                   fallback_cards=(), change_at=None):
    metrics = public_catalog()['metrics']
    count = (end - start) // STEP + 1
    columns = {key: index for index, key in enumerate([*metrics, XID])}
    cards, seen, duplicates = {}, {}, set()
    if source_type == 'synthetic':
        values = np.full((count, len(columns)), np.nan)
        for row in sample_rows(start, end, STEP, 'gpu_temp', scenario, change_at):
            i = (int(row['t']) - start) // STEP
            for key, value in row['values'].items():
                col = columns.get(METRICS[key]['name'])
                if col is not None:
                    values[i, col] = value
        cards['人工构造 GPU'] = values
        seen['人工构造 GPU'] = np.ones(count, dtype=bool)
    else:
        query = selector(source_type, cluster, node, fallback_cards)
        for first in range(start, end + 1, 6 * 3600):
            last = min(end, first + 6 * 3600 - STEP)
            for row in source.query(query, first, last, STEP):
                labels = row['metric']
                metric, card = labels.get('__name__'), labels.get('UUID')
                if metric not in columns or not card or labels.get('GPU_I_ID') or labels.get('GPU_I_PROFILE'):
                    continue
                if (labels.get('cluster_id', DEFAULT_CLUSTER) != cluster
                        or (labels.get('simulated') == 'true') != (source_type == 'simulated')):
                    continue
                aliases = {labels[key] for key in ('Hostname', 'hostname', 'node') if labels.get(key)}
                if (aliases != {node} if not fallback_cards else bool(aliases) or card not in fallback_cards):
                    continue
                if card not in cards:
                    cards[card] = np.full((count, len(columns)), np.nan)
                    seen[card] = np.zeros(count, dtype=bool)
                col = columns[metric]
                for stamp, raw in row['values']:
                    i = int((stamp - start) / STEP)
                    if not 0 <= i < count or stamp != start + i * STEP:
                        continue
                    seen[card][i] = True
                    value = float(raw)
                    point = (card, i, col)
                    if point in duplicates or not valid_reading(metric, value):
                        continue
                    old = cards[card][i, col]
                    if np.isfinite(old) and old != value:
                        duplicates.add(point)
                        cards[card][i, col] = np.nan
                    else:
                        cards[card][i, col] = value
    if not cards:
        channels = np.full((count, len(metrics), 3), np.nan)
        channels[:, :, 2] = 1
        return Capture(start, channels, np.full(count, np.nan)), cards
    return build_capture(start, count, cards, seen), cards


def validate_scope(engine, source_type, cluster, node):
    if source_type == 'synthetic' and SIMULATION and cluster == node == 'synthetic':
        return
    if source_type not in ('simulated', 'real_unverified') or not any(
        entity.get('source_type') == source_type and entity.get('cluster') == cluster and entity.get('node') == node
        for entity in engine.store.list('entity')
    ):
        raise ValueError('请选择拥有明确来源与节点标识的 GPU')


def model_paths(engine, source_type, cluster, node, metric, method, mode):
    validate_scope(engine, source_type, cluster, node)
    validate_selection(metric, method, mode)
    binding = [1, engine.source.url if source_type != 'synthetic' else 'sample-v1',
               source_type, cluster, node, metric, method, mode]
    prefix = sha256(json.dumps(binding).encode()).hexdigest()
    folder = DATA / 'dcgm-detection'
    return folder / (prefix + '.candidate'), folder / (prefix + '.active')


def save_model(path, model):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        stage = temp.name
        try:
            joblib.dump(model, temp, compress=3)
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(stage, path)
        finally:
            if os.path.exists(stage):
                os.unlink(stage)


def train_live(engine, source_type, cluster, node, metric, method, mode, history_hours, end):
    candidate, _ = model_paths(engine, source_type, cluster, node, metric, method, mode)
    if not 3 <= history_hours <= 168 or not 0 < end <= int(time.time()):
        raise ValueError('训练需要 3 至 168 小时的历史范围')
    if source_type == 'synthetic':
        raise ValueError('人工构造来源缺少实际 XID 标签，无法训练此检测器')
    end = end // STEP * STEP
    start = end - history_hours * 3600
    capture, _ = source_capture(engine.source, source_type, cluster, node, start, end)
    split = int(len(capture.xid) * .7)
    rows = (
        example_rows(capture, metric, mode, 0, split, stride=6),
        example_rows(capture, metric, mode, split + WINDOW - 1, len(capture.xid), stride=6),
    )
    with TRAINING_LOCK:
        model = fit_detector(method, mode, [rows[0]] if rows[0] else [], [rows[1]] if rows[1] else [])
        model.update(trained_through=end, version=uuid.uuid4().hex, feature_metrics=feature_metrics(metric))
        save_model(candidate, model)
    return {'status': 'candidate', 'trained_through': end, 'training_windows': model['training_windows'],
            'calibration_windows': model['calibration_windows']}


def activate_live(engine, source_type, cluster, node, metric, method, mode):
    candidate, active = model_paths(engine, source_type, cluster, node, metric, method, mode)
    with TRAINING_LOCK:
        if not candidate.is_file():
            raise ValueError('需要先训练并验证候选模型')
        model = joblib.load(candidate)
        if not model.get('reviewed'):
            raise ValueError('请先查看候选模型在训练之后的独立数据上的回放结果')
        os.replace(candidate, active)
    return {'status': 'active'}


def live_detection(engine, source_type, cluster, node, metric, method, mode, start, end, at,
                   review=False, scenario='normal', compare=False, reference_mode=None):
    candidate, active = model_paths(engine, source_type, cluster, node, metric, method, mode)
    if reference_mode not in (None, 'reference'):
        raise ValueError('仅支持 XID=0 正常参考')
    if not 0 < start < end <= int(time.time()) or end - start > 3 * 3600:
        raise ValueError('请选择最长 3 小时的历史时段')
    if scenario not in ('normal', 'drift', 'relation', 'gap'):
        raise ValueError('未知人工构造场景')
    with TRAINING_LOCK:
        path = candidate if review else active
        model = joblib.load(path) if path.is_file() else None
    if review and not model:
        raise ValueError('当前来源没有可验证的候选模型')
    if model and start < model['trained_through'] + WINDOW * STEP:
        if review:
            raise ValueError('验证时段需从校准结束至少 5 分钟之后开始')
        start = model['trained_through'] + WINDOW * STEP
        if start >= end:
            raise ValueError('模型等待校准结束后的 5 分钟新观测')
    grid_start = start // STEP * STEP - (WINDOW - 1) * STEP
    grid_end = end // STEP * STEP
    capture, cards = source_capture(engine.source, source_type, cluster, node, grid_start, grid_end, scenario)
    result = assess(capture, metric, model, start, end, at)
    if compare and metric == 'all' and at is not None and start <= at <= grid_end:
        def load(other_method, other_mode):
            if (other_method, other_mode) == (method, mode):
                return model
            _, path = model_paths(engine, source_type, cluster, node, metric, other_method, other_mode)
            with TRAINING_LOCK:
                return joblib.load(path) if path.is_file() else None

        result['comparison'] = joint_point(capture, at, load)
    offset = (start - grid_start + STEP - 1) // STEP
    if review and any(row['state'] in ('scored', 'alarm') for row in result['points']):
        with TRAINING_LOCK:
            stored = joblib.load(candidate) if candidate.is_file() else None
            if stored and stored['trained_through'] == model['trained_through'] and stored.get('version') == model.get('version'):
                stored['reviewed'] = True
                save_model(candidate, stored)
    last_at = grid_start + offset * STEP
    result.update(start=last_at, end=grid_end, candidate=candidate.is_file(),
                  model_status='candidate' if review else 'active' if model else 'untrained',
                  xid=[int(v) if np.isfinite(v) else None for v in capture.xid[offset:]],
                  series={key: {card: [float(v) if np.isfinite(v) else None for v in matrix[offset:, index]]
                                for card, matrix in cards.items()}
                          for index, key in enumerate(public_catalog()['metrics'])})
    return result
