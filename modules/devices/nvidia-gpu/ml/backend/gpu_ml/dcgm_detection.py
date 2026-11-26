"""Node-level, causal DCGM detection and the bundled public benchmark."""
from dataclasses import dataclass
from functools import lru_cache
import base64
import json
import threading
import warnings

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.tree import DecisionTreeClassifier

from .settings import BASE

STEP = 10
WINDOW = 30
PUBLIC = BASE / 'frontend/public-gwdg'
XID = 'DCGM_FI_DEV_XID_ERRORS'
NO_DATA = '当前无有效监测数据'
SINGLE = ('logistic_l2', 'hist_gradient_boosting', 'shallow_tree', 'pca_logistic',
          'pca_t2', 'isolation_forest', 'robust_range')
MULTI = ('shallow_tree', 'robust_range', 'pca_t2')
CORE_METRICS = ('DCGM_FI_DEV_GPU_TEMP', 'DCGM_FI_DEV_POWER_USAGE', 'DCGM_FI_DEV_GPU_UTIL',
                'DCGM_FI_DEV_MEM_COPY_UTIL', 'DCGM_FI_DEV_SM_CLOCK')
REFERENCE = SINGLE[4:]
MODES = ('reference', 'supervised')
TRAINING_LOCK = threading.Lock()


def method_catalog():
    """Catalog entries represent methods and input recipes before any version is trained."""
    return {'single': SINGLE, 'multi': MULTI,
            'training': {method: 'reference' if method in REFERENCE else 'supervised' for method in SINGLE}}


@lru_cache(maxsize=1)
def public_catalog():
    return json.loads((PUBLIC / 'index.json').read_text())


def validate_selection(metric, method, mode):
    if metric not in [*public_catalog()['metrics'], 'all', 'core']:
        raise ValueError('未知 DCGM 指标')
    if method not in (MULTI if metric in ('all', 'core') else SINGLE) or mode not in MODES:
        raise ValueError('检测方法或训练方式无效')
    if (method in REFERENCE) == (mode == 'supervised'):
        raise ValueError('检测方法与训练方式不匹配')


def unpack(series):
    if 'b' in series:
        return np.frombuffer(base64.b64decode(series['b']), dtype='<f8')
    runs = series['r']
    return np.repeat(np.asarray(runs[1::2], dtype=float), runs[::2])


@dataclass
class Capture:
    start: int
    # (time, metric, channel), with per-node mean, max, and fraction missing.
    channels: np.ndarray
    xid: np.ndarray

    @property
    def available(self):
        return np.isfinite(self.channels[:, :, 0]).any(axis=1)


@lru_cache(maxsize=6)
def public_capture(collection):
    payload = json.loads((PUBLIC / f'{collection}.json').read_text())
    channels = np.stack([
        np.column_stack([unpack(payload['native'][key][field]) for field in ('mean', 'max', 'missing')])
        for key in public_catalog()['metrics']
    ], axis=1)
    return Capture(payload['start'], channels, unpack(payload['xid']))


def slope(values):
    valid = np.isfinite(values)
    count = valid.sum(axis=-1)
    times = np.arange(values.shape[-1]) / 6
    mean = (valid * times).sum(axis=-1) / np.maximum(count, 1)
    centered = np.where(valid, times - mean[..., None], 0)
    reference = np.take_along_axis(values, valid.argmax(axis=-1, keepdims=True), axis=-1)
    ss = (centered ** 2).sum(axis=-1)
    cross = (centered * np.where(valid, values - reference, 0)).sum(axis=-1)
    return np.divide(cross, ss, out=np.full(cross.shape, np.nan), where=ss > 0)


def features(capture, metric, ends):
    if len(ends) > 2048:
        return np.concatenate([features(capture, metric, ends[i:i+2048]) for i in range(0, len(ends), 2048)])
    cols = public_catalog()['metrics']
    chosen = feature_metrics(metric)
    inputs = capture.channels if metric == 'all' else capture.channels[:, [cols.index(k) for k in chosen], :]
    windows = np.lib.stride_tricks.sliding_window_view(inputs, WINDOW, axis=0)[ends - WINDOW + 1]
    # Feature order mirrors the research export: 10 mean, 10 max, 8 missingness per metric.
    numeric, missing = windows[:, :, :2, :], windows[:, :, 2, :]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)

        def basic(values):
            recent = np.nanmean(values[..., -6:], axis=-1)
            return [values[..., -1], np.nanmean(values[..., -3:], axis=-1), recent,
                    np.nanmean(values, axis=-1), np.nanmax(values, axis=-1),
                    recent - np.nanmean(values[..., :-6], axis=-1)]

        num_stats = np.stack([*basic(numeric), np.nanstd(numeric, axis=-1),
                              np.nanmin(numeric, axis=-1), slope(numeric), slope(numeric[..., -6:])], axis=-1)
        absent = missing >= 1 - 1e-7
        missing_stats = np.stack([*basic(missing), absent.mean(axis=-1),
                                  STEP * np.cumprod(absent[..., ::-1], axis=-1).sum(axis=-1)], axis=-1)
    return np.concatenate((num_stats.reshape(len(ends), len(chosen), 20),
                           missing_stats), axis=-1).reshape(len(ends), 28 * len(chosen)).astype(np.float32)


def feature_metrics(metric):
    if metric == 'core':
        return CORE_METRICS
    return public_catalog()['metrics'] if metric == 'all' else (metric,)


def example_rows(capture, metric, mode, start, end, stride=30):
    ends = np.arange(max(WINDOW - 1, start), end)
    available = input_available(capture, metric)[ends]
    labels = capture.xid[ends]
    if mode == 'reference':
        available &= labels == 0
    elif mode == 'supervised':
        available &= np.isfinite(labels)
        previous_labels = capture.xid[:start]
        previous_known = previous_labels[np.isfinite(previous_labels)]
        if len(previous_known) and previous_known[-1] == 1:
            # Keep an ongoing event on the training side of the temporal split.
            available &= (labels != 1) | np.maximum.accumulate(labels == 0)
    # Preserve short labeled incidents even when regularly sampled rows miss them.
    eligible = ends % stride == 0
    if mode == 'supervised':
        previous = capture.xid[np.maximum(ends - 1, 0)]
        eligible |= (labels == 1) & (previous != 1)
    chosen = ends[available & eligible]
    if not chosen.size:
        return None
    events = 0
    if mode == 'supervised':
        # Count positive episodes with usable inputs. Unknown gaps cannot certify a new event.
        positive = labels == 1
        group = np.cumsum(labels == 0)
        events = len(np.unique(group[positive & available]))
    y = capture.xid[chosen] if mode == 'supervised' else np.zeros(len(chosen))
    return features(capture, metric, chosen), y, events


def input_available(capture, metric):
    if metric == 'core':
        columns = [public_catalog()['metrics'].index(key) for key in CORE_METRICS]
        return np.isfinite(capture.channels[:, columns, 0]).any(axis=1)
    return capture.available


def transform(model, x):
    values = (x[:, model['keep']] - model['center']) / model['scale']
    return np.where(np.isfinite(values), values, 0)


def scores(model, z):
    method = model['method']
    estimator = model.get('estimator')
    if method == 'pca_t2':
        pca = model['pca']
        return np.sum(pca.transform(z) ** 2 / pca.explained_variance_, axis=1)
    if method == 'robust_range':
        return np.max(np.abs(z - model['median']) / model['robust_scale'], axis=1)
    if method == 'isolation_forest':
        return -estimator.score_samples(z)
    if method == 'pca_logistic':
        z = model['pca'].transform(z)
    return estimator.predict_proba(z)[:, 1]


def fit_detector(method, mode, training, calibration):
    if not training or not calibration:
        raise ValueError('待采集：训练段和校准段都需要有效历史数据')
    x, y = (np.concatenate([row[i] for row in training]) for i in (0, 1))
    cx, cy = (np.concatenate([row[i] for row in calibration]) for i in (0, 1))
    if mode == 'supervised':
        for groups, labels in ((training, y), (calibration, cy)):
            if sum(row[2] for row in groups) < 2 or min(np.count_nonzero(labels == i) for i in (0, 1)) < 5:
                raise ValueError('待标注：训练段和校准段各需至少 2 个独立异常事件、5 个正窗口和 5 个正常窗口')
    elif len(x) < 120 or len(cx) < 120:
        raise ValueError('待采集：训练段和校准段各需至少 120 个参考窗口，并应覆盖典型负载')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        center, scale = np.nanmean(x.astype(float), axis=0), np.nanstd(x.astype(float), axis=0)
    keep = np.flatnonzero(np.isfinite(scale) & (scale > np.maximum(1e-12, np.abs(center) * 1e-12)))
    if not len(keep):
        raise ValueError('待采集：当前训练数据没有可学习的变化')
    model = {'method': method, 'mode': mode, 'keep': keep, 'center': center[keep], 'scale': scale[keep]}
    z = transform(model, x)
    weights = np.where(y == 1, 2., 1.)
    if method == 'robust_range':
        median = np.median(z, axis=0)
        model.update(median=median, robust_scale=np.maximum.reduce([
            1.4826 * np.median(np.abs(z - median), axis=0), .1 * z.std(axis=0), np.full(z.shape[1], 1e-6)]))
    elif method == 'isolation_forest':
        model['estimator'] = IsolationForest(n_estimators=100, max_samples=min(256, len(z)), random_state=20261125).fit(z)
    elif method == 'pca_t2':
        pca = PCA(n_components=.95, svd_solver='full').fit(z)
        good = pca.explained_variance_ > max(1e-12, pca.explained_variance_[0] * 1e-12)
        if not np.all(good):
            pca = PCA(n_components=int(good.sum()), svd_solver='full').fit(z)
        model['pca'] = pca
    else:
        if method == 'shallow_tree':
            estimator = DecisionTreeClassifier(max_depth=3, min_samples_leaf=max(5, int(.005 * len(z))),
                                               random_state=20261125)
        elif method == 'hist_gradient_boosting':
            estimator = HistGradientBoostingClassifier(max_iter=60, max_leaf_nodes=7, max_bins=64, early_stopping=False,
                                                        learning_rate=.05, l2_regularization=1., random_state=20261125)
        else:
            if method == 'pca_logistic':
                model['pca'] = PCA(n_components=min(5, *z.shape), svd_solver='full').fit(z)
                z = model['pca'].transform(z)
            estimator = LogisticRegression(C=.1, max_iter=2000, solver='lbfgs')
        model['estimator'] = estimator.fit(z, y.astype(int), sample_weight=weights)
    calibration_scores = scores(model, transform(model, cx))
    if mode == 'supervised':
        precision, recall, values = precision_recall_curve(cy, calibration_scores)
        denom = precision[:-1] + recall[:-1]
        f1 = np.divide(2 * precision[:-1] * recall[:-1], denom, out=np.zeros_like(denom), where=denom > 0)
        threshold = np.nextafter(values[np.flatnonzero(f1 == f1.max())[-1]], -np.inf)
    else:
        threshold = np.quantile(calibration_scores, .99, method='higher')
    model.update(threshold=float(threshold), training_windows=len(x), calibration_windows=len(cx))
    return model


def tree_path(model, z):
    tree = model['estimator'].tree_
    node = 0
    while tree.feature[node] >= 0:
        feature = tree.feature[node]
        above = np.float32(z[feature]) > tree.threshold[node]
        child = tree.children_right[node] if above else tree.children_left[node]
        yield node, child, feature, above
        node = child


def feature_effects(model, z):
    if model['method'] == 'robust_range':
        return np.abs(z - model['median']) / model['robust_scale']
    if model['method'] == 'pca_t2':
        pca = model['pca']
        return (z - pca.mean_) * ((pca.transform(z[None, :])[0] / pca.explained_variance_) @ pca.components_)
    tree = model['estimator'].tree_
    probability = tree.value[:, 0, 1] / tree.value[:, 0, :].sum(axis=1)
    terms = np.zeros_like(z)
    for node, child, feature, _ in tree_path(model, z):
        terms[feature] += probability[child] - probability[node]
    return terms


def explanations(model, z):
    """Return the strongest positive metric contributions for one alarm."""
    terms = feature_effects(model, z)
    metric_terms = np.zeros((len(public_catalog()['metrics']), 28))
    metric_terms.flat[model['keep']] = terms
    strength = metric_terms.max(axis=1) if model['method'] == 'robust_range' else metric_terms.sum(axis=1)
    order = np.argsort(-strength, kind='stable')
    return [{'metric': public_catalog()['metrics'][idx], 'contribution': float(strength[idx])}
            for idx in order[:3] if strength[idx] > 1e-12]


_NUMERIC_FEATURES = ('当前值', '近 30 秒均值', '近 1 分钟均值', '近 5 分钟均值', '近 5 分钟最大值',
                     '近 1 分钟均值与此前 4 分钟均值之差', '近 5 分钟标准差', '近 5 分钟最小值',
                     '近 5 分钟趋势', '近 1 分钟趋势')
_MISSING_FEATURES = (*_NUMERIC_FEATURES[:6], '近 5 分钟全缺测的时间占比', '连续全缺测时长')


def alarm_evidence(model, raw, z):
    """Identify threshold violations, the fitted tree path, or positive T² drivers."""
    method = model['method']
    if method == 'shallow_tree':
        ranked = [(feature, '高于分裂阈值' if above else '低于或等于分裂阈值')
                  for _, _, feature, above in tree_path(model, z)]
    else:
        effects = feature_effects(model, z)
        cutoff = model['threshold'] if method == 'robust_range' else 1e-12
        ranked = [(feature, None) for feature in np.argsort(-effects, kind='stable')[:3]
                  if effects[feature] > cutoff]

    metrics = model.get('feature_metrics', public_catalog()['metrics'])
    evidence = []
    for feature, condition in ranked:
        column = int(model['keep'][feature])
        metric, offset = divmod(column, 28)
        if offset < 20:
            channel = 'GPU 间均值' if offset < 10 else 'GPU 间最大值'
            statistic = _NUMERIC_FEATURES[offset % 10]
        else:
            channel = 'GPU 缺测比例'
            statistic = _MISSING_FEATURES[offset - 20]
        item = {'metric': metrics[metric], 'feature': channel + ' · ' + statistic}
        if condition:
            item.update(condition=condition, imputed=not np.isfinite(raw[column]))
        evidence.append(item)
    return evidence


def assess(capture, metric, model, start, end, at=None):
    first = max(0, (start - capture.start + STEP - 1) // STEP)
    last = min(len(capture.xid), (end - capture.start) // STEP + 1)
    indices = np.arange(first, last)
    available = input_available(capture, metric)[indices]
    selected = indices[available & (indices >= WINDOW - 1)]
    status = {int(i): {'t': int(capture.start + i * STEP),
                       'state': 'no_data' if not valid else 'warmup' if i < WINDOW - 1 else 'untrained'}
              for i, valid in zip(indices, available)}
    for index in indices[~available]:
        status[int(index)]['warning'] = NO_DATA
    drivers = []
    if model is not None and selected.size:
        z = transform(model, features(capture, metric, selected))
        raw = scores(model, z)
        for index, value in zip(selected, raw):
            status[int(index)].update(state='alarm' if value > model['threshold'] else 'scored', score=float(value))
        if metric == 'all' and at is not None:
            index = (at - capture.start) // STEP
            if status.get(index, {}).get('state') == 'alarm':
                drivers = explanations(model, z[np.searchsorted(selected, index)])
    return {'points': list(status.values()), 'drivers': drivers,
            'threshold': model['threshold'] if model else None,
            'training_windows': model['training_windows'] if model else None,
            'calibration_windows': model['calibration_windows'] if model else None}


def joint_point(capture, at, load_model, metric='all'):
    """Score each joint method once at the same point for all metric cards."""
    point = assess(capture, metric, None, at, at)['points']
    if not point:
        return None
    state = point[0]['state']
    index = (at - capture.start) // STEP
    inputs = features(capture, metric, np.array([index])) if state == 'untrained' else None
    comparisons = []
    for method in MULTI:
        mode = 'reference' if method in REFERENCE else 'supervised'
        row = {'method': method, 'mode': mode, 'state': state}
        comparisons.append(row)
        if inputs is None:
            continue
        try:
            model = load_model(method, mode)
        except ValueError as exc:
            row.update(state='unavailable', detail=str(exc))
            continue
        if model is None:
            continue
        if 'trained_through' in model and at < model['trained_through'] + WINDOW * STEP:
            row.update(state='before_model')
            continue
        transformed = transform(model, inputs)
        score = float(scores(model, transformed)[0])
        alarm = score > model['threshold']
        row.update(state='alarm' if alarm else 'scored', score=score, threshold=model['threshold'],
                   drivers=explanations(model, transformed[0]) if alarm else [],
                   evidence=alarm_evidence(model, inputs[0], transformed[0]) if alarm else [])
    return {'t': at, 'methods': comparisons}


def fit_public_model(fold, metric, method, mode):
    catalog = public_catalog()['collections']
    validation, training = [], []
    for row in catalog:
        group = row['fold']
        if group == fold:
            continue
        capture = public_capture(row['id'])
        sample = example_rows(capture, metric, mode, 0, len(capture.xid))
        if sample:
            calibration_fold = 4 if fold is None else (fold + 1) % 5
            (validation if group == calibration_fold else training).append(sample)
    model = fit_detector(method, mode, training, validation)
    model['feature_metrics'] = feature_metrics(metric)
    return model


public_model = lru_cache(maxsize=16)(fit_public_model)


def public_detection(collection, metric, method, mode, start, end, at, compare=False, reference_mode=None):
    validate_selection(metric, method, mode)
    row = next((row for row in public_catalog()['collections'] if row['id'] == collection), None)
    if not row or not row['start'] <= start < end <= row['end'] or end - start > 3 * 3600:
        raise ValueError('请选择采集区间内最长 3 小时的时段')
    if reference_mode not in (None, 'reference'):
        raise ValueError('仅支持 XID=0 正常参考')

    def load(method, mode):
        with TRAINING_LOCK:
            return public_model(row['fold'], metric, method, mode)

    try:
        model = load(method, mode)
    except ValueError:
        if not compare or metric != 'all':
            raise
        model = None
    capture = public_capture(collection)
    result = assess(capture, metric, model, start, end, at)
    if compare and metric == 'all' and at is not None and start <= at <= end:
        result['comparison'] = joint_point(capture, at, load)
    return result
