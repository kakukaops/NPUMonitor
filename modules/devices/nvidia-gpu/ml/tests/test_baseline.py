"""Data eligibility and configurable lifecycle tests runnable without the numerical stack."""
import math
from pathlib import Path
import tempfile
import unittest

from accelerator_monitoring.store import Store
from gpu_ml.baseline import diagnostics, sample_count, PRIMARY_METRICS


class BaselineTests(unittest.TestCase):
    def rows(self):
        return [{'t':float(i*2),'values':{'util':0. if i%10 else 5.+i%7}} for i in range(500)]

    def test_legal_idle_zero_is_not_missing_and_semantic_gate(self):
        report=diagnostics(self.rows(),'util')
        self.assertEqual(report['samples'],500)
        self.assertEqual(report['zero_fraction'],.9)
        self.assertTrue(report['warnings'])
        self.assertEqual(report['gap_pairs'],0)
        with self.assertRaises(ValueError):diagnostics(self.rows(),'gpu_limit')
        with self.assertRaises(ValueError):diagnostics([{'t':i*2.,'values':{'util':0.}} for i in range(500)],'util')

    def test_source_time_gaps_duplicates_and_invalid_numbers(self):
        rows=self.rows();rows[200]['t']+=.6
        self.assertGreater(diagnostics(rows,'util')['gap_pairs'],0)
        rows=self.rows();rows[200]['t']=rows[199]['t']
        with self.assertRaises(ValueError):diagnostics(rows,'util')
        rows=self.rows();rows[-1]['values']['util']=math.nan
        with self.assertRaises(ValueError):diagnostics(rows,'util')
        for invalid in (True,0,31,3.5):
            with self.assertRaises(ValueError):sample_count(invalid)

    def test_confirmation_revision_unknown_and_evidence_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.sqlite')
            def point(t,anomaly,revision=1):
                return {'t':float(t),'model':'m','score':2. if anomaly else 0.,'threshold':1.,'anomaly':anomaly,
                        'decision_config_revision':revision,'calibrated_components':{'util:innovation':.1,'util:level':2.},
                        'expected':{'util':50.},'bounds':{'util':[40.,60.]},'values':{'util':55.}}
            kwargs={'confirmation_samples':2,'recovery_samples':4}
            self.assertFalse(store.apply('task',point(2,True),**kwargs)['active'])
            self.assertTrue(store.apply('task',point(4,True),**kwargs)['active'])
            held=store.apply('task',quality='missing',**kwargs)
            self.assertTrue(held['active']);self.assertEqual(held['pending'],0)
            for t in (6,8,10):self.assertTrue(store.apply('task',point(t,False),**kwargs)['active'])
            # Repeated sample does not advance recovery; parameter revision restarts it.
            self.assertEqual(store.apply('task',point(10,False),**kwargs)['clear_count'],3)
            self.assertTrue(store.apply('task',point(12,False,2),**kwargs)['active'])
            self.assertEqual(store.get('state','task')['clear_count'],1)
            for t in (14,16):self.assertTrue(store.apply('task',point(t,False,2),**kwargs)['active'])
            self.assertFalse(store.apply('task',point(18,False,2),**kwargs)['active'])
            latest=store.get('state','task')
            self.assertEqual(latest['calibrated_components']['util:level'],2.)
            self.assertEqual(latest['values']['util'],55.)
            self.assertEqual(len(store.history('task',0,20)),9)

if __name__=='__main__':unittest.main()
