import copy
import tempfile
import unittest
from pathlib import Path

from gpu_ml.pipeline import build_pipeline, load_artifact
from gpu_ml_runtime.detectors import available_algorithms
from gpu_ml_runtime.catalog import TEMPLATES
from test_v2 import data


class AddedDetectorTests(unittest.TestCase):
    def test_catalog_keeps_saved_schemas_compatible(self):
        spec = TEMPLATES['uni_gpu_temp']
        original = copy.deepcopy(spec)
        self.assertEqual(available_algorithms(spec), ['temporal_mad', 'level_mad', 'rolling_median'])
        self.assertEqual(spec, original)
        model = build_pipeline('uni_gpu_temp', 'rolling_median', spec=original)
        self.assertEqual(model.spec, original)
        with self.assertRaises(ValueError):
            build_pipeline('joint_gpu', 'rolling_median')

    def test_rolling_median_scores_current_without_using_it_as_input(self):
        model = build_pipeline('uni_gpu_temp', 'rolling_median')
        rows = data()
        report = model.fit(rows)
        self.assertIn('forecast_comparison', report['test'])
        normal = rows[-50:]
        changed = copy.deepcopy(normal)
        changed[15]['values']['gpu_temp'] += 50
        before, after = model.predict(normal), model.predict(changed)
        point = 15 - model.window
        self.assertEqual(before[:point], after[:point])
        self.assertEqual(before[point]['expected'], after[point]['expected'])
        self.assertTrue(after[point]['anomaly'])
        self.assertIn('gpu_temp', after[point]['bounds'])

    def test_window_pca_skips_gaps_and_roundtrips(self):
        model = build_pipeline('joint_gpu', 'joint_window_pca')
        rows = data()
        model.fit(rows)
        test = rows[-50:]
        first = model.predict(test[:25])
        self.assertEqual(first[-1]['t'], test[24]['t'])
        longer = model.predict(test)
        self.assertAlmostEqual(first[-1]['score'], longer[len(first) - 1]['score'])
        self.assertEqual(set(first[-1]['contributions']), set(model.spec['targets']))
        gapped = test[:12] + test[13:]
        at_gap = {r['t'] for r in model.predict(gapped)}
        self.assertFalse(any(row['t'] in at_gap for row in test[13:17]))
        self.assertIn(test[17]['t'], at_gap)
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / 'window-pca.joblib'
            digest = model.save(artifact)
            self.assertEqual(longer, load_artifact(artifact, digest).predict(test))
