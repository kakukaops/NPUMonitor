"""Source-bound training and replay for the DCGM method board."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
import time
import uuid

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .dcgm_detection import (
    MULTI, REFERENCE, SINGLE, STEP, TRAINING_LOCK, WINDOW, alarm_evidence, assess, feature_metrics,
    features, fit_public_model, joint_point, public_capture, public_catalog, public_model, transform, unpack,
)
from .dcgm_review import review_target
from .dcgm_scenarios import CATALOG, template_name
from .dcgm_sources import fit_capture_detector, save_model, source_capture
from .pipeline import build_pipeline
from .settings import BASE, DATA, METRICS, TEMPLATES

REFERENCE_HOURS = 12
CARD_TRENDS = ('temporal_mad', 'rolling_median', 'level_mad')
CARD_JOINT = ('joint_pca', 'joint_window_pca', 'joint_iforest')
CARD_FIELDS = ('gpu_temp', 'power', 'util', 'sm_clock', 'mem_util')
METRIC_BY_KEY = {key: spec['name'] for key, spec in METRICS.items()}
SCENES = CATALOG['scenarios']
KIND = 'dcgm_workbench_method'


@dataclass(frozen=True)
class Scope:
    source: str
    node: str
    cluster: str
    collection: str
    gpu: str
    fold: int | None = None
    start: int = 0
    end: int = 0
    fallback: tuple = ()

    def key(self, target, method):
        node_binding = [self.source, self.cluster, self.node, target, method]
        if method not in SINGLE:
            node_binding.extend((self.collection, self.gpu))
        return sha256(json.dumps(node_binding).encode()).hexdigest()

    def window(self, start, end):
        if not self.start <= start < end <= self.end or end - start > 10800 or start % STEP or end % STEP:
            raise ValueError('请选择有效的 10 秒对齐回放时段，最长 3 小时')


def catalog():
    return {'single': CARD_TRENDS, 'joint': CARD_JOINT,
            'card_fields': [METRIC_BY_KEY[key] for key in CARD_FIELDS],
            'scenes': {scene: {'name': spec['name'], 'method': spec['algorithm']}
                       for scene, spec in SCENES.items()}}


def scope_for(engine, source, collection='', cluster='', node='', gpu=''):
    if source == 'public':
        row = next((r for r in public_catalog()['collections'] if r['id'] == collection), None)
        if not row:
            raise ValueError('请选择公开采集区间')
        return Scope(source, row['node'], '', collection, gpu, row['fold'], row['start'], row['end'])
    if source != 'simulated':
        raise ValueError('此方法看板支持公开数据与模拟采集')
    fallback = review_target(engine, source, cluster, node, '')
    if gpu and not any(e['source_type'] == source and e['cluster'] == cluster and
                       (e.get('node') or '') == node and e['uuid'] == gpu for e in engine.store.list('entity')):
        raise ValueError('请选择当前模拟节点的 GPU')
    now = int(time.time())
    return Scope(source, node, cluster, '', gpu, start=now // 30 * 30 - 7 * 86400,
                 end=now // STEP * STEP, fallback=fallback)


def methods_for(target):
    if target in public_catalog()['metrics']:
        return (*SINGLE, *CARD_TRENDS)
    if target in ('all', 'core'):
        return MULTI
    if target == 'gpu_joint':
        return CARD_JOINT
    if target in SCENES:
        return (SCENES[target]['algorithm'],)
    raise ValueError('未知指标或指标组')


def public_cards(scope, metrics, start, end, gpu=None):
    raw = json.loads((BASE / 'frontend/public-gwdg' / (scope.collection + '.json')).read_text())
    first, last = (start - scope.start) // STEP, (end - scope.start) // STEP + 1
    cards = [card for card in raw['gpus'] if gpu is None or card['id'] == gpu]
    if gpu and not cards:
        raise ValueError('请选择当前采集区间的 GPU')
    result = {}
    for metric in metrics:
        series = raw['native'][metric]['gpus']
        result[metric] = {card['id']: unpack(series[card['id']])[first:last] for card in cards
                          if card['id'] in series and series[card['id']]}
    return result, {card['id']: card['label'] for card in cards}


@lru_cache(maxsize=48)
def collection_cards(collection):
    raw = json.loads((BASE / 'frontend/public-gwdg' / (collection + '.json')).read_text())
    return {card['id']: card['label'] for card in raw['gpus']}


def card_spec(target, method):
    if target in SCENES:
        return TEMPLATES[template_name(target, 'laboratory')]
    keys = [target] if method in CARD_TRENDS else [METRIC_BY_KEY[key] for key in CARD_FIELDS]
    return {'kind': 'univariate' if method in CARD_TRENDS else 'multivariate',
            'required': keys, 'targets': keys,
            'algorithms': list(CARD_TRENDS if method in CARD_TRENDS else CARD_JOINT)}


def card_inputs(spec):
    return {key: METRIC_BY_KEY.get(key, key) for key in spec['required']}


def card_rows(series, inputs, gpu, start, end, healthy=None):
    if not gpu:
        raise ValueError('请选择用于卡级训练和回放的 GPU')
    if any(gpu not in series[field] for field in inputs.values()):
        return []
    values = np.column_stack([series[field][gpu] for field in inputs.values()])
    indices = np.flatnonzero(np.isfinite(values).all(axis=1))
    if healthy is not None:
        indices = indices[healthy[indices]]
    return [{'t': start + int(i) * STEP, 'values': dict(zip(inputs, map(float, values[i])))}
            for i in indices if start + i * STEP <= end]


def source_window(engine, scope, metrics, start, end, gpu=None):
    if scope.source == 'public':
        data, labels = public_cards(scope, metrics, start, end, gpu)
        return data, labels, public_capture(scope.collection)
    capture, cards = source_capture(engine.source, scope.source, scope.cluster, scope.node, start, end,
                                    fallback_cards=scope.fallback)
    indices = {field: public_catalog()['metrics'].index(field) for field in metrics}
    data = {field: {card: values[:, index] for card, values in cards.items() if gpu is None or card == gpu}
            for field, index in indices.items()}
    return data, {card: card for card in cards}, capture


def default_configuration(scope, method):
    public_reference = scope.source == 'public' and method in SINGLE
    return {'enabled': public_reference, 'active': {'version': 'gwdg'} if public_reference else None,
            'candidate': None}


def configuration(engine, scope, target, method):
    return engine.store.get(KIND, scope.key(target, method)) or default_configuration(scope, method)


def board_state(engine, scope, target):
    return {'methods': {method: configuration(engine, scope, target, method) for method in methods_for(target)},
            'cards': collection_cards(scope.collection) if scope.source == 'public' else None}


def artifact(key, version):
    return DATA / 'dcgm-workbench' / (key + '-' + version + '.joblib')


def method_mode(method):
    return 'reference' if method in REFERENCE else 'supervised'


def train(engine, scope, target, method, end):
    with threadpool_limits(limits=1):
        if scope.source == 'public' and method in SINGLE:
            return fit_public_model(scope.fold, target, method, method_mode(method)), None
        if not scope.start + 1 <= end <= scope.end or end % STEP:
            raise ValueError('请选择有效的历史训练结束时间')
        start = max(scope.start, end - REFERENCE_HOURS * 3600)
        if method in SINGLE:
            capture, _ = source_capture(engine.source, scope.source, scope.cluster, scope.node, start, end,
                                        fallback_cards=scope.fallback)
            return fit_capture_detector(capture, target, method, method_mode(method)), end
        if not scope.gpu:
            raise ValueError('先选择一张 GPU')
        spec = card_spec(target, method)
        inputs = card_inputs(spec)
        series, _, capture = source_window(engine, scope, inputs.values(), start, end, scope.gpu)
        first = (start - capture.start) // STEP
        label = capture.xid[first:first + (end - start) // STEP + 1]
        is_eligible = label == 0 if scope.source == 'public' else label != 1
        rows = card_rows(series, inputs, scope.gpu, start, end, is_eligible)
        if len(rows) < 240:
            raise ValueError('至少需要 240 个有效参考点。请检查字段与 XID 覆盖，或选择采集区间更晚的时刻')
        model = build_pipeline(target, method, spec=spec)
        try:
            model.fit(rows)
        except ValueError as exc:
            raise ValueError(f'{exc}。参考时段有 {len(rows)} 个有效端点，训练、校准和验证需要各自的有效覆盖。') from exc
        return model, end


def update(engine, scope, target, method, operation, actor, end=0):
    if method not in methods_for(target):
        raise ValueError('模型与所选指标不匹配')
    key = scope.key(target, method)
    with TRAINING_LOCK:
        config = configuration(engine, scope, target, method)
        if operation == 'train':
            model, through = train(engine, scope, target, method, end)
            version = uuid.uuid4().hex
            if method in SINGLE:
                summary = {'training': model['training_windows'], 'calibration': model['calibration_windows']}
            else:
                summary = {'training': model.report['train_samples'], 'calibration': model.report['calibration_samples']}
            save_model(artifact(key, version), model)
            retired = config.get('candidate')
            config['candidate'] = dict(version=version, through=through, reviewed=False, **summary)
        else:
            retired = None
            if operation == 'enable':
                candidate = config.get('candidate')
                if candidate and candidate['reviewed']:
                    retired, config['active'] = config.get('active'), candidate
                    config['candidate'] = None
                if not config.get('active'):
                    raise ValueError('先训练并验证一个候选模型')
                config['enabled'] = True
            elif operation == 'pause':
                config['enabled'] = False
            elif operation == 'reference' and method in SINGLE:
                retired = config.get('active')
                config.update(active={'version': 'gwdg'}, enabled=True)
            else:
                raise ValueError('未知的模型操作')
        saved = engine.store.put(KIND, key, config)
        if retired and retired['version'] != 'gwdg':
            artifact(key, retired['version']).unlink(missing_ok=True)
        engine.store.audit(actor, 'dcgm_workbench_' + operation, key,
                           {'source': scope.source, 'node': scope.node, 'target': target, 'method': method})
        return saved


def selected_model(engine, scope, target, method, review):
    with TRAINING_LOCK:
        config = configuration(engine, scope, target, method)
        version = config.get('candidate') if review else config.get('active') if config['enabled'] else None
        if not version:
            if review:
                raise ValueError('此方法尚无训练候选')
            return None, None
        if version['version'] == 'gwdg':
            with threadpool_limits(limits=1):
                model = public_model(scope.fold, target, method, method_mode(method))
        else:
            model = joblib.load(artifact(scope.key(target, method), version['version']))
        return model, version


def pipeline_result(model, spec, observations, scope, read_start, start, end, eligible):
    inputs = card_inputs(spec)
    rows = card_rows(observations, inputs, scope.gpu, read_start, end)
    observed = {row['t'] for row in rows}
    scored = {point['t']: point for point in model.predict(rows)} if model and rows else {}
    result = []
    for t in range(start, end + 1, STEP):
        p = scored.get(t)
        if p and t >= eligible:
            result.append({'t': t, 'state': 'alarm' if p['anomaly'] else 'scored',
                           'score': p['score'], 'expected': {inputs[k]: v for k, v in p['expected'].items()},
                           'bounds': {inputs[k]: v for k, v in p['bounds'].items()},
                           'contributions': {inputs[k]: v for k, v in p['contributions'].items()}})
        else:
            state = ('no_data' if t not in observed else 'before_model' if t < eligible else
                     'warmup' if model else 'untrained')
            result.append({'t': t, 'state': state})
    return {'points': result, 'threshold': model.policy.threshold * model.policy.factor if model else None,
            'reference_kind': model.capabilities['reference_kind'] if model else None}


def number(value):
    return float(value) if np.isfinite(value) else None


def replay(engine, scope, target, method, start, end, at=None, review=False):
    if method not in methods_for(target):
        raise ValueError('模型与所选指标不匹配')
    scope.window(start, end)
    if at is not None and not start <= at <= end:
        raise ValueError('选中时刻须位于回放范围内')
    issue = None
    try:
        model, version = selected_model(engine, scope, target, method, review)
    except ValueError as exc:
        if review:
            raise
        model, version, issue = None, configuration(engine, scope, target, method).get('active'), str(exc)
    node_level = method in SINGLE
    eligible = version['through'] + WINDOW * STEP if version and version.get('through') else scope.start
    read_start = max(scope.start, start - 600, eligible - (WINDOW - 1) * STEP) if eligible <= start else max(scope.start, start - 600)
    spec = None if node_level else card_spec(target, method)
    fields = feature_metrics(target) if node_level else tuple(card_inputs(spec).values())
    observations, labels, capture = source_window(engine, scope, fields, read_start, end,
                                                  None if node_level else scope.gpu)
    with threadpool_limits(limits=1):
        if node_level:
            result = assess(capture, target, model if eligible <= end else None, max(start, min(eligible, end)), end)
            earlier = range(start, min(eligible, end + 1), STEP)
            if earlier:
                result['points'] = [{'t': t, 'state': 'before_model'} for t in earlier] + [
                    row for row in result['points'] if row['t'] >= eligible]
            index = (at - capture.start) // STEP if at is not None else -1
            decision = next((row for row in result['points'] if row['t'] == at), None)
            if model and decision and decision['state'] == 'alarm':
                raw = features(capture, target, np.array([index]))
                result['evidence'] = alarm_evidence(model, raw[0], transform(model, raw)[0])
                result['evidenceAt'] = at
            if scope.source == 'simulated' and target in public_catalog()['metrics'] and not any(
                np.isfinite(values).any() for values in observations[target].values()
            ):
                result.update(points=[{'t': t, 'state': 'no_data'} for t in range(start, end + 1, STEP)])
            if target in ('all', 'core') and at is not None:
                def load(other, _):
                    if other == method and issue:
                        raise ValueError(issue)
                    other_model, other_version = (model, version) if other == method else selected_model(
                        engine, scope, target, other, False)
                    if other_model and other_version.get('through'):
                        return {**other_model, 'trained_through': other_version['through']}
                    return other_model

                result['comparison'] = joint_point(capture, at, load, target)
        else:
            result = pipeline_result(model, spec, observations, scope, read_start, start, end, eligible)
    if issue:
        result['model_issue'] = issue
        for row in result['points']:
            if row['state'] == 'untrained':
                row['state'] = 'unavailable'
    first = (start - capture.start) // STEP
    offset = (start - read_start) // STEP
    result.update(start=start, end=end, node_level=node_level, version=version,
                  xid=[number(value) for value in capture.xid[first:first + (end - start) // STEP + 1]],
                  labels=labels, fields=fields, series={
                      field: {gpu: [number(value) for value in values[offset:]] for gpu, values in cards.items()}
                      for field, cards in observations.items()})
    if review:
        scored = sum(row['state'] in ('scored', 'alarm') for row in result['points'])
        if not scored:
            raise ValueError('该回放时段没有独立有效评分，请选择更晚或覆盖更好的时段')
        with TRAINING_LOCK:
            config = configuration(engine, scope, target, method)
            candidate = config.get('candidate')
            if not candidate or candidate['version'] != version['version']:
                raise ValueError('候选版本已变化，请刷新后重新验证')
            candidate.update(reviewed=True, review_points=scored)
            engine.store.put(KIND, scope.key(target, method), config)
    return result
