"""Run inside the monitor; read-only compatibility checks, no Store initialization."""
import json, math, time
from pathlib import Path
from urllib.request import urlopen
import os
from accelerator_integrations.nightingale import NightingaleClient
from accelerator_integrations.prometheus import PrometheusClient
from gpu_ml import __version__
from gpu_ml.cli import request
from gpu_ml.pipeline import load_artifact
from gpu_ml.settings import DATA
from gpu_ml.model_backends.http import HttpModelBackend

s=request('/state');backend=HttpModelBackend();local=0;remote=0
assert PrometheusClient(os.environ['PROMETHEUS_URL']).query('up')
assert NightingaleClient(os.environ['NIGHTINGALE_URL'],os.environ['GPU_ML_N9E_TOKEN_FILE']).call('GET','/busi-groups')
for record in s['models']:
    if record.get('backend'):continue
    load_artifact(DATA/'models'/record['artifact'],record['sha256']);local+=1
for task in s['tasks']:
    if not task.get('active_model'):continue
    record=next(m for m in s['models'] if m['id']==task['active_model'])
    if record.get('backend'):
        rows=json.loads((DATA/'snapshots'/record['snapshot']).read_text())
        batch=backend.predict(record['backend'],rows,1.)
        assert batch.quality=='valid' and batch.points
        assert all(math.isfinite(p['score']) for p in batch.points);remote+=1
    fixture={'state':s,'series':request('/series/'+task['id']+'?start='+str(time.time()-900)+'&end='+str(time.time()))}
    Path('/data/evidence/layout-ui-fixture.json').write_text(json.dumps(fixture))
with urlopen('http://localhost:9460/ready',timeout=10) as response:assert response.status==200
out={'passed':True,'version':__version__,'legacy_models_loaded':local,'active_remote_models_scored':remote,
     'ready':True,'shared_integrations':True,'fixture':'layout-ui-fixture.json'}
Path('/data/evidence/layout-runtime.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
