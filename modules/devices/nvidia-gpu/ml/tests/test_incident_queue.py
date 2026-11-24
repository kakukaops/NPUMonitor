import unittest
import tempfile
from pathlib import Path

from gpu_ml.incident_queue import build_incident_queue, build_recovered_queue, group_overlaps
from gpu_ml.sre_preview import build_incident_example
from gpu_ml.store import Store

NOW = 1795500000


class IncidentQueueTests(unittest.TestCase):
    def test_example_groups_same_card_but_keeps_same_node_cards_separate(self):
        queue = build_incident_example(NOW)
        self.assertEqual([row['phase'] for row in queue['groups']], ['confirmed', 'confirmed', 'pending', 'recovered'])
        grouped = next(row for row in queue['groups'] if len(row['members']) == 2)
        self.assertEqual(grouped['start'], NOW - 11 * 60)
        self.assertEqual({row['family'] for row in grouped['members']}, {'univariate', 'multivariate'})
        pending = next(row for row in queue['groups'] if row['phase'] == 'pending')
        self.assertEqual(grouped['entity']['node'], pending['entity']['node'])
        self.assertNotEqual(grouped['entity']['uuid'], pending['entity']['uuid'])
        held = next(row for row in queue['groups'] if row['held'])
        self.assertIsNone(held['members'][0]['score'])
        self.assertTrue(held['members'][0]['missing'])
        self.assertEqual(grouped['members'][0]['notification']['event_id'], 412)
        self.assertEqual(queue['traces']['held'][-1]['t'], held['members'][0]['last_sample'])
        self.assertEqual(queue['traces']['pending'][-1]['score'], pending['members'][0]['score'])
        self.assertTrue(any(row['anomaly'] for row in queue['traces']['recovered']))
        self.assertFalse(queue['traces']['recovered'][-1]['anomaly'])

    def test_disjoint_episodes_on_one_card_remain_separate(self):
        rows = [
            {'id': 'a', 'phase': 'recovered', 'start': NOW - 40, 'end': NOW - 20},
            {'id': 'b', 'phase': 'confirmed', 'start': NOW - 10, 'end': None},
        ]
        self.assertEqual(list(group_overlaps(rows, NOW)), [[rows[0]], [rows[1]]])

    def test_multiple_recoveries_of_a_task_are_persisted_and_cluster_scoped(self):
        entity = {'id': 'c|GPU', 'uuid': 'GPU', 'cluster': 'c'}
        task = {'id': 't', 'entity': entity['id'], 'template': 't'}
        templates = {'t': {'name': 'GPU detector', 'kind': 'univariate', 'targets': ['util']}}
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'monitor.sqlite')
            store.put('entity', entity['id'], entity)
            store.put('task', task['id'], task)
            for offset, anomaly in ((30, True), (28, False), (10, True), (8, False)):
                point = {'t': NOW-offset, 'model': 'm', 'score': int(anomaly), 'threshold': .5,
                         'anomaly': anomaly, 'values': {'util': 50}}
                store.apply('t', point, confirmation_samples=1, recovery_samples=1)
            episodes = store.recovered_episodes(NOW-60, NOW, cluster='c')
            self.assertEqual(len(episodes), 2)
            self.assertEqual(store.recovered_episodes(NOW-60, NOW, cluster='other'), [])
            self.assertEqual(store.recovered_episode(episodes[0]['episode_id']), episodes[0])
            archived = build_recovered_queue([entity], [task], episodes, templates, [], {}, NOW)
            self.assertEqual([group['end'] for group in archived['groups']], [NOW-8, NOW-28])
            self.assertEqual(len({group['members'][0]['episode_id'] for group in archived['groups']}), 2)

    def test_nightingale_matches_current_episode_and_exact_device(self):
        entity = {'id': 'c|GPU', 'uuid': 'GPU', 'cluster': 'c', 'fresh': True, 'quality': {'util': 'valid'}}
        task = {'id': 't', 'entity': entity['id'], 'active_model': 'm', 'enabled': True, 'template': 't'}
        state = {'id': 't', 'active': True, 'opened_at': NOW - 20, 'last_source': NOW - 2,
                 'quality': 'valid', 'model_id': 'm', 'score': 1.2, 'threshold': 1.}
        bindings = [{'id': 't', 'rule_id': 7}]
        templates = {'t': {'name': 'GPU detector', 'kind': 'univariate', 'required': ['util'], 'targets': ['util']}}
        nightingale = {'connected': True, 'checked_at': NOW - 5, 'events': [
            {'id': 1, 'rule_id': 7, 'first_trigger_time': NOW - 40, 'trigger_time': NOW - 3},
            {'id': 2, 'rule_id': 7, 'trigger_time': NOW - 5, 'tags': ['UUID=other']},
        ]}

        def member(inference_enabled=True):
            queue = build_incident_queue([entity], [task], [state], templates, bindings, nightingale,
                                         NOW, inference_enabled)
            return queue['groups'][0]['members'][0]

        self.assertEqual(member()['notification']['status'], 'no_event')
        nightingale['events'].append({'rule_id': 7, 'id': 3, 'trigger_time': NOW - 5, 'tags': ['UUID=GPU']})
        self.assertEqual(member()['notification']['event_id'], 3)
        nightingale['checked_at'] = NOW - 60
        self.assertEqual(member()['notification']['status'], 'unavailable')
        self.assertEqual(member(False)['phase'], 'confirmed')
        self.assertEqual(member(False)['quality'], 'paused')
        self.assertIsNone(member(False)['score'])

        state.update(active=False, pending=1, last_source=NOW - 180)
        queue = build_incident_queue([entity], [task], [state], templates, bindings, nightingale, NOW)
        self.assertFalse(queue['groups'])
        self.assertEqual(queue['devices'][0]['scored'], 0)
        self.assertEqual(queue['devices'][0]['issues'][0]['quality'], 'inference_stale')
