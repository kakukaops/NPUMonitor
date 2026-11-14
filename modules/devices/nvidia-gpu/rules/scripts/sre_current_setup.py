#!/usr/bin/env python3
"""Bind current OS SRE rules to the user's existing local Nightingale explicitly."""
import json,os,sys
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
ROOT=Path(__file__).resolve().parents[5];MODULE=ROOT/'modules/devices/nvidia-gpu/rules';PRIVATE=ROOT/'.local/gpu-os-sre-master'
sys.path.insert(0,str(MODULE/'runtime/src'))
from npumonitor_rules.source import NoRedirect
from npumonitor_rules.bundle import compile_bundle
os.umask(0o077)
opener=build_opener(ProxyHandler({}),NoRedirect())

def call(path,body=None):
    token=(ROOT/'.local/n9e-token').read_text().strip()
    request=Request('http://127.0.0.1:17000/api/n9e'+path,data=None if body is None else json.dumps(body).encode(),headers={'X-User-Token':token,'Content-Type':'application/json'})
    with opener.open(request,timeout=20) as response:value=json.load(response)
    if value.get('err') or value.get('error'):raise ValueError('Existing Nightingale rejected setup')
    return value.get('dat',value.get('data',value))
def one(rows,name):
    found=[r for r in rows if r.get('name')==name]
    if len(found)>1:raise ValueError('duplicate managed object name')
    return found[0] if found else None
def write(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)
def main():
    import secrets,yaml
    PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True);PRIVATE.chmod(0o700)
    for name in ('admin-token','viewer-token','notify-token'):
        p=PRIVATE/name
        if not p.exists():
            with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:f.write(secrets.token_urlsafe(36)+'\n')
        p.chmod(0o600)
    name='GPU OS SRE 管理';team=one(call('/user-groups'),name)
    if not team:
        call('/user-groups',{'name':name,'note':'Current OS SRE rule management','is_sync_to_flashduty':False});team=one(call('/user-groups'),name)
    name='GPU监控规则（OS SRE）';group=one(call('/busi-groups?all=true&limit=1000'),name)
    if not group:
        call('/busi-groups',{'name':name,'members':[{'user_group_id':team['id'],'perm_flag':'rw'}]});group=one(call('/busi-groups?all=true&limit=1000'),name)
    name='GPU OS SRE 本地通知';channel=one(call('/notify-channel-configs'),name);endpoint='http://notification-receiver:9080/webhook'
    if not channel:
        call('/notify-channel-configs',[{'name':name,'ident':'callback','enable':True,'request_type':'http','description':'Current OS SRE local test receiver; no external recipients',
           'request_config':{'http_request_config':{'url':endpoint,'method':'POST','headers':{'Content-Type':'application/json'},'timeout':5000,'concurrency':2,'retry_times':1,'retry_interval':200,'request':{'body':'{{ jsonMarshal $events }}'}}}}]);channel=one(call('/notify-channel-configs'),name)
    if channel['request_config']['http_request_config']['url']!=endpoint:raise ValueError('notification endpoint was externally changed')
    notify=one(call('/notify-rules'),name)
    if not notify:
        call('/notify-rules',[{'name':name,'description':'Current GPU OS SRE rules','enable':True,'user_group_ids':[team['id']],
          'notify_configs':[{'channel_id':channel['id'],'template_id':0,'params':{},'type':'all','severities':[1,2,3],'time_ranges':[],'label_keys':[],'attributes':[]}]}]);notify=one(call('/notify-rules'),name)
    path=PRIVATE/'config.json'
    if not path.exists():
        cfg=json.loads((MODULE/'runtime/config.example.json').read_text());profile=yaml.safe_load((ROOT/'deploy/nvidia-gpu/rules/current/profile.yaml').read_text())
        cfg.update(deployment_id='gpu-os-sre-master',master_profile='h100-master-simulation-v1',profile=profile,limits={'poll_seconds':5,'query_timeout_seconds':5,'query_workers':4,'preflight_seconds':30},notification_counter_verified=False)
        cfg['upstream']['url']='http://gpu-master-prometheus:9090'
        cfg['nightingale'].update(group_id=group['id'],notify_rule_id=notify['id'],eval_interval_seconds=5,include_gateway_health_rule=False)
        cfg['nightingale']['gateway_url']='http://npumonitor-gpu-rules-master-sre-runtime-1:9480'
        cfg['watchdog']['targets'][0]['url']='http://npumonitor-gpu-rules-master-sre-runtime-1:9480/ready'
        cfg['watchdog'].update(callback_url=endpoint)
        write(path,cfg)
    cfg=json.loads(path.read_text())
    if cfg['nightingale']['group_id']!=group['id'] or cfg['nightingale']['notify_rule_id']!=notify['id']:raise ValueError('active installation binding changed; use explicit release migration')
    bundle=compile_bundle(cfg,MODULE);write(PRIVATE/'bundle.json',bundle)
    print(json.dumps({'target_nightingale_port':17000,'group_id':group['id'],'notify_rule_id':notify['id'],'rules':len(bundle['rules']),'sha256':bundle['sha256']}))
if __name__=='__main__':main()
