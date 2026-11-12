"""Local administrative operations and real Prometheus/Nightingale acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .settings import DATA

BASE='http://127.0.0.1:9460/api/gpu-ml/v1'


def request(path,body=None,method=None,role='admin',headers=None):
    token=Path(os.environ['GPU_ML_'+role.upper()+'_TOKEN_FILE']).read_text().strip()
    req=Request(BASE+path,data=None if body is None else json.dumps(body).encode(),method=method or ('POST' if body is not None else 'GET'),
                headers={'Content-Type':'application/json','Authorization':'Bearer '+token,**(headers or {})})
    with urlopen(req,timeout=30) as response:return json.load(response)


def wait(predicate,label,timeout=55):
    deadline=time.time()+timeout
    while time.time()<deadline:
        state=request('/state')
        if predicate(state):return state
        time.sleep(2)
    raise AssertionError('等待超时: '+label)


def verify():
    start=time.time();result={'scope':'simulated-GPU / real existing Prometheus and Nightingale','production_admitted':False,'cases':[]}
    initial=request('/state')
    if not initial['simulation']:raise ValueError('verify仅允许显式模拟预览环境')
    request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
    wait(lambda s:any(e['uuid']=='GPU-ML-SIM-0000' and e['fresh'] for e in s['entities']),'GPU数据首次采集')
    bindings=request('/integrations/nightingale/sync',{})
    rule_id=next(b['rule_id'] for b in bindings if b['id']=='sim-0-thermal')
    def state_for(s,key):return next((v for v in s['states'] if v['id']==key),{})
    wait(lambda s:state_for(s,'sim-0-thermal').get('quality')=='valid' and not state_for(s,'sim-0-thermal').get('active'),'正常基线')
    for scenario,task in [('temperature_spike','sim-0-thermal'),('thermal_drift','sim-0-thermal'),('power_clock','sim-0-relation'),('activity_drop','sim-0-activity')]:
        at=time.time();request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':scenario})
        current=wait(lambda s:state_for(s,task).get('active') and state_for(s,task).get('last_source',0)>=at,scenario)
        record={'scenario':scenario,'task':task,'detection_seconds':round(time.time()-at,2),'passed':True}
        if scenario=='temperature_spike':
            event_state=wait(lambda s:any(e['rule_id']==rule_id for e in s['nightingale'].get('events',[])),'实际夜莺活动事件',75)
            event=next(e for e in event_state['nightingale']['events'] if e['rule_id']==rule_id)
            record.update(nightingale_event_id=event['id'],hash=event['hash'])
            request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'missing'})
            time.sleep(20)
            held=request('/state');assert state_for(held,task)['active'] and state_for(held,task)['quality']!='valid'
            held_event=next(e for e in held['nightingale']['events'] if e['rule_id']==rule_id)
            assert held_event['id']==event['id'] and held_event['hash']==event['hash']
            record['missing_preserves_same_nightingale_event']=True
        request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
        wait(lambda s:not state_for(s,task).get('active',True) and state_for(s,task).get('quality')=='valid','新鲜正常证据恢复')
        result['cases'].append(record);print(json.dumps(record),flush=True)
    # Role checks, invalid training and compatibility failures are real HTTP checks.
    from urllib.error import HTTPError
    try:request('/system/inference',{'enabled':False},role='viewer');raise AssertionError('viewer竟能停推理')
    except HTTPError as exc:assert exc.code==403
    try:request('/training-jobs',{'task':'sim-0-thermal','algorithm':'ridge_iforest','start':time.time()-86400,'end':time.time()-5,'step':2});raise AssertionError('超额窗口未拒绝')
    except HTTPError as exc:assert exc.code in (400,422)
    result.update(passed=True,elapsed_seconds=round(time.time()-start,2),role_check=True,bindings=len(bindings))
    folder=DATA/'evidence';folder.mkdir(exist_ok=True)
    (folder/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


def restore(archive,target):
    """Offline restore to a NEW empty directory; never overwrites a running volume."""
    target=Path(target)
    if target.exists() and any(target.iterdir()):raise ValueError('恢复目标必须为空目录，不覆盖运行状态')
    with tempfile.TemporaryDirectory() as temporary:
        stage=Path(temporary)
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                path=Path(member.name)
                if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk():raise ValueError('备份路径非法')
            tar.extractall(stage,filter='data')
        db=sqlite3.connect(stage/'gpu-ml.sqlite')
        try:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('备份数据库完整性失败')
            if db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]!='1':raise ValueError('备份schema不兼容')
            for row in db.execute("SELECT payload FROM documents WHERE kind='model'"):
                model=json.loads(row[0])
                if Path(model['snapshot']).name!=model['snapshot']:raise ValueError('备份快照路径非法')
                if model.get('backend'):
                    if not all(isinstance(model['backend'].get(k),str) and model['backend'][k] for k in ('backend_id','platform_id','model_ref')):raise ValueError('外部模型引用无效')
                else:
                    if Path(model['artifact']).name!=model['artifact']:raise ValueError('备份制品路径非法')
                    artifact=stage/'models'/model['artifact']
                    if hashlib.sha256(artifact.read_bytes()).hexdigest()!=model['sha256']:raise ValueError('备份模型摘要错误')
                snapshot=stage/'snapshots'/model['snapshot']
                if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=model['dataset_sha256']:raise ValueError('训练快照摘要错误')
        finally:db.close()
        import shutil
        target.mkdir(parents=True,exist_ok=True)
        for path in stage.iterdir():
            destination=target/path.name
            if path.is_dir():shutil.copytree(path,destination)
            else:shutil.copy2(path,destination)
    return {'restored_to':str(target),'schema':1}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['sync','verify','backup','restore']);parser.add_argument('archive',nargs='?');parser.add_argument('target',nargs='?');args=parser.parse_args()
    if args.command=='sync':print(json.dumps({'synced_rules':len(request('/integrations/nightingale/sync',{}))}))
    elif args.command=='backup':print(json.dumps(request('/backups',{})))
    elif args.command=='restore':print(json.dumps(restore(args.archive,args.target)))
    else:
        try:verify()
        finally:
            try:request('/simulation',{'uuid':'GPU-ML-SIM-0000','scenario':'normal'})
            except Exception:pass
