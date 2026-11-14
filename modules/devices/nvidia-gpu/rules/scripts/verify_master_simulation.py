import json,time
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[5];P=ROOT/'.local/gpu-os-sre-master';TOKEN=(P/'admin-token').read_text().strip();REPORT={'scope':'independent new-stack real Prometheus and runtime; no shared Nightingale mutations','cases':[]}
def api(port,path,body=None):
 req=Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
 with urlopen(req,timeout=30) as r:return json.load(r)
def wait(f,label,timeout=45):
 end=time.time()+timeout
 while time.time()<end:
  if f():print('PASS:',label,flush=True);REPORT['cases'].append({'case':label,'passed':True});return
  time.sleep(1)
 raise AssertionError(label)
def scenario(name,**opts):api(19477,'/control',{'scenario':name,**opts})
def states():return api(19476,'/state')['states']
def active(key,uid='GPU-CONTRACT-0000'):return next((s for s in states() if s['rule_id']=='os_sre.'+key and s['identity'].get('UUID')==uid and s['active']),None)
original=(P/'config.json').read_bytes()
try:
 cfg=json.loads(original);cfg['rule_overrides']={k:{'for_seconds':4} for k in ('os_sre.remap_resource_exhausted','os_sre.thermal_margin_exhausted','os_sre.fabric_manager_error','os_sre.ecc_change_pending','os_sre.master_field_missing','os_sre.master_input_invalid','os_sre.gpu_link_down')}
 (P/'config.json').write_text(json.dumps(cfg));(P/'config.json').chmod(0o600)
 import subprocess,os
 env=dict(os.environ,PYTHONPATH=str(ROOT/'modules/devices/nvidia-gpu/rules/runtime/src'))
 subprocess.run(['python','-m','npumonitor_rules.cli','compile','--config',str(P/'config.json'),'--output',str(P/'bundle.json')],check=True,env=env,stdout=subprocess.DEVNULL)
 gen=api(19476,'/status')['state']['generation'];api(19476,'/admin/activate',{'expected_generation':gen,'reason':'isolated new profile acceptance with explicit shorter confirmation only'})
 scenario('baseline');wait(lambda:api(19476,'/status')['ready'],'88-field runtime ready')
 scenario('resource_busy');time.sleep(8);assert not any(s['active'] for s in states() if s['rule_id'].startswith('os_sre.') and s['identity'].get('UUID')=='GPU-CONTRACT-0000');REPORT['cases'].append({'case':'high GPU/SM activity alone is not a fault','passed':True});print('PASS: high activity is not a fault',flush=True)
 scenario('memory_capacity_high');time.sleep(7);assert not any(s['active'] for s in states() if s['identity'].get('UUID')=='GPU-CONTRACT-0000');REPORT['cases'].append({'case':'high framebuffer occupancy alone is not a fault','passed':True});print('PASS: high framebuffer occupancy is not a fault',flush=True)
 for scene,key in [('inforom_invalid','inforom_invalid'),('memory_unrepairable','memory_unrepairable'),('recovery_required','recovery_required'),('remap_exhausted','remap_resource_exhausted'),('thermal_margin','thermal_margin_exhausted'),('ecc_pending','ecc_change_pending'),('fabric_error','fabric_manager_error')]:
  scenario(scene);wait(lambda key=key:active(key),scene+' firing');assert not active(key,'GPU-CONTRACT-0001');scenario('baseline');wait(lambda key=key:not active(key),scene+' valid clear')
 scenario('nvlink_inactive');wait(lambda:active('gpu_link_down'),'NVLink inactive firing');scenario('nvlink_sleep');time.sleep(7);assert active('gpu_link_down');REPORT['cases'].append({'case':'SLEEP does not declare traffic-ready recovery','passed':True});scenario('baseline');wait(lambda:not active('gpu_link_down'),'NVLink ACTIVE verified clear')
 scenario('baseline',omit=[{'metric':'DCGM_FI_DEV_FB_USED','identity':{'UUID':'GPU-CONTRACT-0000'}}]);wait(lambda:active('master_field_missing'),'new resource field missing detected');scenario('baseline');wait(lambda:not active('master_field_missing'),'resource field restored')
 REPORT['passed']=True
finally:
 scenario('baseline');(P/'config.json').write_bytes(original);(P/'config.json').chmod(0o600)
 import subprocess,os
 env=dict(os.environ,PYTHONPATH=str(ROOT/'modules/devices/nvidia-gpu/rules/runtime/src'))
 subprocess.run(['python','-m','npumonitor_rules.cli','compile','--config',str(P/'config.json'),'--output',str(P/'bundle.json')],check=True,env=env,stdout=subprocess.DEVNULL)
 gen=api(19476,'/status')['state']['generation'];api(19476,'/admin/activate',{'expected_generation':gen,'reason':'restore master profile declared default confirmation after acceptance'})
 path=ROOT/'modules/devices/nvidia-gpu/rules/runtime/evidence/master-stage-acceptance.json';path.write_text(json.dumps(REPORT,ensure_ascii=False,indent=2)+'\n')
