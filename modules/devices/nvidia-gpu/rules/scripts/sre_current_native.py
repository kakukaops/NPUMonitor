#!/usr/bin/env python3
"""Synchronize the current local Nightingale GPU group with native PromQL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re
from urllib.parse import urlencode
from urllib.request import Request

from sre_current_setup import PRIVATE, call, one, opener, write
from build_production_contract import build, prometheus_rules
from build_os_sre import compile_profile
from npumonitor_rules.nightingale import MONITORING_RELIABILITY_RULE_IDS, OWNER
from npumonitor_rules.selected_catalog import extend_selected_catalog


def inspect_query(query):
    request = Request(
        'http://127.0.0.1:19093/api/v1/query',
        data=urlencode({'query': query}).encode(),
    )
    with opener.open(request, timeout=20) as response:
        result = json.load(response)
    if result.get('status') != 'success' or result.get('data', {}).get('resultType') != 'vector':
        raise RuntimeError('Prometheus did not return a successful vector result')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads((PRIVATE/'config.json').read_text())
    deployment = config['deployment_id']
    group_id = config['nightingale']['group_id']
    route = f'/busi-group/{group_id}/alert-rules'
    group = one(call('/busi-groups?all=true&limit=1000'), 'GPU监控规则（OS SRE）')
    source = one(call('/datasource/list', {'plugin_type': 'prometheus'}), 'GPU主清单模拟-原始指标')
    if not group or group['id'] != group_id or not source or source.get('http', {}).get('url') != config['upstream']['url']:
        raise RuntimeError('Current GPU group or raw Prometheus binding is missing or changed')

    definition, _ = build()
    profile = config['profile']
    native_triggers = {}
    base = compile_profile(profile, with_provenance=False, additional_required_fields=definition['metric_contracts'],
                           native_triggers=native_triggers)
    catalog = extend_selected_catalog(base, profile, definition, production=True, native_triggers=native_triggers)
    native = prometheus_rules(catalog, native_triggers)['groups'][-1]['rules']
    inventory = {}
    for record in catalog['inventory_records']:
        inventory.setdefault(record['record'], []).append(record['expr'])

    def owned(rows):
        result = {}
        for row in rows:
            tags = row.get('annotations') or {}
            if tags.get('managed_by') != OWNER or tags.get('deployment_id') != deployment:
                continue
            ident = tags.get('sre_rule_id')
            if ident in result:
                raise RuntimeError('Duplicate GPU rule identity: ' + str(ident))
            result[ident] = row
        return result

    rows = call(route)
    current = owned(rows)
    wanted = {}
    for rule in native:
        ident = rule['labels']['sre_rule_id']
        query = re.sub(r'\bsre:inventory:\w+',
                       lambda match: '(' + ' or '.join(inventory.get(match[0], ['vector(0) > 0'])) + ')',
                       rule['expr'])
        old = current.get(ident, {})
        title = rule['annotations']['summary'].split(' · ', 1)[0]
        annotations = {k: v for k, v in (old.get('annotations') or {}).items()
                       if k not in ('bundle_sha', 'sync_operation')}
        annotations.update(managed_by=OWNER, deployment_id=deployment, sre_rule_id=ident,
                           execution='native-promql', input_metrics=rule['annotations']['input_metrics'])
        note = '原生 PromQL 触发。表达式退出表示当前条件未命中。'
        if ident.startswith(('os_sre.xid_', 'os_sre.sxid_')):
            code = 'SXID' if ident.startswith('os_sre.sxid_') else 'XID'
            note += f'事件触发值为实际 {code} 错误码。'
        wanted[ident] = {
            'name': old.get('name', f'NPUMonitor {deployment} {title}'),
            'group_id': group_id, 'cate': 'prometheus', 'prod': 'metric', 'disabled': 0,
            'datasource_queries': [{'match_type': 0, 'op': 'in', 'values': [source['id']]}],
            'rule_config': {'queries': [{
                'prom_ql': query, 'severity': int(rule['labels']['severity']),
                'recover_config': {'judge_type': 0},
            }]},
            'prom_eval_interval': config['nightingale']['eval_interval_seconds'],
            'prom_for_duration': int(rule['for'].removesuffix('s')),
            'notify_version': 1, 'notify_rule_ids': old.get('notify_rule_ids', [config['nightingale']['notify_rule_id']]),
            'notify_recovered': 1, 'notify_repeat_step': old.get('notify_repeat_step', 3600),
            'notify_max_number': old.get('notify_max_number', 3), 'recover_duration': 0,
            'append_tags': ['managed_by='+OWNER, 'deployment='+deployment, 'sre_rule_id='+ident],
            'annotations': annotations, 'note': note,
        }

    # Nightingale normalizes query metadata on save. Compare only the fields we manage.
    def matches(row, desired):
        for key in ('name', 'disabled', 'datasource_queries', 'prom_eval_interval',
                    'prom_for_duration', 'notify_rule_ids', 'annotations', 'note'):
            if row.get(key) != desired[key]:
                return False
        queries = row.get('rule_config', {}).get('queries', [])
        return len(queries) == 1 and all(queries[0].get(key) == value
                                         for key, value in desired['rule_config']['queries'][0].items()
                                         if key in ('prom_ql', 'severity'))

    retired = sorted(set(current) & MONITORING_RELIABILITY_RULE_IDS)
    unknown = set(current) - set(wanted) - set(retired)
    if unknown:
        raise RuntimeError('Unexpected managed rule definitions: ' + ', '.join(sorted(unknown)))
    occupied = {row['name'] for row in rows if row['id'] not in {r['id'] for r in current.values()}}
    if occupied & {rule['name'] for rule in wanted.values()}:
        raise RuntimeError('An unmanaged rule uses a GPU rule name')
    changes = [ident for ident, rule in wanted.items() if not matches(current.get(ident, {}), rule)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(inspect_query, (rule['rule_config']['queries'][0]['prom_ql'] for rule in wanted.values())))
    print(json.dumps({'validated': len(wanted), 'changes': len(changes), 'retire': len(retired),
                      'datasource_id': source['id']}), flush=True)
    if not args.apply or not (changes or retired):
        return

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = PRIVATE/f'native-migration-{timestamp}.json'
    write(backup, {'group_id': group_id, 'rules': list(current.values())})
    print(f'Saved rule backup: {backup}', flush=True)
    for ident in changes:
        desired = wanted[ident]
        if ident in current:
            old = current[ident]
            call(f'/busi-group/{group_id}/alert-rule/{old["id"]}', dict(old, **desired), method='PUT')
        else:
            call(route, [desired])
    migrated = owned(call(route))
    unmatched = [ident for ident, rule in wanted.items() if not matches(migrated.get(ident, {}), rule)]
    if unmatched:
        raise RuntimeError('Native readback mismatch: ' + ', '.join(unmatched))
    if retired:
        call(route, {'ids': [current[ident]['id'] for ident in retired]}, method='DELETE')
    final = owned(call(route))
    if set(final) != set(wanted) or any(not matches(final[ident], rule) for ident, rule in wanted.items()):
        raise RuntimeError('Final Nightingale readback does not match the native rule set')
    print(json.dumps({'verified_enabled': len(final), 'retired': len(retired), 'group_id': group_id}))


if __name__ == '__main__':
    main()
