"""Method board lifecycle and source-bound training regressions."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

import numpy as np

from gpu_ml import dcgm_workbench as workbench
from gpu_ml.dcgm_detection import CORE_METRICS, XID
from gpu_ml.simulation import CLUSTER, Simulator, UUIDS
from gpu_ml.store import Store

COLLECTION = 'collection_7a246afef961d90a'
METRIC = 'DCGM_FI_DEV_GPU_TEMP'


class SimulatedSource:
    def query(self, expression, start, end, step):
        self.last_query = expression
        times = np.arange(start, end + 1, step)
        series = ((field, 50 + i * 7 + 5 * np.sin(times / 240)) for i, field in enumerate(CORE_METRICS))
        for field, values in [*series, (XID, np.zeros(len(times)))]:
            yield {'metric': {'__name__': field, 'UUID': UUIDS[0], 'cluster_id': CLUSTER, 'simulated': 'true'},
                   'values': list(zip(times, values))}


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = temp.name
        data_patch = patch.object(workbench, 'DATA', Path(directory))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.engine = SimpleNamespace(store=Store(Path(directory) / 'store.db'), source=SimulatedSource())
        self.engine.store.put('entity', UUIDS[0], {
            'source_type': 'simulated', 'cluster': CLUSTER, 'uuid': UUIDS[0],
        })
        gpu = next(iter(workbench.collection_cards(COLLECTION)))
        self.public = workbench.scope_for(self.engine, 'public', COLLECTION, gpu=gpu)
        self.simulated = workbench.scope_for(self.engine, 'simulated', cluster=CLUSTER, gpu=UUIDS[0])

    def scored(self, result):
        return [p for p in result['points'] if p['state'] in ('scored', 'alarm')]

    def test_public_card_trend_training_review_enable_and_pause(self):
        scope, method = self.public, 'rolling_median'
        end = scope.start + 12 * 3600
        start, stop = scope.start + 13 * 3600, scope.start + 16 * 3600
        before = workbench.board_state(self.engine, scope, METRIC)['methods']
        self.assertTrue(before['pca_t2']['enabled'])
        self.assertFalse(before[method]['enabled'])
        cfg = workbench.update(self.engine, scope, METRIC, method, 'train', 'operator', end)
        self.assertFalse(cfg['candidate']['reviewed'])
        with self.assertRaisesRegex(ValueError, '验证'):
            workbench.update(self.engine, scope, METRIC, method, 'enable', 'operator')
        with self.assertRaisesRegex(ValueError, '独立有效评分'):
            workbench.replay(self.engine, scope, METRIC, method, end - 600, end, review=True)
        reviewed = workbench.replay(self.engine, scope, METRIC, method, start, stop, review=True)
        self.assertTrue(any(p.get('bounds') for p in self.scored(reviewed)))
        cfg = workbench.update(self.engine, scope, METRIC, method, 'enable', 'operator')
        self.assertTrue(cfg['enabled'])
        self.assertEqual(cfg['active']['version'], reviewed['version']['version'])
        self.assertTrue(self.scored(workbench.replay(self.engine, scope, METRIC, method, start, stop)))
        workbench.update(self.engine, scope, METRIC, method, 'pause', 'operator')
        self.assertFalse(self.scored(workbench.replay(self.engine, scope, METRIC, method, start, stop)))
        self.assertTrue(workbench.board_state(self.engine, scope, METRIC)['methods']['pca_t2']['enabled'])

    def test_simulated_reference_training_keeps_node_versions_separate(self):
        scope, target, method = self.simulated, 'core', 'robust_range'
        end = int(time.time()) // 10 * 10
        train_end = end - 1200
        cfg = workbench.update(self.engine, scope, target, method, 'train', 'operator', train_end)
        self.assertGreaterEqual(cfg['candidate']['calibration'], 120)
        reviewed = workbench.replay(self.engine, scope, target, method, end - 600, end, review=True)
        self.assertEqual(len(self.scored(reviewed)), 61)
        self.assertIn('UUID=~', self.engine.source.last_query)
        workbench.update(self.engine, scope, target, method, 'enable', 'operator')
        result = workbench.replay(self.engine, scope, target, method, end - 600, end, at=end)
        self.assertEqual(len(result['comparison']['methods']), 3)
        self.assertEqual(list(result['labels']), [UUIDS[0]])
        self.assertEqual(workbench.board_state(self.engine, self.public, target)['methods'][method]['active']['version'], 'gwdg')
        with self.assertRaisesRegex(ValueError, '待标注|待采集'):
            workbench.update(self.engine, scope, target, 'shallow_tree', 'train', 'operator', train_end)

    def test_simulator_xid_opt_in(self):
        sim = Simulator()
        normal = [row for row in sim.metrics().splitlines() if row.startswith(XID + '{')]
        self.assertEqual(len(normal), len(UUIDS))
        self.assertTrue(all(row.endswith(' 0') for row in normal))
        sim.set(UUIDS[0], 'xid_fault')
        fault = [row for row in sim.metrics().splitlines() if row.startswith(XID + '{')]
        self.assertEqual(sum(row.endswith(' 79') for row in fault), 1)
        self.assertIn(UUIDS[0], next(row for row in fault if row.endswith(' 79')))

    def test_simulated_card_baseline_uses_its_own_training_history(self):
        scope, method = self.simulated, 'rolling_median'
        end = scope.end
        cfg = workbench.update(self.engine, scope, METRIC, method, 'train', 'operator', end - 900)
        self.assertFalse(cfg['enabled'])
        result = workbench.replay(self.engine, scope, METRIC, method, end - 600, end, review=True)
        self.assertFalse(result['node_level'])
        self.assertTrue(self.scored(result)[0]['bounds'][METRIC])
        self.assertEqual(list(result['series'][METRIC]), [UUIDS[0]])
        self.assertFalse(workbench.board_state(self.engine, self.public, METRIC)['methods'][method]['candidate'])

    def test_library_reuses_exact_versions_without_replacing_new_candidate(self):
        scope, method = self.simulated, 'level_mad'
        end = scope.end
        first = workbench.update(self.engine, scope, METRIC, method, 'train', 'operator', end - 1800)['candidate']
        first_id = first['version']
        workbench.replay(self.engine, scope, METRIC, method, end - 600, end, review=True, version_id=first_id)
        second = workbench.update(self.engine, scope, METRIC, method, 'train', 'operator', end - 900)['candidate']
        rows = {row['id']: row for row in workbench.library(self.engine)}
        self.assertEqual(rows[first_id]['status'], 'ready')
        self.assertEqual(rows[second['version']]['status'], 'trained')
        self.assertEqual(rows[first_id]['review_start'], end - 600)
        preview = workbench.replay(self.engine, scope, METRIC, method, end - 600, end, version_id=first_id)
        self.assertEqual(preview['version']['id'], first_id)
        self.assertGreater(len(self.scored(preview)), 0)
        config = workbench.update(self.engine, scope, METRIC, method, 'enable', 'operator', version_id=first_id)
        self.assertEqual(config['candidate']['version'], second['version'])
        self.assertEqual(config['active']['version'], first_id)
        with self.assertRaisesRegex(ValueError, '先验证'):
            workbench.update(self.engine, scope, METRIC, method, 'enable', 'operator', version_id=second['version'])
        with self.assertRaisesRegex(ValueError, '不可用于'):
            workbench.compatible_version(self.engine, self.public, METRIC, method, first_id)

    def test_reference_registry_preserves_holdout_scope(self):
        scope, method = self.public, 'shallow_tree'
        prepared = workbench.update(self.engine, scope, 'core', method, 'prepare', 'operator')
        self.assertEqual(prepared['fold'], scope.fold)
        self.assertTrue(workbench.version_path(prepared).is_file())
        self.assertEqual(workbench.library(self.engine)[0]['status'], 'ready')
        self.assertEqual(workbench.compatible_version(self.engine, scope, 'core', method, prepared['id'])['id'],
                         prepared['id'])
        with self.assertRaisesRegex(ValueError, '不可用于'):
            workbench.compatible_version(self.engine, self.simulated, 'core', method, prepared['id'])


if __name__ == '__main__':
    unittest.main()
