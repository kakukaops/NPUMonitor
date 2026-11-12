import copy
import tempfile
from pathlib import Path
import unittest
import numpy as np
from gpu_ml.models import build_model,GPUModel


def data(n=1200):
    rng=np.random.default_rng(17);rows=[]
    for i in range(n):
        z=np.sin(i/17)+rng.normal(0,.05)
        rows.append({'t':float(i*2),'values':{'gpu_temp':60+z,'power':250+20*z+rng.normal(0,.2),'sm_clock':1500+30*z+rng.normal(0,.5),'util':70+10*z+rng.normal(0,.2)}})
    return rows

class V2Tests(unittest.TestCase):
    def test_temporal_causal_alignment_and_spike(self):
        rows=data();m=build_model('uni_gpu_temp','temporal_mad');m.fit(rows[:800]);normal=m.predict(rows[800:])
        self.assertEqual(normal[0]['t'],rows[812]['t']);self.assertLess(np.mean([p['anomaly'] for p in normal]),.15)
        altered=copy.deepcopy(rows[800:]);altered[40]['values']['gpu_temp']+=20
        a=m.predict(altered);self.assertEqual(normal[:28],a[:28]);self.assertTrue(a[28]['anomaly'])
        self.assertEqual(a[28]['t'],altered[40]['t'])
    def test_no_windows_across_gaps_or_short_input(self):
        m=build_model('uni_gpu_temp','temporal_mad');rows=data();m.fit(rows)
        self.assertEqual(m.predict(rows[:12]),[])
        g=copy.deepcopy(rows[:30]);g[15]['t']+=1
        for p in m.predict(g):self.assertFalse(30<=p['t']<=54)
    def test_joint_detects_relationship_break_and_reference_not_forecast(self):
        rows=data();m=build_model('joint_gpu','joint_pca');m.fit(rows[:800]);sample=copy.deepcopy(rows[800:])
        self.assertLess(np.mean([p['anomaly'] for p in m.predict(sample)]),.15)
        for r in sample:r['values']['power']+=70
        result=m.predict(sample);self.assertGreater(np.mean([p['anomaly'] for p in result]),.95)
        self.assertEqual(result[0]['reference_kind'],'joint_reconstruction');self.assertIn('power',result[0]['contributions'])
    def test_artifact_roundtrip_and_algorithm_mismatch(self):
        rows=data()
        for template,algorithm in [('uni_gpu_temp','temporal_mad'),('joint_gpu','joint_pca')]:
            model=build_model(template,algorithm);model.fit(rows)
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'model';digest=model.save(p);loaded=GPUModel.load(p,digest)
                self.assertEqual(model.predict(rows[-50:]),loaded.predict(rows[-50:]))
        with self.assertRaises(ValueError):build_model('uni_gpu_temp','joint_pca')
        with self.assertRaises(ValueError):build_model('thermal','temporal_mad')
    def test_duplicate_and_insufficient_rejected(self):
        rows=data();rows[1]['t']=rows[0]['t']
        for template,algorithm in [('uni_gpu_temp','temporal_mad'),('joint_gpu','joint_pca')]:
            with self.assertRaises(ValueError):build_model(template,algorithm).fit(rows)
            with self.assertRaises(ValueError):build_model(template,algorithm).fit(data(50))
