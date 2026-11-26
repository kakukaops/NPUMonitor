from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gpu_ml.rule_board import GROUP_NAME, OWNER, RuleBoard, rule_catalog, rule_inputs


class RuleBoardTests(unittest.TestCase):
    @patch('gpu_ml.rule_board.SIMULATION', True)
    def test_catalog_and_threshold_replay(self):
        client = Mock()
        board = RuleBoard(client)
        result = board.board('synthetic')
        by_id = {rule['id']: rule for rule in result['rules']}
        self.assertEqual(set(by_id), set(rule_catalog()[1]))
        selected = by_id['os_sre.gpu_thermal']
        self.assertEqual(selected['state'], 'example')
        self.assertEqual(selected['for_seconds'], 60)
        self.assertIn('os_sre.thermal_margin_exhausted', by_id)
        detail = board.detail(None, 'synthetic', selected['id'])
        self.assertEqual(detail['threshold'], 90)
        self.assertEqual([field['field'] for field in detail['series']], selected['fields'])
        high = next(point['t'] for point in detail['series'][0]['points'] if point['value'] > detail['threshold'])
        self.assertEqual(detail['active_start'] - high, selected['for_seconds'])
        self.assertGreater(detail['active_end'], detail['active_start'])
        client.call.assert_not_called()

    def test_live_status_is_scoped_to_owned_rule_group_and_source(self):
        def fake_call(method, path):
            self.assertEqual(method, 'GET')
            if path.startswith('/busi-groups?'):
                return [{'id': 7, 'name': GROUP_NAME}]
            if path == '/busi-group/7/alert-rules':
                return [
                    {'id': 11, 'annotations': {'managed_by': OWNER, 'deployment_id': 'gpu-os-sre-master',
                                               'sre_rule_id': 'os_sre.gpu_thermal'}, 'disabled': 0},
                    {'id': 12, 'annotations': {'managed_by': OWNER, 'deployment_id': 'site-prod',
                                               'sre_rule_id': 'os_sre.gpu_thermal'}, 'disabled': 1},
                    {'id': 13, 'annotations': {'managed_by': 'other', 'deployment_id': 'gpu-os-sre-master',
                                               'sre_rule_id': 'os_sre.gpu_thermal'}, 'disabled': 0},
                ]
            if path.startswith('/alert-cur-events/list?bgid=7'):
                return {'list': [
                    {'id': 4, 'rule_id': 11, 'trigger_time': 1700000000, 'tags': ['UUID=sample-gpu']},
                    {'id': 5, 'rule_id': 13, 'trigger_time': 1700000000},
                ]}
            if path.startswith('/alert-his-events/list?bgid=7'):
                return {'list': [{'id': 3, 'rule_id': 11, 'trigger_time': 1699999800,
                                  'is_recovered': True, 'recover_time': 1699999900}]}
            self.fail(path)

        board = RuleBoard(SimpleNamespace(call=fake_call))
        sim = board.board('simulated')
        real = board.board('real_unverified')
        self.assertEqual(sim['status'], 'connected')
        self.assertEqual([event['id'] for event in sim['events']], ['4', '3'])
        self.assertEqual(real['events'], [])
        self.assertEqual(next(r for r in sim['rules'] if r['id'] == 'os_sre.gpu_thermal')['state'], 'active')
        self.assertEqual(next(r for r in real['rules'] if r['id'] == 'os_sre.gpu_thermal')['state'], 'paused')

    def test_current_device_input_filters_other_sources_and_partitions(self):
        def row(value, **labels):
            return {'metric': {'__name__': 'DCGM_FI_DEV_GPU_TEMP', 'UUID': 'a', **labels},
                    'values': [(1700000000, str(value))]}

        source = SimpleNamespace(query=lambda *_: [
            row(90, cluster_id='other', simulated='true'),
            row(91, cluster_id='target', simulated='true', GPU_I_ID='1'),
            row(92, cluster_id='target'),
            row(73, cluster_id='target', simulated='true'),
        ])
        device = {'uuid': 'a', 'cluster': 'target', 'source_type': 'simulated'}
        curves = rule_inputs(source, ['DCGM_FI_DEV_GPU_TEMP'], device, 1699999100, 1700000000)
        self.assertEqual(curves[0]['points'], [{'t': 1700000000, 'value': 73}])
