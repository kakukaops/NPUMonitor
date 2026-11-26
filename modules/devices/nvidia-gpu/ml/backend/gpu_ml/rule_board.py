"""Read-side catalog, deployed rule status and input curves for rule monitoring."""

from collections import defaultdict
from functools import lru_cache
import json
from math import isfinite
import re
import threading
import time

from .dcgm_sources import valid_reading
from .incident_queue import event_tags, timestamp
from .settings import BASE, DEFAULT_CLUSTER, SIMULATION

GROUP_NAME = 'GPU监控规则（OS SRE）'
OWNER = 'npumonitor-os-sre'
SOURCES = ('simulated', 'real_unverified', 'synthetic', 'public')
EXTRA_CATEGORIES = {
    'inforom_invalid': '内存与可靠性',
    'memory_unrepairable': '内存与可靠性',
    'recovery_required': '内存与可靠性',
    'remap_resource_exhausted': '内存与可靠性',
    'ecc_change_pending': '内存与可靠性',
    'thermal_margin_exhausted': '温度与时钟',
    'power_violation_recent': '温度与时钟',
    'fabric_manager_error': '拓扑与互连',
}
EXAMPLES = {
    'os_sre.gpu_thermal': ('GPU 温度超过设备门槛', (70., 97., 90.)),
    'os_sre.memory_thermal': ('显存温度超过设备门槛', (81., 116., 110.)),
    'os_sre.sram': ('SRAM 超阈值标志置位', (0., 1., None)),
}


@lru_cache(maxsize=1)
def rule_catalog():
    repository = BASE.parent / 'rules'
    installed = BASE / 'config'
    current = installed / 'rule-board-production.json'
    base = installed / 'rule-board-base.json'
    if not current.is_file():
        current = repository / 'runtime/production/catalog.json'
        base = repository / 'monitoring/os-sre/catalog.json'
    contract = json.loads(current.read_text())
    definitions = json.loads(base.read_text())
    provenance = {row['rule_id']: row.get('provenance', {}) for row in definitions['rules']}
    rules = {}
    for row in contract['rules']:
        key = row['rule_id']
        basis = provenance.get(key, {})
        category = basis.get('category') or EXTRA_CATEGORIES.get(key.split('.', 1)[-1], '数据质量')
        category = {'拓扑与fabric': '拓扑与互连', 'XID与SXid': '设备错误码'}.get(category, category)
        rules[key] = {
            'id': key, 'title': row['title'], 'category': category, 'severity': row['severity'],
            'fields': row.get('input_fields', []), 'for_seconds': row.get('for_seconds', 0), 'kind': row['kind'],
            'status': row.get('status'), 'note': row.get('note', ''),
            'criterion': basis.get('project_criterion', ''),
            'expression': row.get('expression', ''), 'example': EXAMPLES.get(key, (None,))[0],
        }
    return contract['version'], rules


def check_source(source):
    if source not in SOURCES or (source == 'synthetic' and not SIMULATION):
        raise ValueError('请选择可用的数据来源')


def deployment_source(deployment):
    if isinstance(deployment, str) and deployment:
        return 'simulated' if deployment in ('gpu-os-sre-master', 'h100-master-simulation-v1') else 'real_unverified'
    return None


def rows(response):
    return response if isinstance(response, list) else (response.get('list') or response.get('items') or [])


def read_nightingale_rules(client):
    groups = rows(client.call('GET', '/busi-groups?all=true&limit=1000'))
    matching = [item for item in groups if item['name'] == GROUP_NAME]
    if len(matching) != 1:
        return {'status': 'unconfigured', 'rules': {}, 'events': [], 'at': None}
    group_id = int(matching[0]['id'])
    known = rule_catalog()[1]
    rules, by_id = {}, {}
    for row in rows(client.call('GET', f'/busi-group/{group_id}/alert-rules')):
        tags = row.get('annotations') or {}
        identifier = tags.get('sre_rule_id')
        if tags.get('managed_by') != OWNER or identifier not in known:
            continue
        source = deployment_source(tags.get('deployment_id') or tags.get('deployment'))
        if source is None:
            continue
        rule_id = str(row['id'])
        rule_key = (source, identifier)
        previous = rules.get(rule_key)
        enabled = row.get('disabled') in (None, 0, '0')
        rules[rule_key] = {'id': identifier, 'source': source,
                           'enabled': enabled or bool(previous and previous['enabled'])}
        by_id[rule_id] = rules[rule_key]
    events = []
    for suffix, recovered in (('/alert-cur-events/list', False), ('/alert-his-events/list', True)):
        limit = 100 if recovered else 1000
        response = client.call('GET', f'{suffix}?bgid={group_id}&hours=24&limit={limit}')
        for row in rows(response):
            rule = by_id.get(str(row.get('rule_id')))
            when = timestamp(row.get('first_trigger_time')) or timestamp(row.get('trigger_time'))
            if not rule or not when or row.get('id') is None or (recovered and not row.get('is_recovered')):
                continue
            tags = event_tags(row)
            events.append({
                'id': str(row['id']), 'rule': rule['id'], 'source': rule['source'], 'at': when,
                'end': timestamp(row.get('recover_time')), 'active': not recovered,
                'uuid': tags.get('UUID'), 'cluster': tags.get('cluster_id'),
                'subject': (tags.get('UUID') or tags.get('switch_id') or tags.get('Hostname')
                            or tags.get('instance') or '监控平台'),
            })
    return {'status': 'connected', 'rules': rules, 'events': sorted(events, key=lambda row: -row['at']), 'at': time.time()}


class RuleBoard:
    def __init__(self, client):
        self.client = client
        self.lock = threading.Lock()
        self.snapshot = {'status': 'unavailable', 'rules': {}, 'events': [], 'at': None}
        self.refresh_at = -30

    def live(self):
        with self.lock:
            if time.monotonic() - self.refresh_at >= 20:
                try:
                    self.snapshot = read_nightingale_rules(self.client)
                except (OSError, ValueError, TypeError, KeyError, AttributeError):
                    self.snapshot = dict(self.snapshot, status='unavailable')
                self.refresh_at = time.monotonic()
            return self.snapshot

    def board(self, source):
        check_source(source)
        version, catalog = rule_catalog()
        snapshot = self.live() if source in ('simulated', 'real_unverified') else {
            'status': 'replay' if source == 'synthetic' else 'catalog', 'rules': {}, 'events': [], 'at': None,
        }
        events = [event for event in snapshot['events'] if event['source'] == source]
        by_rule = defaultdict(list)
        for event in events:
            by_rule[event['rule']].append(event)
        output = []
        for key, rule in catalog.items():
            deployment = snapshot['rules'].get((source, key))
            active = sum(event['active'] for event in by_rule[key])
            state = ('active' if active else 'enabled' if deployment and deployment['enabled'] else
                     'paused' if deployment else 'example' if source == 'synthetic' and rule['example'] else
                     'blocked' if rule['status'] == 'blocked' else 'catalog')
            output.append(dict({k: v for k, v in rule.items() if k not in ('expression', 'note', 'criterion')},
                               state=state, active=active))
        return {'version': version, 'rules': output, 'events': events,
                'status': snapshot['status'], 'at': snapshot['at']}

    def detail(self, engine, source, rule_id, entity='', event_id=''):
        check_source(source)
        rule = rule_catalog()[1].get(rule_id)
        if not rule:
            raise ValueError('未知规则')
        result = {'note': rule['note'], 'criterion': rule['criterion'], 'expression': rule['expression'], 'series': []}
        if source == 'synthetic':
            return dict(result, **rule_example(rule))
        if source not in ('simulated', 'real_unverified') or not entity:
            return result
        device = engine.store.get('entity', entity)
        if not device or device['source_type'] != source:
            raise ValueError('请选择当前来源中的采集设备')
        now = int(time.time()) // 10 * 10
        event = next((row for row in self.live()['events'] if row['id'] == event_id and row['rule'] == rule_id
                      and row['source'] == source and row['uuid'] == device['uuid']
                      and (not row['cluster'] or row['cluster'] == device['cluster'])), None) if event_id else None
        end = min(now, int(event['at']) // 10 * 10 + 600) if event else now
        start = end - 900
        try:
            series = rule_inputs(engine.source, rule['fields'], device, start, end)
        except (OSError, ValueError, RuntimeError):
            return dict(result, series_error='当前采集暂无法读取原始输入')
        return dict(result, series=series, start=start, end=end, marker=event['at'] if event else None)


def rule_inputs(source, fields, device, start, end):
    selected = {key for key in fields if re.fullmatch(r'[a-zA-Z_:][a-zA-Z0-9_:]*', key)}
    if not selected:
        return []
    labels = {'UUID': device['uuid'], '__name__': '|'.join(sorted(selected))}
    selector = '{' + ','.join(key + ('=~' if key == '__name__' else '=') + json.dumps(value)
                              for key, value in labels.items()) + '}'
    series = defaultdict(list)
    for row in source.query('last_over_time(' + selector + '[10s])', start, end, 10):
        attrs = row['metric']
        key = attrs.get('__name__')
        if (key not in selected or attrs.get('UUID') != device['uuid']
                or attrs.get('cluster_id', DEFAULT_CLUSTER) != device['cluster']
                or (attrs.get('simulated') == 'true') != (device['source_type'] == 'simulated')
                or attrs.get('GPU_I_ID') or attrs.get('GPU_I_PROFILE')):
            continue
        series[key].append([{'t': stamp, 'value': value} for stamp, raw in row['values']
                            if isfinite(value := float(raw)) and valid_reading(key, value)])
    return [{'field': field, 'points': series[field][0]} for field in fields if len(series[field]) == 1]


def rule_example(rule):
    item = EXAMPLES.get(rule['id'])
    if not item:
        return {}
    title, (normal, abnormal, threshold) = item
    start = 1795641600
    raise_at, clear_at = start + 120, start + 300
    end = start + 420
    readings = [{'t': t, 'value': abnormal if raise_at <= t < clear_at else normal}
                for t in range(start, end + 1, 10)]
    series = [{'field': rule['fields'][0], 'points': readings}]
    if threshold is not None:
        series.append({'field': rule['fields'][1], 'points': [{'t': p['t'], 'value': threshold} for p in readings]})
    return {'example_title': title, 'start': start, 'end': end, 'marker': raise_at + rule['for_seconds'],
            'active_start': raise_at + rule['for_seconds'], 'active_end': clear_at, 'series': series,
            'threshold': threshold}
