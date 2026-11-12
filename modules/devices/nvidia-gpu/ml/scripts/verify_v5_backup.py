"""Run in monitor to freeze its snapshot; platform restore is run separately."""
import json,tempfile,time
from pathlib import Path
from gpu_ml.cli import request,restore,wait
s=request('/state');backup=request('/backups',{})
assert backup['remote_model_refs'] and 'remote weights' in backup['scope']
with tempfile.TemporaryDirectory(prefix='monitor-backup-v5-') as tmp:
 result=restore(Path('/data/backups')/(backup['id']+'.tar.gz'),Path(tmp)/'restored')
 assert result['schema']==1
ref=next(m for m in s['models'] if m.get('backend') and m['id']==next(t['active_model'] for t in s['tasks'] if t.get('scenario_id')=='thermal_relation' and t.get('scenario_profile')=='laboratory'))
Path('/data/evidence/v5-model-reference.json').write_text(json.dumps(ref))
t=next(t for t in s['tasks'] if t['id']==ref['task'])
fixture={'state':s,'series':request('/series/'+t['id']+'?start='+str(time.time()-900)+'&end='+str(time.time()))}
Path('/data/evidence/v5-ui-fixture.json').write_text(json.dumps(fixture))
out={'passed':True,'monitor_backup_restored':True,'remote_refs':len(backup['remote_model_refs']),'scope':backup['scope'],'recorded_at':time.time()}
Path('/data/evidence/v5-backup.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
