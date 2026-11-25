"""Verify the common review contract and source isolation."""

import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from gpu_ml.dcgm_detection import CORE_METRICS, features, public_capture
from gpu_ml.dcgm_review import node_review, review_target, TREND_FIELDS
from gpu_ml.simulation import CLUSTER


class FixtureSource:
    def __init__(self, source, cluster, node=None):
        self.source = source
        self.cluster = cluster
        self.node = node
        self.url = 'http://fixture'
        self.queries = []

    def query(self, expression, start, end, step):
        self.queries.append(expression)
        label = {'UUID': 'card-1', 'cluster_id': self.cluster}
        if self.node:
            label['Hostname'] = self.node
        if self.source == 'simulated':
            label['simulated'] = 'true'
        t = np.arange(start, end + 1, step)
        for i, key in enumerate(TREND_FIELDS):
            values = 50 + i * 8 + np.sin(t / 30) * 3
            yield {'metric': dict(label, __name__=key),
                   'values': [(int(stamp), str(float(v))) for stamp, v in zip(t, values)]}


def engine_for(source=None, cards=()):
    return SimpleNamespace(source=source, store=SimpleNamespace(list=lambda _: list(cards)))


class NodeReviewTest(unittest.TestCase):
    def test_public_review_exposes_node_and_cards_without_fabricating_card_xid(self):
        r = node_review(engine_for(), 'public', collection='collection_7a246afef961d90a')
        self.assertEqual(r['source'], 'public')
        self.assertEqual(r['identity'], 'node')
        self.assertTrue(r['cards'])
        self.assertTrue(all(x['xid'] is None for x in r['cards']))
        self.assertEqual(features(public_capture('collection_7a246afef961d90a'), 'core',
                                  np.array([400])).shape, (1, 28 * len(CORE_METRICS)))

    @patch('gpu_ml.dcgm_review.SIMULATION', True)
    def test_synthetic_scores_trend_and_preserves_unknown_xid(self):
        r = node_review(engine_for(), 'synthetic', scenario='drift')
        self.assertIsNone(r['xid'])
        self.assertIn(r['node_detection']['state'], ('alarm', 'scored'))
        trend = r['cards'][0]['trends']['DCGM_FI_DEV_GPU_TEMP']
        self.assertEqual(trend['state'], 'alarm')
        self.assertGreaterEqual(trend['duration'], 3)
        self.assertEqual(len(trend['points']), 30)

    @patch('gpu_ml.dcgm_review.SIMULATION', True)
    def test_synthetic_gap_does_not_generate_an_alarm_score(self):
        r = node_review(engine_for(), 'synthetic', scenario='gap')
        self.assertEqual(r['node_detection']['state'], 'missing')
        self.assertFalse(r['cards'][0]['observed'])
        self.assertEqual(r['cards'][0]['trends']['DCGM_FI_DEV_GPU_TEMP']['state'], 'missing')

    def test_simulated_and_real_share_the_review_pipeline(self):
        for kind, cluster, node in [('simulated', CLUSTER, None), ('real_unverified', 'lab', 'host-a')]:
            with self.subTest(kind=kind):
                source = FixtureSource(kind, cluster, node)
                e = engine_for(source, [{'uuid': 'card-1', 'source_type': kind, 'cluster': cluster, 'node': node}])
                r = node_review(e, kind, cluster=cluster, node=node or '', at=int(time.time()) - 10)
                self.assertIn(r['node_detection']['state'], ('alarm', 'scored'))
                self.assertIn('跨源影子评分', r['node_detection']['version'])
                self.assertEqual(r['cards'][0]['gpu'], 'card-1')
                self.assertEqual(len(r['cards'][0]['trends']['DCGM_FI_DEV_GPU_TEMP']['points']), 30)
                self.assertIn('simulated="true"' if kind == 'simulated' else 'simulated!="true"', source.queries[0])
                self.assertIn('Hostname=""' if not node else 'Hostname="host-a"', source.queries[0])

    def test_unlabeled_real_cards_require_exact_gpu_scope(self):
        e = engine_for(None, [{'uuid': 'gpu-a', 'source_type': 'real_unverified', 'cluster': 'lab'}])
        self.assertEqual(review_target(e, 'real_unverified', 'lab', '', 'gpu-a'), ('gpu-a',))
        with self.assertRaises(ValueError):
            review_target(e, 'real_unverified', 'lab', '', '')
        with self.assertRaises(ValueError):
            review_target(e, 'simulated', 'lab', '', 'gpu-a')
