import tempfile
import unittest
from pathlib import Path

from gpu_ml.monitor_view import association_snapshot, replay_input, replay_results, sample_rows, summarize_confirmations
from gpu_ml.source import Source
from gpu_ml.store import Store


class MonitorViewTests(unittest.TestCase):
    def test_evidence_uses_confirmed_point_and_preserves_available_attribution(self):
        points = [{'t': 2, 'score': 9, 'threshold': 1, 'anomaly': True, 'values': {'power': 320}},
                  {'t': 4, 'score': 1.5, 'threshold': 1, 'anomaly': True, 'values': {'power': 290},
                   'contributions': {'power': 1.5}},
                  {'t': 6, 'score': .3, 'threshold': 1, 'values': {'power': 250}}]
        report = association_snapshot(points, [{'start': 4, 'end': 6}])
        self.assertEqual((report['t'], report['selection']), (4, 'confirmed_peak'))
        self.assertEqual(report['contributions'], {'power': 1.5})
        self.assertEqual(association_snapshot(points, [])['selection'], 'candidate_peak')
        self.assertIsNone(association_snapshot([], []))

    def test_online_evidence_never_prefers_a_previous_peak(self):
        points = [{'t': 2, 'score': 9, 'threshold': 1, 'anomaly': True, 'model': 'm'},
                  {'t': 6, 'score': .3, 'threshold': 1, 'model': 'm'}]
        state = {'quality': 'valid', 'last_source': 6, 'model_id': 'm'}
        report = association_snapshot(points, [{'start': 2, 'end': 6}], state)
        self.assertEqual((report['t'], report['selection']), (6, 'current'))
        state['quality'] = 'missing'
        self.assertEqual(association_snapshot(points, [], state)['selection'], 'last_valid')

    def test_replay_and_store_use_identical_confirmation_and_gap_rules(self):
        task = {'id': 'detector', 'confirmation_samples': 2, 'recovery_samples': 2}
        stamps = [100, 102, 104, 106, 108, 110, 112, 120, 122]
        decisions = [True, True, None, False, None, False, False, True, True]
        rows = [{'t': t, 'values': {} if decision is None else {'gpu_temp': 65.}}
                for t, decision in zip(stamps, decisions)]
        scored = [{'t': row['t'], 'values': row['values'], 'score': float(decision), 'threshold': .8, 'anomaly': decision}
                  for row, decision in zip(rows, decisions) if decision is not None]
        replay, state, episodes = replay_results(rows, scored, task, 'm1', 2, ['gpu_temp'])
        self.assertEqual(episodes, [{'start': 102, 'end': 112}, {'start': 122, 'end': None}])
        self.assertTrue(replay[2]['active'])
        self.assertEqual(replay[2]['quality'], 'missing')

        by_time = {point['t']: point for point in scored}
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root) / 'live.sqlite')
            for row, replay_point in zip(rows, replay):
                point = by_time.get(row['t'])
                result = {**point, 'model': 'm1', 'cadence_seconds': 2} if point else None
                actual = store.apply(task['id'], result, 'valid' if point else 'missing',
                                     row['t'], task['confirmation_samples'], task['recovery_samples'])
                self.assertEqual(actual['active'], replay_point['active'])
                self.assertEqual(actual['pending'], replay_point['pending'])
            self.assertEqual(state['last_source'], actual['last_source'])

    def test_sample_uses_requested_cadence_and_has_explicit_gaps(self):
        points = sample_rows(10001, 10301, 2, 'gpu_temp', 'gap')
        self.assertTrue(all(b['t']-a['t'] == 2 for a, b in zip(points, points[1:])))
        self.assertTrue(any(not row['values'] for row in points))
        self.assertIn('gpu_temp', points[0]['values'])

    def test_prometheus_missing_input_resets_confirmation_and_preserves_observation(self):
        class PartialSource(Source):
            def history_samples(self, entity, start, end, step, metrics=None):
                values = {'gpu_temp': {100: 80, 102: 80, 104: 85, 106: 80},
                          'power': {100: 200, 102: 200, 106: 200}}
                return {key: {stamp: stamp for stamp in row} for key, row in values.items()}, values, {}

        source = PartialSource()
        frames, observations = source.monitor_history('c|gpu', 100, 106, 2, ['gpu_temp', 'power'], ['gpu_temp', 'power'])
        self.assertEqual([point['t'] for point in source.history('c|gpu', 100, 106, 2, ['gpu_temp', 'power'])], [100, 102, 106])
        self.assertEqual(frames[2]['input_issues'], {'power': 'missing'})
        self.assertEqual(observations['gpu_temp'][2]['values']['gpu_temp'], 85)
        self.assertNotIn(104, [point['t'] for point in observations['power']])
        task = {'id': 'task', 'template': 'joint', 'confirmation_samples': 3}
        inputs = replay_input(frames, ['gpu_temp', 'power'], task)
        scores = [{**row, 'score': 2, 'threshold': 1, 'anomaly': True} for row in inputs]
        _, state, episodes = replay_results(frames, scores, task, 'model', 2, ['gpu_temp', 'power'])
        self.assertEqual(state['pending'], 1)
        self.assertEqual(episodes, [])

    def test_repeated_prometheus_source_value_does_not_count_twice(self):
        frames = [
            {'t': 100, 'source_time': 100, 'values': {'gpu_temp': 80}},
            {'t': 102, 'source_time': 100, 'values': {'gpu_temp': 80}},
            {'t': 104, 'source_time': 104, 'values': {'gpu_temp': 85}},
        ]
        task = {'id': 'task', 'template': 'uni_gpu_temp', 'confirmation_samples': 2}
        rows = replay_input(frames, ['gpu_temp'], task)
        scores = [{**row, 'score': 2, 'threshold': 1, 'anomaly': True} for row in rows]
        replay, _, episodes = replay_results(frames, scores, task, 'model', 2, ['gpu_temp'])
        self.assertEqual([point['t'] for point in replay], [100, 104])
        self.assertEqual(episodes, [{'start': 104, 'end': None}])

    def test_event_evaluation_uses_confirmation_time_and_explicit_labels(self):
        rows = [{'t': stamp, 'quality': quality} for stamp, quality in
                ((102, 'valid'), (104, 'valid'), (106, 'valid'), (112, 'missing'), (131, 'valid'), (135, 'valid'))]
        labels = [
            {'start': 100, 'end': 108, 'kind': 'fault'},
            {'start': 110, 'end': 116, 'kind': 'fault'},
            {'start': 130, 'end': 134, 'kind': 'normal_change'},
            {'start': 134, 'end': 138, 'kind': 'normal_change'},
        ]
        report = summarize_confirmations(rows, [{'start': 106}, {'start': 131}, {'start': 120}], labels)
        self.assertEqual(report['event_recall'], .5)
        self.assertEqual(report['normal_window_false_alarm_rate'], .5)
        self.assertEqual(report['unscored_fault_windows'], 1)
        self.assertEqual(report['median_detection_delay_seconds'], 6)
        self.assertAlmostEqual(report['unscored_fraction'], 1/6)
