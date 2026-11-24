import tempfile
import unittest
from pathlib import Path

from gpu_ml.monitor_view import replay_results, sample_rows
from gpu_ml.store import Store


class MonitorViewTests(unittest.TestCase):
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
