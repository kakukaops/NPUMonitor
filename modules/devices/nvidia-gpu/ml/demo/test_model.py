"""Independent held-out replay tests; no anomaly labels are model inputs."""
import unittest
import numpy as np
from model import Detector, healthy, inject
import app


class DetectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector(0)

    def test_held_out_normal_false_positive_budget(self):
        ts = np.arange(10000, 12000, 2)
        _, scores, _ = self.detector.evaluate(ts, healthy(ts, seed=123))
        self.assertLess(np.mean(scores > self.detector.threshold), .025)

    def test_four_anomaly_scenarios(self):
        ts = np.arange(12000, 12200, 2)
        normal = healthy(ts, seed=131)
        for scenario in ('spike', 'drop', 'drift', 'correlation'):
            with self.subTest(scenario=scenario):
                _, scores, _ = self.detector.evaluate(ts, inject(normal, scenario, 30))
                self.assertGreater(np.mean(scores > self.detector.threshold), .8)

    def test_missing_or_stale_data_is_not_normal(self):
        app.MODELS.update({s: self.detector for s in app.SERVICES})
        result = app.assemble([], 1000)
        self.assertTrue(all(s['status'] == 'no_data' for s in result))
        rows = []
        for name, signal, value in [('ml_demo_sample_time', None, 10), ('ml_demo_truth', None, 0),
                                     ('ml_demo_value', 'qps', 900), ('ml_demo_value', 'latency_ms', 85),
                                     ('ml_demo_value', 'cpu_percent', 43)]:
            labels = {'__name__': name, 'service': 'checkout'}
            if signal:
                labels['signal'] = signal
            rows.append({'metric': labels, 'values': [[1000, str(value)]]})
        self.assertEqual(app.assemble(rows, 1000)[0]['points'], [])

    def test_lookback_duplicates_cannot_create_sustained_alert(self):
        app.MODELS.update({s: self.detector for s in app.SERVICES})
        rows = []
        for name, signal, value in [('ml_demo_sample_time', None, 1000), ('ml_demo_truth', None, 1),
                                     ('ml_demo_value', 'qps', 900), ('ml_demo_value', 'latency_ms', 250),
                                     ('ml_demo_value', 'cpu_percent', 43)]:
            labels = {'__name__': name, 'service': 'checkout'}
            if signal:
                labels['signal'] = signal
            rows.append({'metric': labels, 'values': [[t, str(value)] for t in (1000, 1002, 1004, 1006)]})
        result = app.assemble(rows, 1007)[0]
        self.assertEqual(len(result['points']), 1)
        self.assertNotEqual(result['status'], 'alert')
        original = result['points'][0]['score']
        rows[1]['values'] = [[t, '0'] for t in (1000, 1002, 1004, 1006)]
        self.assertEqual(app.assemble(rows, 1007)[0]['points'][0]['score'], original)

    def test_future_samples_do_not_change_past_scores(self):
        ts = np.arange(15000, 15200, 2)
        normal = healthy(ts, seed=333)
        _, before, _ = self.detector.evaluate(ts[:50], normal[:50])
        normal[50:] = inject(normal[50:], 'spike', 10)
        _, after, _ = self.detector.evaluate(ts, normal)
        np.testing.assert_array_equal(before, after[:50])


if __name__ == '__main__':
    unittest.main()
