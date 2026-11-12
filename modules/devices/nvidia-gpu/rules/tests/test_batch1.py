"""Check streaming fixture timing and isolation, beyond expression-only tests."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
LAB=Path('/app') if Path('/app/batch1_simulator.py').exists() else Path(__file__).resolve().parents[1]/'lab'
sys.path.insert(0,str(LAB))
from batch1_simulator import BatchModel, FIELDS
from simulator import Model
from batch1_notifications import interpret


class BatchFixtures(unittest.TestCase):
    def test_stale_has_old_explicit_timestamp_and_distinct_replica(self):
        with patch('batch1_simulator.time.time',return_value=1000):
            m=BatchModel();m.select('stale');status,body=m.snapshot()
        self.assertEqual(status,200)
        samples=[s for s in body.splitlines() if s.startswith(FIELDS[2]+'{')]
        self.assertEqual(len(samples),2)
        self.assertTrue(samples[0].endswith(' 0 880000'))
        self.assertIn('fixture_age="old"',samples[0])
        self.assertNotIn('fixture_age',samples[1])

    def test_transient_invalid_is_sampled_then_clears_without_scenario_reset(self):
        with patch('batch1_simulator.time.time',return_value=1000):
            m=BatchModel();m.select('transient_invalid')
        with patch('batch1_simulator.time.time',return_value=1014):
            self.assertIn(' NaN\n',m.snapshot()[1])
        with patch('batch1_simulator.time.time',return_value=1015):
            self.assertNotIn(' NaN',m.snapshot()[1])

    def test_batch_scenarios_do_not_change_original_simulator(self):
        old=Model();old.select('hot')
        m=BatchModel();m.select('sram')
        self.assertEqual(old.state()['scenario'],'hot')
        self.assertNotIn('GPU-SIM-',m.snapshot()[1])
        self.assertNotIn('GPU-BATCH1-',old.snapshot()[1])

    def test_duplicate_has_distinct_labels_and_single_gpu_scope(self):
        m=BatchModel();m.select('duplicate');body=m.snapshot()[1]
        samples=[s for s in body.splitlines() if s.startswith(FIELDS[2]+'{')]
        self.assertEqual(len(samples),3)
        self.assertEqual(sum('replica="second"' in s for s in samples),1)
        self.assertIn('UUID="GPU-BATCH1-0000"',next(s for s in samples if 'replica=' in s))


class NotificationContract(unittest.TestCase):
    def test_raw_hardware_recovery_is_unverified_exit(self):
        for rule in ['sram_threshold_exceeded','row_remap_failed']:
            row=interpret([{'tags':['rule_id=batch1_'+rule], 'is_recovered':True}])[0]
            self.assertEqual(row['state'],'condition_exited')
            self.assertEqual(row['end_reason'],'unverified_condition_exit')
            self.assertFalse(row['hardware_recovery_confirmed'])
            self.assertIn('不能据此判断硬件修复',row['message'])

    def test_quality_exit_does_not_claim_hardware_recovery(self):
        row=interpret([{'tags_map':{'rule_id':'batch1_required_field_missing'},'is_recovered':True}])[0]
        self.assertEqual(row['end_reason'],'quality_condition_exit')
        self.assertFalse(row['hardware_recovery_confirmed'])

    def test_original_demo_payload_is_not_reinterpreted(self):
        self.assertEqual(interpret([{'tags':['rule_id=gpu_lab_temperature'],'is_recovered':True}]),[])


if __name__=='__main__':unittest.main()
