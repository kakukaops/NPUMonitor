"""Regression checks for the DCGM node gate and public-data contract."""
import hashlib
import unittest

import numpy as np

from gpu_ml.dcgm_detection import NO_DATA, PUBLIC, WINDOW, Capture, assess, features, joint_point, public_capture, public_catalog
from gpu_ml.dcgm_sources import build_capture


class DcgmDetectionTest(unittest.TestCase):
    def test_saved_observations_preserve_xid_when_all_dcgm_is_missing(self):
        collection = 'collection_7a246afef961d90a'
        capture = public_capture(collection)
        at = capture.start + 8951 * 10
        self.assertEqual(capture.xid[8951], 1)
        for metric in ('DCGM_FI_DEV_GPU_TEMP', 'all'):
            point = assess(capture, metric, None, at, at)['points'][0]
            self.assertEqual(point, {'t': at, 'state': 'no_data', 'warning': NO_DATA})

    def test_partial_data_and_observed_zero_do_not_fire_the_gate(self):
        metrics = public_catalog()['metrics']
        observations = np.full((WINDOW + 1, len(metrics) + 1), np.nan)
        observations[WINDOW - 1:, 0] = 0
        observations[WINDOW - 1, -1] = 32
        capture = build_capture(0, len(observations), {'gpu': observations},
                                {'gpu': np.ones(len(observations), dtype=bool)})
        self.assertEqual(capture.xid[WINDOW - 1], 1)
        self.assertTrue(np.isnan(capture.xid[WINDOW]))
        result = assess(capture, metrics[-1], None, 280, 300)
        self.assertEqual([p['state'] for p in result['points']], ['no_data', 'untrained', 'untrained'])

    def test_model_inputs_are_causal_and_exclude_xid(self):
        base = public_capture('collection_7a246afef961d90a')
        ends = np.array([100, 200])
        channels = base.channels.copy()
        channels[201:] = 99999
        changed = Capture(base.start, channels, np.ones(len(base.xid)))
        expected = features(base, 'all', ends)
        self.assertEqual(expected.shape, (2, 504))
        np.testing.assert_allclose(features(changed, 'all', ends), expected, equal_nan=True)

    def test_joint_point_gates_all_three_methods_together(self):
        capture = public_capture('collection_7a246afef961d90a')
        at = capture.start + 8951 * 10

        def fail(*args):
            self.fail('No model should be loaded for a point with all DCGM inputs missing')

        comparison = joint_point(capture, at, 'unlabeled', fail)
        self.assertEqual(comparison['t'], at)
        self.assertEqual(
            [(row['method'], row['mode'], row['state']) for row in comparison['methods']],
            [('shallow_tree', 'supervised', 'no_data'), ('robust_range', 'unlabeled', 'no_data'),
             ('pca_t2', 'unlabeled', 'no_data')],
        )

    def test_joint_point_shares_the_same_time_and_reports_each_model_state(self):
        capture = public_capture('collection_7a246afef961d90a')
        index = np.flatnonzero(capture.available[WINDOW:] & np.isfinite(capture.channels[WINDOW:, 5, 0]))[0] + WINDOW
        at = capture.start + int(index) * 10
        model = dict(method='robust_range', keep=np.array([5 * 28]), center=np.zeros(1), scale=np.ones(1),
                     median=np.zeros(1), robust_scale=np.ones(1), threshold=0.)

        def load(method, mode):
            if method == 'robust_range':
                self.assertEqual(mode, 'reference')
                return model
            if method == 'pca_t2':
                raise ValueError('Calibration unavailable')
            return None

        comparison = joint_point(capture, at, 'reference', load)
        untrained, alarm, unavailable = comparison['methods']
        self.assertEqual(untrained['state'], 'untrained')
        self.assertEqual(alarm['state'], 'alarm')
        self.assertEqual(alarm['drivers'][0]['metric'], 'DCGM_FI_DEV_GPU_TEMP')
        self.assertEqual(unavailable['detail'], 'Calibration unavailable')

    def test_bundled_intervals_match_index(self):
        rows = public_catalog()['collections']
        self.assertEqual(len(rows), 48)
        self.assertEqual(len({row['node'] for row in rows}), 19)
        for row in rows:
            payload = (PUBLIC / (row['id'] + '.json')).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), row['sha256'])
            self.assertNotIn(b'"available":', payload)


if __name__ == '__main__':
    unittest.main()
