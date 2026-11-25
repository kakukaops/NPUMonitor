"""Read-side view of current and most recently recovered detector episodes."""

from collections import defaultdict
from math import isfinite

from .settings import FRESHNESS

DAY = 86400
SYNC_MAX_AGE = 45
PHASE_ORDER = {'confirmed': 0, 'pending': 1, 'recovered': 2}


def timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0:
        return value
    return None


def event_tags(event):
    if isinstance(event.get('tags_map'), dict) and event['tags_map']:
        return event['tags_map']
    return dict(tag.split('=', 1) for tag in event.get('tags') or [] if isinstance(tag, str) and '=' in tag)


def notification(task, member, entity, binding, records, connected, now):
    policy = task.get('notification_mode', 'alert')
    rule_id = binding.get('rule_id') if binding else None
    result = {'policy': policy, 'rule_id': rule_id}
    if member['phase'] == 'pending':
        return dict(result, status='pending')
    if connected and rule_id is not None:
        for event in records.get(str(rule_id), []):
            start = timestamp(event.get('first_trigger_time')) or timestamp(event.get('trigger_time'))
            end = member['end'] or now
            tags = event_tags(event)
            if start is None or start < member['start'] or start > end:
                continue
            if any(str(tags[key]) != str(expected) for key, expected in (
                ('UUID', entity['uuid']), ('cluster_id', entity['cluster']), ('detector_id', task['id'])
            ) if key in tags):
                continue
            return dict(result, status='recorded', event_id=event['id'], at=start,
                        hash=event.get('hash'), recovered=bool(event.get('is_recovered')))
    if policy == 'evidence':
        return dict(result, status='evidence_only')
    if rule_id is None:
        return dict(result, status='unbound')
    return dict(result, status='no_event' if connected else 'unavailable')


def task_signal(task, state, entity, spec, now, inference_enabled):
    last_sample, quality = task_input_quality(task, state, entity, now, inference_enabled)
    start = timestamp(state.get('opened_at'))
    end = None
    if state.get('active') and start is not None:
        phase = 'confirmed'
    elif quality == 'valid' and state.get('pending', 0) > 0:
        phase, start = 'pending', last_sample
    elif state.get('reason') == 'fresh_normal_confirmed':
        end = timestamp(state.get('closed_at'))
        if start is None or end is None or not start <= end <= now or now - end > DAY:
            return None
        phase = 'recovered'
    else:
        return None
    if start > now:
        return None

    current_score = quality == 'valid' and phase != 'recovered'
    return {
        'id': task['id'], 'name': spec.get('name') or task['name'],
        'episode_id': state.get('episode_id') if phase != 'pending' else None,
        'family': 'scenario' if task.get('scenario_id') else spec.get('kind', 'legacy'),
        'phase': phase, 'start': start, 'end': end, 'quality': quality, 'last_sample': last_sample,
        'pending': state.get('pending', 0), 'confirmation': task.get('confirmation_samples', 3),
        'clear_count': state.get('clear_count', 0), 'recovery': task.get('recovery_samples', 3),
        'metrics': spec.get('targets', []), 'reason_metric': state.get('reason_metric'),
        'inputs': spec.get('required', []),
        'conditions': spec.get('features', []) if task.get('scenario_id') else [],
        'directions': spec.get('directions', []) if task.get('scenario_id') else [],
        'contributions': state.get('contributions', {}) if current_score else {},
        'missing': [
            key for key in spec.get('required', [])
            if not entity['fresh'] or entity.get('quality', {}).get(key) != 'valid'
        ],
        'score': state.get('score') if current_score else None,
        'threshold': state.get('threshold') if current_score else None,
    }


def task_input_quality(task, state, entity, now, inference_enabled):
    last_sample = timestamp(state.get('last_source'))
    quality = state.get('quality', 'unverified')
    if not inference_enabled:
        quality = 'paused'
    elif quality == 'valid' and state.get('model_id') != task['active_model']:
        quality = 'model_changed'
    elif quality == 'valid' and (not entity['fresh'] or last_sample is None or not 0 <= now - last_sample <= FRESHNESS):
        quality = 'inference_stale'
    return last_sample, quality


def group_overlaps(members, now):
    """Merge overlapping time ranges for exactly one GPU."""
    end = None
    group = []
    for member in sorted(members, key=lambda row: (row['start'], row['id'])):
        if group and member['start'] > end:
            yield group
            group = []
        # A pending signal only has an observed sample time in the current state.
        stop = member['end'] or (member['start'] if member['phase'] == 'pending' else now)
        end = max(end, stop) if group else stop
        group.append(member)
    if group:
        yield group


def notification_records(nightingale, now):
    checked_at = timestamp(nightingale.get('checked_at'))
    connected = bool(nightingale.get('connected') and checked_at and 0 <= now - checked_at <= SYNC_MAX_AGE)
    records = defaultdict(list)
    if connected:
        for event in [*(nightingale.get('events') or []), *(nightingale.get('history') or [])]:
            if event.get('rule_id') is not None and event.get('id') is not None:
                records[str(event['rule_id'])].append(event)
    return records, connected, checked_at


def build_incident_queue(entities, tasks, states, templates, bindings, nightingale, now, inference_enabled=True):
    by_entity = {entity['id']: entity for entity in entities}
    by_binding = {binding['id']: binding for binding in bindings}
    by_state = {state['id']: state for state in states}
    records, connected, checked_at = notification_records(nightingale, now)
    per_entity = defaultdict(list)
    coverage = defaultdict(lambda: {'enabled': 0, 'scored': 0})
    devices = {entity['id']: {'entity': {key: entity.get(key) for key in ('id', 'uuid', 'cluster', 'node', 'source_type')},
                              'enabled': 0, 'scored': 0, 'issues': [], 'signals': 0} for entity in entities}
    for task in tasks:
        entity = by_entity.get(task['entity'])
        if not entity or task.get('deleted'):
            continue
        device = devices[entity['id']]
        spec = templates[task['template']]
        name = spec.get('name') or task['name']
        if not task.get('enabled') or not task.get('active_model'):
            device['issues'].append({'name': name, 'quality': 'paused' if not task.get('enabled') else 'untrained',
                                     'missing': []})
            continue
        state = by_state.get(task['id'], {})
        counts = coverage[entity['cluster']]
        counts['enabled'] += 1
        device['enabled'] += 1
        _, quality = task_input_quality(task, state, entity, now, inference_enabled)
        if quality == 'valid':
            counts['scored'] += 1
            device['scored'] += 1
        else:
            device['issues'].append({'name': name, 'quality': quality, 'missing': [
                key for key in spec.get('required', []) if not entity['fresh'] or entity.get('quality', {}).get(key) != 'valid'
            ]})
        member = task_signal(task, state, entity, spec, now, inference_enabled)
        if member:
            member['notification'] = notification(task, member, entity, by_binding.get(task['id']), records, connected, now)
            per_entity[entity['id']].append(member)
            if member['phase'] != 'recovered':
                device['signals'] += 1

    groups = incident_groups(per_entity, by_entity, now)
    return {'groups': groups, 'coverage': dict(coverage), 'devices': list(devices.values()), 'nightingale_connected': connected,
            'nightingale_checked_at': checked_at, 'at': now}


def build_recovered_queue(entities, tasks, episodes, templates, bindings, nightingale, now):
    by_entity = {entity['id']: entity for entity in entities}
    by_task = {task['id']: task for task in tasks}
    by_binding = {binding['id']: binding for binding in bindings}
    records, connected, checked_at = notification_records(nightingale, now)
    per_entity = defaultdict(list)
    for episode in episodes:
        task = by_task.get(episode['id'])
        entity = by_entity.get(task['entity']) if task else None
        if not entity:
            continue
        spec = templates[task['template']]
        member = {
            'id': task['id'], 'episode_id': episode['episode_id'], 'name': spec.get('name') or task['name'],
            'family': 'scenario' if task.get('scenario_id') else spec.get('kind', 'legacy'),
            'phase': 'recovered', 'start': episode['opened_at'], 'end': episode['closed_at'],
            'quality': 'valid', 'last_sample': episode['last_source'], 'pending': 0,
            'confirmation': episode['confirmation_samples'], 'clear_count': episode['clear_count'],
            'recovery': episode['recovery_samples'], 'metrics': spec['targets'],
            'inputs': spec.get('required', []),
            'conditions': spec.get('features', []) if task.get('scenario_id') else [],
            'directions': spec.get('directions', []) if task.get('scenario_id') else [],
            'reason_metric': episode.get('reason_metric'), 'contributions': {}, 'missing': [],
            'score': None, 'threshold': None,
        }
        member['notification'] = notification(task, member, entity, by_binding.get(task['id']), records, connected, now)
        per_entity[entity['id']].append(member)
    groups = incident_groups(per_entity, by_entity, now)
    groups.sort(key=lambda group: -group['end'])
    return {'groups': groups, 'at': now, 'nightingale_connected': connected, 'nightingale_checked_at': checked_at}


def attach_incident_evidence(queue, read_points, models):
    members = [member for group in queue['groups'] for member in group['members']]
    points = read_points(members)
    algorithms = {model['id']: model['algorithm'] for model in models}
    for member in members:
        point = points.get((member['id'], member['start'], member.get('episode_id')))
        if point is None:
            continue
        member['decision'] = {
            key: point[key] for key in ('t', 'model', 'score', 'threshold', 'values', 'expected',
                                       'contributions', 'evidence') if key in point
        }
        member['decision']['algorithm'] = algorithms.get(point.get('model'))
    return queue


def incident_groups(per_entity, by_entity, now):
    groups = []
    for entity_id, members in per_entity.items():
        entity = by_entity[entity_id]
        for signals in group_overlaps(members, now):
            lead = min(signals, key=lambda row: (PHASE_ORDER[row['phase']], row['start']))
            pending = [row for row in signals if row['phase'] == 'pending']
            confirmed = [row for row in signals if row['phase'] == 'confirmed']
            held = [row for row in confirmed if row['quality'] != 'valid']
            groups.append({
                'id': f"{entity_id}|{signals[0]['id']}|{signals[0]['start']}",
                'entity': {key: entity.get(key) for key in ('id', 'uuid', 'cluster', 'node', 'source_type')},
                'phase': lead['phase'], 'start': min(row['start'] for row in signals),
                'end': max(row['end'] for row in signals) if lead['phase'] == 'recovered' else None,
                'pending': len(pending), 'confirmed': len(confirmed), 'held': len(held),
                'members': sorted(signals, key=lambda row: (PHASE_ORDER[row['phase']], row['start'])),
            })
    groups.sort(key=lambda row: (PHASE_ORDER[row['phase']], -row['start'], row['id']))
    return groups
