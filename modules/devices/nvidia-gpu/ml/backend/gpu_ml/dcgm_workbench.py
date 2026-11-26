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
VERSION_KIND = 'dcgm_workbench_version'
REFERENCE_RELEASE = 'gwdg-v2-node-detector-v1'


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

    def binding(self):
        return {key: getattr(self, key) for key in ('source', 'node', 'cluster', 'collection', 'gpu', 'fold')}


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


def reference_id(scope, target, method):
    digest = sha256(json.dumps([REFERENCE_RELEASE, scope.fold, target, method]).encode()).hexdigest()
    return 'ref-' + digest[:24]


def version_path(record):
    return artifact(record.get('binding_key', 'reference'), record['version'])


def register_local(engine, scope, target, method, version):
    record = dict(version, **scope.binding(), binding_key=scope.key(target, method), target=target,
                  method=method, origin='trained', created_at=version.get('created_at', time.time()))
    return engine.store.put(VERSION_KIND, version['version'], record)


def reference_model(engine, scope, target, method):
    identity = reference_id(scope, target, method)
    record = engine.store.get(VERSION_KIND, identity)
    path = artifact('reference', identity)
    if record and path.is_file():
        return joblib.load(path), record
    with threadpool_limits(limits=1):
        model = public_model(scope.fold, target, method, method_mode(method))
    save_model(path, model)
    record = engine.store.put(VERSION_KIND, identity, dict(
        **scope.binding(), version=identity, origin='gwdg', release=REFERENCE_RELEASE, target=target, method=method,
        reviewed=True, through=None, created_at=time.time(),
        training=model['training_windows'], calibration=model['calibration_windows']))
    return model, record


def local_versions(config):
    return [version for slot in ('active', 'candidate') if (version := config.get(slot))
            and version['version'] != 'gwdg']


def recover_library(engine, configs):
    """Recover metadata for surviving artifacts created before the model library."""
    pending = {row['id']: row for row in configs if not row.get('binding') and
               any(artifact(row['id'], version['version']).is_file() for version in local_versions(row))}
    if not pending:
        return
    metrics = public_catalog()['metrics']
    targets = [*metrics, 'all', 'core', 'gpu_joint', *SCENES]
    hints = {row['object_id']: json.loads(row.get('details') or '{}') for row in engine.store.audits()
             if row['object_id'] in pending and row['action'].startswith('dcgm_workbench_')}
    pairs = {(target, method) for target in targets for method in methods_for(target)}
    if len(hints) == len(pending):
        pairs &= {(hint.get('target'), hint.get('method')) for hint in hints.values()}

    def find(scope, node_only):
        for target, method in pairs:
            if (method in SINGLE) != node_only:
                continue
            key = scope.key(target, method)
            row = pending.pop(key, None)
            if not row:
                continue
            for version in local_versions(row):
                if artifact(key, version['version']).is_file():
                    register_local(engine, scope, target, method, version)
            engine.store.put(KIND, key, dict(row, binding=scope.binding(), target=target, method=method))

    for row in public_catalog()['collections']:
        if not pending:
            return
        args = ('public', row['node'], '', row['id'])
        find(Scope(*args, '', row['fold']), True)
        if pending and any(method not in SINGLE for _, method in pairs):
            for gpu in collection_cards(row['id']):
                find(Scope(*args, gpu, row['fold']), False)
    for entity in engine.store.list('entity'):
        if not pending:
            return
        if entity.get('source_type') != 'simulated':
            continue
        scope = Scope('simulated', entity.get('node') or '', entity['cluster'], '', entity['uuid'])
        find(scope, True)
        find(scope, False)


def library(engine):
    configs = engine.store.list(KIND)
    if any(not row.get('binding') and local_versions(row) for row in configs):
        with TRAINING_LOCK:
            recover_library(engine, engine.store.list(KIND))
    configs_by_key = {row['id']: row for row in configs}
    result = []
    for record in engine.store.list(VERSION_KIND):
        config = configs_by_key.get(record.get('binding_key'))
        if record['origin'] == 'gwdg':
            scope = Scope(**{key: record[key] for key in ('source', 'node', 'cluster', 'collection', 'gpu', 'fold')})
            config = configs_by_key.get(scope.key(record['target'], record['method']))
        active_id = (config.get('active') or {}).get('version') if config else None
        active_here = active_id == ('gwdg' if record['origin'] == 'gwdg' else record['version'])
        status = ('missing' if not version_path(record).is_file() else
                  ('enabled' if config['enabled'] else 'paused') if active_here else
                  'ready' if record['reviewed'] else 'trained')
        result.append(dict(record, status=status))
    return sorted(result, key=lambda row: (row['created_at'], row['id']), reverse=True)


def compatible_version(engine, scope, target, method, version_id):
    record = engine.store.get(VERSION_KIND, version_id)
    if (not record or record['target'] != target or record['method'] != method or
        (record['version'] != reference_id(scope, target, method) if record['origin'] == 'gwdg'
         else record['binding_key'] != scope.key(target, method)) or not version_path(record).is_file()):
        raise ValueError('此模型版本不可用于当前来源、节点或指标')
    return record


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


def update(engine, scope, target, method, operation, actor, end=0, version_id=None):
    if method not in methods_for(target):
        raise ValueError('模型与所选指标不匹配')
    key = scope.key(target, method)
    with TRAINING_LOCK:
        config = configuration(engine, scope, target, method)
        for version in local_versions(config):
            if not engine.store.get(VERSION_KIND, version['version']) and artifact(key, version['version']).is_file():
                register_local(engine, scope, target, method, version)
        if operation == 'prepare' and method in SINGLE:
            return reference_model(engine, scope, target, method)[1]
        if operation == 'train':
            model, through = train(engine, scope, target, method, end)
            version = uuid.uuid4().hex
            if method in SINGLE:
                summary = {'training': model['training_windows'], 'calibration': model['calibration_windows']}
            else:
                summary = {'training': model.report['train_samples'], 'calibration': model.report['calibration_samples']}
            save_model(artifact(key, version), model)
            config['candidate'] = dict(version=version, through=through, reviewed=False, created_at=time.time(), **summary)
            register_local(engine, scope, target, method, config['candidate'])
        else:
            if operation == 'enable':
                candidate = compatible_version(engine, scope, target, method, version_id) if version_id else config.get('candidate')
                if version_id and not candidate['reviewed']:
                    raise ValueError('请先验证所选模型版本')
                if candidate and candidate['reviewed']:
                    reference = candidate.get('origin') == 'gwdg'
                    config['active'] = {'version': 'gwdg'} if reference else candidate
                    if (config.get('candidate') or {}).get('version') == candidate['version']:
                        config['candidate'] = None
                if not config.get('active'):
                    raise ValueError('先训练并验证一个候选模型')
                config['enabled'] = True
            elif operation == 'pause':
                config['enabled'] = False
            elif operation == 'reference' and method in SINGLE:
                reference_model(engine, scope, target, method)
                config.update(active={'version': 'gwdg'}, enabled=True)
            else:
                raise ValueError('未知的模型操作')
        saved = engine.store.put(KIND, key, dict(config, binding=scope.binding(), target=target, method=method))
        engine.store.audit(actor, 'dcgm_workbench_' + operation, key,
                           {'source': scope.source, 'node': scope.node, 'target': target, 'method': method})
        return saved


def selected_model(engine, scope, target, method, review, version_id=None, reference=False):
    with TRAINING_LOCK:
        if reference:
            model, record = reference_model(engine, scope, target, method)
            return model, record
        config = configuration(engine, scope, target, method)
        version = (compatible_version(engine, scope, target, method, version_id) if version_id else
                   config.get('candidate') if review else config.get('active') if config['enabled'] else None)
        if not version:
            if review:
                raise ValueError('此方法尚无训练候选')
            return None, None
        if version['version'] == 'gwdg':
            model, record = reference_model(engine, scope, target, method)
            version = dict(version, origin='gwdg', library_id=record['id'])
        elif version.get('origin') == 'gwdg':
            model = joblib.load(version_path(version))
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


def replay(engine, scope, target, method, start, end, at=None, review=False, version_id=None, reference=False):
    if method not in methods_for(target):
        raise ValueError('模型与所选指标不匹配')
    scope.window(start, end)
    if at is not None and not start <= at <= end:
        raise ValueError('选中时刻须位于回放范围内')
    if reference and (scope.source != 'public' or method not in SINGLE or review or version_id):
        raise ValueError('样例仅支持公开数据的留出节点模型回放')
    issue = None
    try:
        model, version = selected_model(engine, scope, target, method, review, version_id, reference)
    except ValueError as exc:
        if review or version_id:
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
                        engine, scope, target, other, False, reference=reference)
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
            if version_id:
                saved = compatible_version(engine, scope, target, method, version_id)
            elif candidate and candidate['version'] == version['version']:
                saved = candidate
            else:
                raise ValueError('候选版本已变化，请刷新后重新验证')
            if saved.get('origin') != 'gwdg':
                saved.update(reviewed=True, review_points=scored, review_start=start, review_end=end)
                register_local(engine, scope, target, method, saved)
                if candidate and candidate['version'] == saved['version']:
                    config['candidate'] = saved
                    engine.store.put(KIND, scope.key(target, method), config)
    return result
