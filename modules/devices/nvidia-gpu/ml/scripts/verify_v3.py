"""Run inside service via stdin. Real HTTP + source history; simulated GPU only."""
import json,time
from pathlib import Path
from urllib.error import HTTPError
from gpu_ml.cli import request,wait

out={'scope':'v3 pipeline / actual Prometheus and Nightingale / simulated GPU','production_admitted':False,'cases':[]}
s=request('/state');assert s['simulation']
request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
entity='gpu-ml-simulation|GPU-ML-SIM-0000'
request('/policies',{'entities':[entity],'metrics':['gpu_temp'],'kind':'univariate'})
request('/policies',{'entities':[entity],'metrics':['gpu_temp','power','sm_clock','util'],'kind':'multivariate'})
s=request('/state');temp=next(t for t in s['tasks'] if t['entity']==entity and t['template']=='uni_gpu_temp');joint=next(t for t in s['tasks'] if t['entity']==entity and t.get('policy_kind')=='multivariate')
previous_models={t['id']:t['active_model'] for t in s['tasks']}

def job_done(job):
 state=wait(lambda s:any(j['id']==job['id'] and j['status'] in ('completed','failed') for j in s['jobs']),'job '+job['id'],120)
 done=next(j for j in state['jobs'] if j['id']==job['id']);assert done['status']=='completed',done
 return done

end=time.time()-5
job=request('/training-jobs',{'task':temp['id'],'algorithm':'temporal_mad','start':end-1800,'end':end,'step':2,'pipeline':{'preprocessing':{'kind':'robust_scale'},'detector':{'window':12}}})
done=job_done(job);s=request('/state');base=next(m for m in s['models'] if m['id']==done['model_id'])
assert base['pipeline']['schema']==3
assert next(t for t in s['tasks'] if t['id']==temp['id'])['active_model']==previous_models[temp['id']]
post=request('/models/'+base['id']+'/postprocess',{'factor':1.5})
assert post['pipeline']['detector_id']==base['pipeline']['detector_id']
assert post['pipeline']['preprocessor_id']==base['pipeline']['preprocessor_id']
assert post['pipeline']['calibrator_id']==base['pipeline']['calibrator_id']
assert post['pipeline']['decision_id']!=base['pipeline']['decision_id']
assert post['report']['detector_retrained'] is False
recal=request('/models/'+base['id']+'/postprocess',{'calibration':{'component_quantile':.995,'threshold_quantile':.995},'factor':1.5})
assert recal['pipeline']['calibrator_id']!=base['pipeline']['calibrator_id']
assert recal['pipeline']['detector_id']==base['pipeline']['detector_id']
out['cases'].append({'name':'train-and-independent-postprocess-versions','passed':True,'base':base['id'],'threshold_version':post['id'],'recalibration_version':recal['id'],'samples':base['report']['samples']})
try:request('/models/'+base['id']+'/postprocess',{'factor':1.2},role='viewer');raise AssertionError('viewer write')
except HTTPError as exc:assert exc.code==403
try:request('/models/'+base['id']+'/postprocess',{'calibration':{'component_quantile':.2,'threshold_quantile':.99}});raise AssertionError('bad quantile')
except HTTPError as exc:assert exc.code==400
assert post['status']=='validated',post['report']
request('/tasks/'+temp['id']+'/publish',{'model':post['id']})
s=wait(lambda s:any(x['id']==temp['id'] and x['quality']=='valid' and x.get('model_id')==post['id'] for x in s['states']),'v3 online',60)
series=request('/series/'+temp['id']+'?start='+str(time.time()-120)+'&end='+str(time.time()))
p=series['points'][-1];assert p['pipeline_id']==post['pipeline']['pipeline_id'] and p['raw_score'] is not None
assert p['capabilities']['reference_kind']=='causal_forecast' and 20<p['expected']['gpu_temp']<100
end=time.time()-4;start=end-300
replay=job_done(request('/replays',{'task':temp['id'],'model':post['id'],'start':start,'end':end,'step':2,'labels':[{'start':start,'end':end,'kind':'normal_change'}]}))
r=request('/replays/'+replay['id']);assert r['evaluation']['normal_labelled_points']>0 and r['evaluation']['labelled_point_recall'] is None
out['cases'].append({'name':'online-units-provenance-labelled-replay','passed':True,'scored_points':r['evaluation']['scored_points'],'normal_labelled_alert_rate':r['evaluation']['normal_labelled_alert_rate']})
# Comparison is explicitly not an automatic selection or publication operation.
end=time.time()-5
comp=job_done(request('/comparisons',{'task':joint['id'],'algorithms':['joint_pca','joint_iforest'],'start':end-1800,'end':end,'step':2,'pipeline':{'preprocessing':{'kind':'robust_scale'}}}))
comparison=request('/comparisons/'+comp['id']);assert comparison['automatic_winner'] is None
candidates=comparison['candidates'];assert all(c['status']!='failed' for c in candidates),candidates
assert len({c['dataset_sha256'] for c in candidates})==1
assert len({json.dumps(c['report']['partitions'],sort_keys=True) for c in candidates})==1
assert next(t for t in request('/state')['tasks'] if t['id']==joint['id'])['active_model']==previous_models[joint['id']]
score_only=next(c for c in candidates if c['algorithm']=='joint_iforest')
end=time.time()-4
replay=job_done(request('/replays',{'task':joint['id'],'model':score_only['model'],'start':end-120,'end':end,'step':2}))
r=request('/replays/'+replay['id']);assert r['points'] and all(p['expected']=={} and p['bounds']=={} for p in r['points'])
assert r['capabilities']['reference_kind']=='none' and r['evaluation']['normal_labelled_alert_rate'] is None
out['cases'].append({'name':'same-snapshot-candidate-comparison-and-score-only','passed':True,'comparison':comp['id'],'models':[c['model'] for c in candidates]})
# Manually created ensemble preserves members and refuses incompatible versions.
ensemble=request('/ensembles',{'task':joint['id'],'models':[c['model'] for c in candidates]})
assert ensemble['status']=='validated',ensemble['report']
assert ensemble['pipeline']['kind']=='calibrated_max_ensemble'
assert next(t for t in request('/state')['tasks'] if t['id']==joint['id'])['active_model']==previous_models[joint['id']]
try:request('/ensembles',{'task':joint['id'],'models':[candidates[0]['model'],base['id']]});raise AssertionError('incompatible ensemble allowed')
except HTTPError as exc:assert exc.code==400
end=time.time()-4
job=job_done(request('/replays',{'task':joint['id'],'model':ensemble['id'],'start':end-120,'end':end,'step':2}))
result=request('/replays/'+job['id']);assert result['points'] and all(p['reference_kind']=='none' for p in result['points'])
post_ensemble=request('/models/'+ensemble['id']+'/postprocess',{'factor':1.2})
assert post_ensemble['pipeline']['members']==ensemble['pipeline']['members']
request('/tasks/'+joint['id']+'/publish',{'model':post_ensemble['id']})
wait(lambda s:any(x['id']==joint['id'] and x['quality']=='valid' and x.get('model_id')==post_ensemble['id'] for x in s['states']),'ensemble online',60)
request('/tasks/'+joint['id']+'/rollback',{})
assert next(t for t in request('/state')['tasks'] if t['id']==joint['id'])['active_model']==previous_models[joint['id']]
out['cases'].append({'name':'same-source-frozen-ensemble-and-independent-threshold','passed':True,'ensemble':ensemble['id'],'postprocess':post_ensemble['id']})
# Shadow isolated from primary, including score-only outputs.
request('/tasks/'+joint['id']+'/shadow',{'model':score_only['model']})
wait(lambda s:any(x['id']==joint['id'] and x.get('model')==score_only['model'] for x in s['shadow']),'score-only shadow',60)
assert next(t for t in request('/state')['tasks'] if t['id']==joint['id'])['active_model']==previous_models[joint['id']]
request('/tasks/'+joint['id']+'/shadow',{'model':None})
out['cases'].append({'name':'score-only-shadow-does-not-switch-primary','passed':True})
bindings=request('/integrations/nightingale/sync',{});rid=next(b['rule_id'] for b in bindings if b['id']==temp['id'])
try:
 request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'temperature_spike'})
 s=wait(lambda s:any(x['id']==temp['id'] and x.get('active') and x.get('pipeline_id')==post['pipeline']['pipeline_id'] for x in s['states']) and any(e['rule_id']==rid for e in s['nightingale'].get('events',[])),'v3 native event',90)
 event=next(e for e in s['nightingale']['events'] if e['rule_id']==rid)
 out['cases'].append({'name':'v3-native-nightingale-event','passed':True,'event_id':event['id'],'rule_id':rid,'hash':event['hash']})
finally:request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
wait(lambda s:any(x['id']==temp['id'] and x['quality']=='valid' and not x.get('active') for x in s['states']) and not any(e['rule_id']==rid for e in s['nightingale'].get('events',[])),'fresh normal recovery',120)
# Restore the preceding online version and republish to verify both artifact generations.
if previous_models[temp['id']]:
 request('/tasks/'+temp['id']+'/rollback',{})
 assert next(t for t in request('/state')['tasks'] if t['id']==temp['id'])['active_model']==previous_models[temp['id']]
 request('/tasks/'+temp['id']+'/publish',{'model':post['id']})
out['cases'].append({'name':'online-version-rollback-and-v3-publish','passed':True})
request('/tasks/'+joint['id']+'/publish',{'model':post_ensemble['id']})
out.update(passed=True,recorded_at=time.time())
Path('/data/evidence/v3.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
