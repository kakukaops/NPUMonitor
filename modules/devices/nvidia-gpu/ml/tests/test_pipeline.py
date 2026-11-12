import copy
import tempfile
from pathlib import Path
import unittest
import numpy as np
from gpu_ml.pipeline import build_pipeline,load_artifact,StrictPreprocessor,QuantileCalibrator,CalibratedMaxEnsemble
from gpu_ml.evaluation import summarize,validate_labels
from test_v2 import data

class PipelineTests(unittest.TestCase):
    def fit(self,algorithm='temporal_mad',config=None):
        template='joint_gpu' if algorithm.startswith('joint_') else 'uni_gpu_temp'
        model=build_pipeline(template,algorithm,config);model.fit(data());return model
    def test_time_split_and_train_only_fit_no_future_leak(self):
        rows=data();model=self.fit();altered=copy.deepcopy(rows)
        for r in altered[1080:]:r['values']['gpu_temp']+=1000
        other=build_pipeline('uni_gpu_temp','temporal_mad');other.fit(altered)
        np.testing.assert_array_equal(model.detector.regression.coef_,other.detector.regression.coef_)
        self.assertEqual(model.calibrator.scales,other.calibrator.scales)
        self.assertEqual(model.policy.threshold,other.policy.threshold)
        partitions=list(model.report['partitions'].values())
        for a,b in zip(partitions,partitions[1:]):self.assertLess(a['end'],b['start'])
        self.assertIsNone(model.report['test']['normal_labelled_alert_rate'])
    def test_preprocessing_inverse_and_causal_prefix(self):
        model=self.fit(config={'preprocessing':{'kind':'robust_scale'}})
        rows=data()[900:];a=model.predict(rows[:60]);b=model.predict(rows)
        self.assertEqual(a,b[:len(a)])
        p=a[-1];self.assertEqual(p['values'],rows[59]['values'])
        self.assertGreater(p['expected']['gpu_temp'],50);self.assertLess(p['expected']['gpu_temp'],70)
        self.assertEqual(p['reference_kind'],'causal_forecast')
    def test_no_interpolation_and_strict_source_times(self):
        with self.assertRaises(ValueError):StrictPreprocessor(['gpu_temp'],{'kind':'interpolate'})
        model=self.fit();rows=data()[:40];rows[20]['t']+=1
        points=model.predict(rows)
        self.assertFalse(any(40<=p['t']<=64 for p in points))
        rows=data()[:40];rows[3]['t']=rows[2]['t']
        with self.assertRaises(ValueError):model.predict(rows)
        rows=data()[:40];rows[3]['values']['gpu_temp']=float('nan')
        with self.assertRaises(ValueError):model.predict(rows)
    def test_threshold_revision_without_detector_refit(self):
        model=self.fit();rows=data();before=model.predict(rows[-100:])
        clone=model.reconfigure(rows,factor=1.5);after=clone.predict(rows[-100:])
        self.assertEqual(model.detector_id,clone.detector_id);self.assertEqual(model.preprocessor_id,clone.preprocessor_id)
        self.assertEqual(model.calibrator_id,clone.calibrator_id);self.assertNotEqual(model.decision_id,clone.decision_id)
        self.assertNotEqual(model.pipeline_id,clone.pipeline_id)
        self.assertEqual([p['score'] for p in before],[p['score'] for p in after])
        self.assertAlmostEqual(after[0]['threshold'],before[0]['threshold']*1.5)
        np.testing.assert_array_equal(model.detector.regression.coef_,clone.detector.regression.coef_)
        self.assertEqual(model.policy.factor,1.)
    def test_recalibration_separate_and_bad_config_rejected(self):
        model=self.fit();clone=model.reconfigure(data(),calibration={'component_quantile':.95,'threshold_quantile':.99})
        self.assertEqual(model.detector_id,clone.detector_id);self.assertNotEqual(model.calibrator_id,clone.calibrator_id)
        self.assertEqual(model.preprocessor.centers,clone.preprocessor.centers)
        with self.assertRaises(ValueError):QuantileCalibrator({'component_quantile':float('nan'),'threshold_quantile':.99})
        with self.assertRaises(ValueError):build_pipeline('uni_gpu_temp','temporal_mad',{'detector':{'window':True}})
    def test_score_only_capability_and_save_load(self):
        for algorithm in ('joint_iforest','level_mad','joint_pca'):
            model=self.fit(algorithm);points=model.predict(data()[-50:]);self.assertTrue(points)
            if algorithm!='joint_pca':
                self.assertEqual(model.capabilities['reference_kind'],'none');self.assertEqual(points[0]['expected'],{});self.assertEqual(points[0]['bounds'],{})
            self.assertIn('raw_components',points[0]);self.assertIn('calibrated_score',points[0]);self.assertFalse(model.capabilities['online_update'])
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'artifact';digest=model.save(path)
                self.assertEqual(points,load_artifact(path,digest).predict(data()[-50:]))
                path.write_bytes(path.read_bytes()+b'x')
                with self.assertRaises(ValueError):load_artifact(path,digest)
    def test_frozen_ensemble_threshold_ratios_and_roundtrip(self):
        a=self.fit('joint_pca');b=self.fit('joint_iforest');rows=data()[-50:]
        ensemble=CalibratedMaxEnsemble([a,b],['a','b']);points=ensemble.predict(rows)
        pa=a.predict(rows);pb=b.predict(rows)
        self.assertEqual(points[0]['score'],max(pa[0]['score']/pa[0]['threshold'],pb[0]['score']/pb[0]['threshold']))
        self.assertEqual(points[0]['expected'],{});self.assertEqual(points[0]['reference_kind'],'none')
        changed=ensemble.reconfigure(data(),factor=1.5)
        self.assertEqual(changed.predict(rows)[0]['score'],points[0]['score']);self.assertEqual(changed.predict(rows)[0]['threshold'],1.5)
        with self.assertRaises(ValueError):ensemble.reconfigure(data(),calibration={})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ensemble';digest=ensemble.save(path)
            self.assertEqual(points,load_artifact(path,digest).predict(rows))
        self.assertEqual(a.predict(rows),pa)

    def test_labelled_evaluation_does_not_label_unknown_as_normal(self):
        rows=[{'t':float(i*2)} for i in range(10)]
        points=[{'t':r['t'],'anomaly':r['t'] in (4.,6.,14.)} for r in rows]
        report=summarize(points,rows)
        self.assertIsNone(report['normal_labelled_alert_rate']);self.assertIsNone(report['labelled_point_recall'])
        labels=validate_labels([{'start':2,'end':8,'kind':'fault'},{'start':10,'end':18,'kind':'normal_change'}],0,20)
        report=summarize(points,rows,labels)
        self.assertAlmostEqual(report['labelled_point_recall'],2/3)
        self.assertAlmostEqual(report['normal_labelled_alert_rate'],1/4)
        self.assertEqual(report['fault_intervals'][0]['first_detection_delay_seconds'],2.)
        with self.assertRaises(ValueError):validate_labels(labels+[{'start':3,'end':5,'kind':'unconfirmed'}],0,20)
