"""Fixture behavior tests. Integration still requires real Prometheus/Nightingale."""
from pathlib import Path
import sys
import tempfile
import unittest

LAB = Path('/app') if Path('/app/simulator.py').exists() else Path(__file__).resolve().parents[1] / 'lab'
sys.path.insert(0, str(LAB))
from simulator import Model
from receiver import Store


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.model = Model(clock=lambda: self.now)

    def body(self):
        status, body = self.model.snapshot()
        self.assertEqual(status, 200)
        return body

    def temperature(self, value):
        return any(line.startswith('DCGM_FI_DEV_GPU_TEMP{gpu="0"') and
                   line.endswith(' ' + str(value)) for line in self.body().splitlines())

    def test_normal_has_two_distinct_devices_and_no_fault(self):
        body = self.body()
        temps = [line for line in body.splitlines() if line.startswith('DCGM_FI_DEV_GPU_TEMP{')]
        self.assertEqual(len(temps), 2)
        self.assertIn('UUID="GPU-SIM-0000"', temps[0])
        self.assertIn('UUID="GPU-SIM-0001"', temps[1])
        self.assertTrue(self.temperature(55))
        self.assertIn('simulated="true"', body)

    def test_fault_isolated_to_one_gpu(self):
        self.model.select('hot')
        self.assertTrue(self.temperature(95))
        temp1 = [x for x in self.body().splitlines() if x.startswith('DCGM_FI_DEV_GPU_TEMP{gpu="1"')]
        self.assertTrue(temp1[0].endswith(' 56'))

    def test_transient_edges(self):
        self.model.select('transient')
        for second, value in [(9.999, 55), (10, 95), (19.999, 95), (20, 55)]:
            self.now = second
            self.assertTrue(self.temperature(value), second)

    def test_sustained_recovers_after_70_seconds(self):
        self.model.select('sustained')
        for second, value in [(0, 55), (10, 95), (79.999, 95), (80, 55)]:
            self.now = second
            self.assertTrue(self.temperature(value), second)

    def test_missing_differs_from_empty_and_scrape_failure(self):
        self.model.select('missing')
        self.assertNotIn('GPU-SIM-0001', self.body())
        self.assertIn('GPU-SIM-0000', self.body())
        self.model.select('empty')
        self.assertNotIn('GPU-SIM-', self.body())
        self.assertIn('gpu_simulator_info', self.body())
        self.model.select('scrape_error')
        self.assertEqual(self.model.snapshot()[0], 503)
        self.assertEqual(self.model.state()['scenario'], 'scrape_error')

    def test_counter_preserved_until_explicit_reset(self):
        self.model.select('ecc')
        self.assertEqual(self.model.ecc, 1)
        self.model.select('normal')
        self.assertEqual(self.model.ecc, 1)
        self.model.select('ecc')
        self.assertEqual(self.model.ecc, 2)
        self.model.select('counter_reset')
        self.assertEqual(self.model.ecc, 0)

    def test_invalid_input_is_not_a_valid_temperature(self):
        self.model.select('invalid')
        self.assertTrue(self.temperature('NaN'))
        self.model.select('normal')
        self.assertTrue(self.temperature(55))

    def test_invalid_scenario_does_not_change_state(self):
        for name in ['unknown', None, {}, []]:
            with self.assertRaises(ValueError):
                self.model.select(name)
        self.assertEqual(self.model.state()['generation'], 0)

    def test_xid_is_gauge_code(self):
        self.model.select('xid')
        body = self.body()
        self.assertIn('# TYPE DCGM_FI_DEV_XID_ERRORS gauge', body)
        self.assertTrue(any(x.startswith('DCGM_FI_DEV_XID_ERRORS{gpu="0"') and x.endswith(' 79')
                            for x in body.splitlines()))


class ReceiverTests(unittest.TestCase):
    def test_persistence_and_recent_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            store = Store(path)
            for index in range(105):
                store.append({'index': index})
            events = Store(path).recent()
            self.assertEqual(len(events), 100)
            self.assertEqual(events[0]['payload']['index'], 5)
            self.assertEqual(events[-1]['payload']['index'], 104)
            self.assertIn('received_at', events[0])

    def test_rotation_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            store = Store(path, max_bytes=120)
            store.append({'message': 'a' * 50})
            store.append({'message': 'b' * 50})
            self.assertTrue(path.with_suffix('.previous.jsonl').exists())
            self.assertEqual(store.recent()[0]['payload']['message'], 'b' * 50)


if __name__ == '__main__':
    unittest.main()
