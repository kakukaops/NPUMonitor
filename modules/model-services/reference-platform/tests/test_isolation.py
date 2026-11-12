"""Exercise the reusable runtime with no vendor plugin or monitoring application."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
import gpu_ml_runtime


class IsolationTests(unittest.TestCase):
    def test_generic_fit_score_and_roundtrip_without_device_packages(self):
        code = '''
import hashlib, math, sys, tempfile
from pathlib import Path
from gpu_ml_runtime.pipeline import build_pipeline, load_artifact
from gpu_ml_runtime.catalog import TEMPLATES
from gpu_ml_runtime.detectors import DETECTORS
assert not TEMPLATES and 'dcgm_conditional' not in DETECTORS
spec={'kind':'univariate','targets':['signal'],'features':[],
      'required':['signal'],'algorithms':['level_mad']}
rows=[{'t':float(i*2),'values':{'signal':10+math.sin(i*.17)}} for i in range(600)]
model=build_pipeline('neutral_signal','level_mad',spec=spec)
model.fit(rows)
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'model.joblib';digest=model.save(path)
    restored=load_artifact(path,digest)
    normal=restored.predict(rows[-60:])
    abnormal=[{'t':r['t'],'values':{'signal':r['values']['signal']+30}} for r in rows[-60:]]
    points=restored.predict(abnormal)
    assert len(points)==len(normal) and all(p['anomaly'] for p in points)
assert not any(n.split('.')[0] in ('gpu_ml','nvidia_gpu_ml') for n in sys.modules)
'''
        # A fresh process gets only the generic runtime import root.
        env={**os.environ,'PYTHONPATH':str(Path(gpu_ml_runtime.__file__).parents[1]),'MODEL_DEVICE_PLUGINS':''}
        subprocess.run([sys.executable,'-c',code],env=env,cwd='/tmp',check=True,capture_output=True,text=True)

    def test_model_service_image_has_no_monitor_control_plane(self):
        import importlib.util
        for name in ('gpu_ml.engine','gpu_ml.source','gpu_ml.nightingale','gpu_ml.store'):
            self.assertIsNone(importlib.util.find_spec(name),name)
