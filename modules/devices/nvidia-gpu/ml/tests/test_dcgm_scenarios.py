import copy
import tempfile
from pathlib import Path
import unittest
import numpy as np
from gpu_ml.pipeline import build_pipeline,load_artifact
from gpu_ml.dcgm_scenarios import CATALOG,template_name
from gpu_ml.simulation import healthy
from gpu_ml.settings import METRICS

def reference(n=1200,start=0,seed=11):
    ts=np.arange(start,start+n*2,2,dtype=float);v=healthy(ts,0,seed)
    return [{'t':float(t),'values':{k:float(x[i]) for k,x in v.items()}} for i,t in enumerate(ts)]

class DCGMScenarioTests(unittest.TestCase):
    def model(self,scene):
        spec=CATALOG['scenarios'][scene]
        m=build_pipeline(template_name(scene,'laboratory'),spec['algorithm']);m.fit(reference());return m
    def test_catalog_uses_only_existing_dcgm_fields(self):
        self.assertEqual(len(CATALOG['scenarios']),4)
        for spec in CATALOG['scenarios'].values():
            self.assertTrue(set(spec['required'])<=set(METRICS));self.assertNotIn('job_running',spec['required'])
            self.assertTrue(all(METRICS[k]['name'].startswith('DCGM_') for k in spec['required']))
    def test_conditional_relations_detect_deviations_and_holdout_normal(self):
        for scene in ('thermal_relation','power_clock_relation'):
            m=self.model(scene);rows=reference(300,4000,29);normal=m.predict(rows)
            self.assertLess(np.mean([p['anomaly'] for p in normal]),.12)
            bad=copy.deepcopy(rows)
            for r in bad:
                if scene=='thermal_relation':r['values']['gpu_temp']+=8;r['values']['memory_temp']+=7
                else:r['values']['power']+=70;r['values']['sm_clock']-=170
            results=m.predict(bad);self.assertGreater(np.mean([p['anomaly'] for p in results]),.95)
            self.assertEqual(results[0]['reference_kind'],'conditional_baseline');self.assertIn('residuals',results[0]['evidence'])
    def test_normal_high_load_and_outside_reference_are_not_forced_faults(self):
        m=self.model('thermal_relation');rows=reference(100,4000)
        for r in rows:
            u=96.;p=70+3.5*u
            r['values'].update(util=u,power=p,mem_util=.65*u,gpu_temp=30+.055*p+.1*u,memory_temp=37+.055*p+.12*u)
        points=m.predict(rows);self.assertTrue(points);self.assertLess(np.mean([p['anomaly'] for p in points]),.1)
        for r in rows:r['values']['util']=3.;r['values']['mem_util']=1.
        self.assertEqual(m.predict(rows),[]);self.assertEqual(m.detector.latest_quality(m.preprocessor.transform(rows)),'outside_reference')
    def test_sustained_thermal_and_clock_residuals(self):
        for scene in ('thermal_degradation','clock_degradation'):
            m=self.model(scene);rows=reference(250,4000,31);normal=m.predict(rows)
            self.assertLess(np.mean([p['anomaly'] for p in normal]),.15)
            bad=copy.deepcopy(rows)
            for i,r in enumerate(bad):
                if scene=='thermal_degradation':r['values']['gpu_temp']+=max(0,i-50)*.06;r['values']['memory_temp']+=max(0,i-50)*.05
                else:r['values']['sm_clock']-=max(0,i-50)*1.2
            out=m.predict(bad);self.assertTrue(any(p['anomaly'] for p in out[-60:]))
            self.assertIn('residual_slope_per_hour',out[-1]['evidence']);self.assertEqual(out[-1]['scenario']['profile'],'laboratory')
    def test_short_pulse_does_not_become_sustained_degradation(self):
        m=self.model('thermal_degradation');rows=reference(220,4000,32)
        rows[90]['values']['gpu_temp']+=20
        out=m.predict(rows);near=[p for p in out if rows[90]['t']<=p['t']<=rows[120]['t']]
        # Median and 5-95% clipping remove an isolated spike from the drift window.
        self.assertLess(sum(p['anomaly'] for p in near),len(near)*.2)
    def test_production_reference_length_is_enforced(self):
        for scene in CATALOG['scenarios']:
            m=build_pipeline(template_name(scene,'production'),CATALOG['scenarios'][scene]['algorithm'])
            with self.assertRaises(ValueError):m.fit(reference())
        rows=reference()
        for i,r in enumerate(rows):r['t']=i*700.
        m=build_pipeline(template_name('clock_degradation','production'),'dcgm_residual_trend');m.fit(rows)
        self.assertEqual(m.detector.trend_seconds,21600)
    def test_gaps_configuration_and_provenance_roundtrip(self):
        m=self.model('thermal_degradation');rows=reference(200,4000)
        for r in rows:r['values']['mem_clock']+=300
        self.assertEqual(m.predict(rows),[])
        rows=reference(200,4000);rows[100]['t']+=1
        points=m.predict(rows);self.assertFalse(any(rows[100]['t']<=p['t']<=rows[140]['t'] for p in points))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'artifact';digest=m.save(path)
            self.assertEqual(m.predict(reference(80,4000)),load_artifact(path,digest).predict(reference(80,4000)))
    def test_preprocessing_inverse_keeps_evidence_in_original_units(self):
        m=build_pipeline(template_name('thermal_relation','laboratory'),'dcgm_conditional',{'preprocessing':{'kind':'robust_scale'}});m.fit(reference())
        rows=reference(80,4000);points=m.predict(rows);p=points[-1]
        self.assertAlmostEqual(p['evidence']['residuals']['gpu_temp'],p['values']['gpu_temp']-p['expected']['gpu_temp'])

    def test_engine_rejects_laboratory_training_and_publish_to_real_entities(self):
        import threading
        from unittest.mock import Mock,patch
        from gpu_ml.engine import Engine
        from gpu_ml.store import Store
        from gpu_ml.settings import TEMPLATES
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');template=template_name('thermal_relation','laboratory')
            store.put('task','real',{'entity':'cluster|real-GPU','template':template,'scope':'real_unverified','enabled':True})
            record={'entity':'cluster|real-GPU','template':template,'source_type':'real_unverified','status':'validated','feature_schema':TEMPLATES[template]}
            store.put('model','bad-profile',record)
            engine=Engine.__new__(Engine);engine.store=store;engine.lock=threading.RLock();engine.load=Mock()
            with patch('gpu_ml.engine.SIMULATION',True):
                with self.assertRaises(ValueError):engine.queue_training('real','dcgm_conditional',100,3700,2)
                with self.assertRaises(ValueError):engine.publish('real','bad-profile','admin')
            engine.load.assert_not_called()
