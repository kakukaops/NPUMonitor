#!/usr/bin/env python3
"""Prepare a wholly isolated acceptance system; never reads existing credentials."""
import json,os,secrets,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
os.umask(0o077)
ROOT=Path(__file__).resolve().parents[5];MODULE=ROOT/'modules/devices/nvidia-gpu/rules';PRIVATE=ROOT/'.local/npumonitor-rules-contract'
sys.path.insert(0,str(MODULE/'runtime/src'))
from npumonitor_rules.bundle import compile_bundle

def write(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)

def prepare():
    PRIVATE.mkdir(parents=True,exist_ok=True);PRIVATE.chmod(0o700)
    for name in ('admin-token','viewer-token','bootstrap-password'):
        p=PRIVATE/name
        if not p.exists():
            with p.open('x') as f:f.write(secrets.token_urlsafe(36)+'\n')
        p.chmod(0o600)
    if not (PRIVATE/'config.json').exists():
        import yaml
        profile=yaml.safe_load((MODULE/'monitoring/os-sre/profile.yaml').read_text())
        profile.update(collector_job_regex='dcgm-contract',freshness_seconds=8,counter_window_seconds=30,confirmation_seconds=4)
        profile['gpus']=[{'job':'dcgm-contract','instance':'sre-source:9490','UUID':'GPU-CONTRACT-'+str(i).zfill(4),'required_fields':['DCGM_FI_DEV_GPU_TEMP','DCGM_FI_DEV_MEMORY_TEMP'],
            'pcie_gen':5,'pcie_width':16,'pcie_active_bytes_per_second':1000000,'fabric_expected':True} for i in range(2)]
        profile['switches']=[{'job':'dcgm-contract','instance':'sre-source:9490','switch_id':'SW-CONTRACT-0000'}]
        profile['links']=[{'job':'dcgm-contract','instance':'sre-source:9490','UUID':'GPU-CONTRACT-'+str(i).zfill(4),'link_id':'0'} for i in range(2)]+[{'job':'dcgm-contract','instance':'sre-source:9490','switch_id':'SW-CONTRACT-0000','link_id':'0'}]
        profile['monitor_targets']=[{'job':'nightingale-self','instance':'sre-source:9490','evaluation_expected':True}]
        write(PRIVATE/'config.json',{'deployment_id':'contract-acceptance','contract_profile':'dcgm-os-sre-physical-v1','profile':profile,
             'upstream':{'url':'http://sre-prometheus:9090'},'gateway':{'admin_token_file':'/run/secrets/admin','viewer_token_file':'/run/secrets/viewer','port':9480},
             'limits':{'poll_seconds':2,'query_timeout_seconds':2,'query_workers':8,'max_source_gap_seconds':8,'max_poll_age_seconds':30,'preflight_seconds':5},'notification_counter_verified':False,
             'nightingale':{'url':'http://sre-nightingale:17000','token_file':'/run/secrets/n9e','gateway_url':'http://sre-runtime:9480','group_id':0,'notify_rule_id':0,'eval_interval_seconds':2},
             'watchdog':{'targets':[{'name':'rule-gateway','url':'http://sre-runtime:9480/ready'},{'name':'nightingale','url':'http://sre-nightingale:17000/'}],
                 'callback_url':'http://sre-receiver:9492/webhook','callback_token_file':'/run/secrets/admin','interval_seconds':2,'timeout_seconds':2,'failure_count':5,'repeat_seconds':3600}})
    compile_local()

def compile_local():
    value=compile_bundle(json.loads((PRIVATE/'config.json').read_text()),MODULE);write(PRIVATE/'bundle.json',value)
    print(json.dumps({'compiled':True,'rules':len(value['rules']),'sha256':value['sha256']}))

def bootstrap():
    base='http://127.0.0.1:17001/api/n9e';jwt=None;api_key=None
    def call(method,path,body=None,anonymous=False):
        headers={'Content-Type':'application/json'}
        if not anonymous:
            if api_key:headers['X-User-Token']=api_key
            elif jwt:headers['Authorization']='Bearer '+jwt
        req=Request(base+path,data=None if body is None else json.dumps(body).encode(),method=method,headers=headers)
        with urlopen(req,timeout=20) as f:value=json.load(f)
        if isinstance(value,dict):
            if value.get('error') or value.get('err'):raise ValueError('isolated Nightingale rejected '+path)
            return value.get('dat',value.get('data',value))
        return value
    keyfile=PRIVATE/'n9e-token'
    if keyfile.exists():api_key=keyfile.read_text().strip()
    else:
        new_password=(PRIVATE/'bootstrap-password').read_text().strip()
        try:session=call('POST','/auth/login',{'username':'root','password':new_password},True);old_password=new_password
        except Exception:
            # Published factory password, used only on this brand-new private instance.
            old_password='root.2020';session=call('POST','/auth/login',{'username':'root','password':old_password},True)
        jwt=session['access_token']
        if old_password!=new_password:
            call('PUT','/self/password',{'oldpass':old_password,'newpass':new_password})
            jwt=call('POST','/auth/login',{'username':'root','password':new_password},True)['access_token']
        issued=call('POST','/self/token',{'token_name':'NPUMonitor isolated contract runner'})
        api_key=issued['token'];keyfile.write_text(api_key+'\n');keyfile.chmod(0o600)
    # API-token caches may refresh asynchronously after the token is created.
    for attempt in range(90):
        try:call('GET','/self/profile');break
        except Exception:
            if attempt==89:raise
            time.sleep(1)
    def one(rows,name):
        found=[r for r in rows if r['name']==name]
        if len(found)>1:raise ValueError('isolated object name collision')
        return found[0] if found else None
    name='NPUMonitor Contract Team';team=one(call('GET','/user-groups'),name)
    if not team:
        call('POST','/user-groups',{'name':name,'note':'isolated synthetic acceptance','is_sync_to_flashduty':False});team=one(call('GET','/user-groups'),name)
    name='NPUMonitor OS SRE Contract Acceptance';group=one(call('GET','/busi-groups?all=true&limit=1000'),name)
    if not group:
        call('POST','/busi-groups',{'name':name,'members':[{'user_group_id':team['id'],'perm_flag':'rw'}]});group=one(call('GET','/busi-groups?all=true&limit=1000'),name)
    endpoint='http://sre-receiver:9492/webhook';secret=(PRIVATE/'admin-token').read_text().strip();name='NPUMonitor Contract Webhook';channel=one(call('GET','/notify-channel-configs'),name)
    if not channel:
        call('POST','/notify-channel-configs',[{'name':name,'ident':'callback','enable':True,'request_type':'http','description':'isolated local test receiver',
            'request_config':{'http_request_config':{'url':endpoint,'method':'POST','headers':{'Content-Type':'application/json','Authorization':'Bearer '+secret},'timeout':5000,'concurrency':2,'retry_times':1,'retry_interval':200,'request':{'body':'{{ jsonMarshal $events }}'}}}}])
        channel=one(call('GET','/notify-channel-configs'),name)
    if channel['request_config']['http_request_config']['url']!=endpoint:raise ValueError('test receiver mismatch')
    name='NPUMonitor Contract Notify';notify=one(call('GET','/notify-rules'),name)
    if not notify:
        call('POST','/notify-rules',[{'name':name,'description':'isolated synthetic acceptance','enable':True,'user_group_ids':[team['id']],
          'notify_configs':[{'channel_id':channel['id'],'template_id':0,'params':{},'type':'all','severities':[1,2,3],'time_ranges':[],'label_keys':[],'attributes':[]}]}]);notify=one(call('GET','/notify-rules'),name)
    cfg=json.loads((PRIVATE/'config.json').read_text());cfg['nightingale'].update(group_id=group['id'],notify_rule_id=notify['id']);write(PRIVATE/'config.json',cfg);compile_local()
    print(json.dumps({'isolated':True,'group_id':group['id'],'notify_rule_id':notify['id']}))

if __name__=='__main__':{'prepare':prepare,'compile':compile_local,'bootstrap':bootstrap}[sys.argv[1]]()
