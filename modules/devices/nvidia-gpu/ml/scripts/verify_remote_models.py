"""Explicit simulated-GPU HTTP acceptance. Registers existing platform models; no production use."""
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from gpu_ml.cli import request,wait
from gpu_ml.baseline import PRIMARY_METRICS,reference_rows
from gpu_ml.model_backends.http import HttpModelBackend
from gpu_ml.model_backends.contracts import dataset_hash
from gpu_ml.settings import METRICS,TEMPLATES,DATA

state=request('/state')
assert state['simulation'],'Only explicit simulation is allowed'
backend=HttpModelBackend()
assert backend.url=='http://model-platform:9470','Only the known local reference platform is allowed'
uid='GPU-ML-SIM-0000';entity='gpu-ml-simulation|'+uid
services=request('/model-services')['services']
name='参考平台接入验证（同机）'
service=next((s for s in services if s['name']==name),None)
if not service:
    service=request('/model-services',{'name':name,'url':backend.url,'token':Path(backend.token_file).read_text().strip(),'timeout_seconds':12})
assert service['location']=='reference','Never label a same-host reference as a verified remote machine'
result={'scope':'simulated GPU; same-host independent HTTP reference; not customer platform or cross-machine verification','registered':[]}
for metric in PRIMARY_METRICS:
    task=next(t for t in state['tasks'] if t['entity']==entity and t['template']=='uni_'+metric and not t.get('deleted'))
    template=task['template'];rows=reference_rows(entity,metric,1794896400,1794900000,2)
    # Direct platform submission represents a model prepared outside the monitor's training workflow.
    body={'training_spec':{'template':template,'algorithm':'temporal_mad','feature_schema':TEMPLATES[template],
        'entity':entity,'source_type':'simulated','input_contract':{metric:{'metric_id':METRICS[metric]['metric_id'],'unit':METRICS[metric]['unit']}},
        'source_window':{'start':rows[0]['t'],'end':rows[-1]['t']},'pipeline':{}},'dataset':{'rows':rows,'sha256':dataset_hash(rows)}}
    ident='remote-registration-demo-v1-'+metric
    backend.submit(ident,'fit',body)
    deadline=time.time()+55
    while time.time()<deadline:
        job=backend.job(ident)
        if job['status'] in ('completed','failed','cancelled'):break
        time.sleep(.2)
    assert job['status']=='completed',job.get('error',job['status'])
    model=job['result'];deployed=backend.deploy(model['model_ref'],model['platform_id'])
    catalog=request('/model-services/'+service['id']+'/models?'+urlencode({'task':task['id']}))
    assert any(m['model_ref']==model['model_ref'] for m in catalog['models'])
    before=request('/state');before_task=next(t for t in before['tasks'] if t['id']==task['id'])
    imported=request('/remote-models/register',{'service_id':service['id'],'task':task['id'],'model_ref':model['model_ref'],'deployment_ref':deployed['deployment_ref']})
    registered=imported['model'];assert registered['external_registration'] and 'snapshot' not in registered and 'artifact' not in registered
    after=request('/state');assert next(t for t in after['tasks'] if t['id']==task['id'])['active_model']==before_task['active_model']
    if metric=='memory_temp':
        request('/tasks/'+task['id']+'/publish',{'model':registered['id']})
        live=wait(lambda s:any(v['id']==task['id'] and v.get('model_id')==registered['id'] and v['quality']=='valid' for v in s['states']),'Imported deployment online API scoring',timeout=55)
        assert next(t for t in live['tasks'] if t['id']==task['id'])['active_model']==registered['id']
    result['registered'].append({'metric':metric,'model_id':registered['id'],'existing_deployment_reused':True,'trial_points':registered['connection_validation']['scored_points'],'location':registered['execution_location']})
# Viewer cannot configure services or register models.
for path,body in [('/model-services',{}),('/remote-models/register',{})]:
    try:request(path,body,role='viewer');raise AssertionError('Viewer could mutate remote model configuration')
    except HTTPError as exc:assert exc.code==403
result.update(passed=True,viewer_denied=True,credentials_returned=False,online_import_verified='memory_temp')
folder=DATA/'evidence';folder.mkdir(exist_ok=True);(folder/'remote-models.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
