"""Nightingale 9.3.0 management adapter. Own namespace; local-test notify only."""
import json
import hashlib
import os
from pathlib import Path
import time
from urllib.request import Request, ProxyHandler, build_opener
from .settings import NIGHTINGALE

from accelerator_integrations.nightingale import NightingaleClient

OWNER='gpu-monitoring-ml'
GROUP='GPU机器学习监控'
DS_NAME='GPU-ML持久结果'


class Nightingale:
    def __init__(self,store):
        self.store=store;self.last_error=None
        self.client=NightingaleClient(NIGHTINGALE,os.environ.get('GPU_ML_N9E_TOKEN_FILE','/run/secrets/n9e-token'))

    def call(self,method,path,body=None):
        return self.client.call(method,path,body)

    @staticmethod
    def one(rows,name):
        found=[r for r in rows if r['name']==name]
        if len(found)>1:raise ValueError('同名夜莺对象重复，停止覆盖')
        return found[0] if found else None

    def signature(self):
        rows=[(t['id'],t['name'],t['enabled'],t.get('notification_mode','alert')) for t in self.store.list('task')]
        return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()

    def sync(self):
        sources=self.call('POST','/datasource/list',{'plugin_type':'prometheus'})
        source=self.one(sources,DS_NAME)
        if not source:
            self.call('POST','/datasource/upsert',{'name':DS_NAME,'identifier':'gpu-ml-results','plugin_type':'prometheus',
                'plugin_type_name':'Prometheus','category':'timeseries','status':'enabled','cluster_name':'default',
                'settings':{'prometheus_cluster_name':'default'},'http':{'url':'http://gpu-ml:9460','timeout':10000,'dial_timeout':3000},
                'auth':{'basic_auth':False},'description':OWNER+' 持久检测结果，非通用PromQL'})
            source=self.one(self.call('POST','/datasource/list',{'plugin_type':'prometheus'}),DS_NAME)
        if source['http']['url']!='http://gpu-ml:9460' or OWNER not in source.get('description',''):
            raise ValueError('同名数据源不属于本模块或已修改')
        group=self.one(self.call('GET','/busi-groups?all=true&limit=1000'),GROUP)
        team=self.one(self.call('GET','/user-groups'),'GPU模拟-测试用户组')
        if not team:raise ValueError('缺少既有本地测试用户组，停止初始化')
        if not group:
            self.call('POST','/busi-groups',{'name':GROUP,'members':[{'user_group_id':team['id'],'perm_flag':'rw'}]})
            group=self.one(self.call('GET','/busi-groups?all=true&limit=1000'),GROUP)
        notify=self.one(self.call('GET','/notify-rules'),'GPU模拟-通知规则')
        channels=self.call('GET','/notify-channel-configs')
        if not notify or not notify.get('enable'):raise ValueError('本地测试通知规则不可用')
        for cfg in notify['notify_configs']:
            channel=next(c for c in channels if c['id']==cfg['channel_id'])
            if channel['request_config']['http_request_config']['url']!='http://notification-receiver:9080/webhook':
                raise ValueError('通知出口不是指定本地测试接收器，拒绝绑定')
        existing=self.call('GET',f'/busi-group/{group["id"]}/alert-rules')
        output=[]
        wanted=[(task['id'],task['name'],f'gpu_ml_active{{detector_id="{task["id"]}"}} == 1',task['enabled'] and task.get('notification_mode','alert')=='alert') for task in self.store.list('task')]
        wanted.append(('platform','GPU ML检测平台健康','gpu_ml_platform_unhealthy',True))
        wanted.append(('quality','GPU ML输入与模型质量','gpu_ml_input_unhealthy',True))
        for ident,name,expression,enabled in wanted:
            rule_name='GPU-ML '+name
            matches=[r for r in existing if r.get('annotations',{}).get('managed_by')==OWNER and r.get('annotations',{}).get('detector_id')==ident]
            if len(matches)>1:raise ValueError('同一检测任务出现重复受管规则')
            old=matches[0] if matches else self.one(existing,rule_name)
            desired={'name':rule_name,'group_id':group['id'],'cate':'prometheus','prod':'metric',
                'datasource_queries':[{'match_type':0,'op':'in','values':[source['id']]}],
                'rule_config':{'queries':[{'prom_ql':expression,'severity':2,'recover_config':{'judge_type':0}}]},
                'prom_eval_interval':5,'prom_for_duration':10 if ident=='quality' else 0,'disabled':int(not enabled),'notify_version':1,
                'notify_rule_ids':[notify['id']],'notify_recovered':1,'notify_repeat_step':300,'notify_max_number':3,
                'recover_duration':0,'note':'GPU ML检测条件退出或管理关闭不等于硬件修复；输入未知时保持已确认异常。独立详情 http://localhost:19460',
                'append_tags':['managed_by='+OWNER,'detector_id='+ident],
                'annotations':{'managed_by':OWNER,'detector_id':ident,'scope':'simulation-preview'}}
            if old:
                if old.get('annotations',{}).get('managed_by')!=OWNER:raise ValueError('同名规则非本模块管理')
                old_expression=old['rule_config']['queries'][0]['prom_ql']
                if old_expression!=expression or old['datasource_queries']!=desired['datasource_queries']:
                    raise ValueError('受管规则被手工修改，停止覆盖')
                if old.get('disabled',0)!=desired['disabled'] or old['name']!=rule_name:
                    old.update(disabled=desired['disabled'],name=rule_name)
                    self.call('PUT',f'/busi-group/{group["id"]}/alert-rule/{old["id"]}',old)
                rule=old
            else:
                self.call('POST',f'/busi-group/{group["id"]}/alert-rules',[desired])
                rule=self.one(self.call('GET',f'/busi-group/{group["id"]}/alert-rules'),rule_name)
            binding=self.store.put('binding',ident,{'rule_id':rule['id'],'source_id':source['id'],'group_id':group['id'],
                                                    'expression':expression,'synced_at':time.time()})
            output.append(binding)
        self.store.put('system','sync_error',{'error':None,'at':time.time()})
        self.store.put('system','nightingale',{'status':'synced','synced_at':time.time(),'rules':len(output),'task_signature':self.signature(),'group_id':group['id']})
        return output

    def events(self):
        group=self.store.get('system','nightingale')
        if not group:return {'connected':False,'events':[]}
        try:
            rows=self.call('GET',f'/alert-cur-events/list?bgid={group["group_id"]}&hours=24&limit=1000')
            if isinstance(rows,dict):rows=rows.get('list',rows.get('items',[]))
            own=[r for r in rows if r.get('rule_id') in {b['rule_id'] for b in self.store.list('binding')}]
            history=self.call('GET',f'/alert-his-events/list?bgid={group["group_id"]}&hours=24&limit=100')
            historical=history.get('list',[]) if isinstance(history,dict) else history
            all_rows=self.call('GET','/alert-cur-events/list?hours=24&limit=1000')
            all_events=all_rows.get('list',[]) if isinstance(all_rows,dict) else all_rows
            uuids={e['uuid'] for e in self.store.list('entity')}
            def related(event):
                tags=event.get('tags_map',{})
                if not tags:
                    raw=event.get('tags',[])
                    tags=dict(v.split('=',1) for v in raw if isinstance(v,str) and '=' in v)
                return tags.get('UUID') in uuids and event['rule_id'] not in {b['rule_id'] for b in self.store.list('binding')}
            result={'connected':True,'events':own,'history':historical[:30],
                    'rule_events':[e for e in all_events if related(e)],'checked_at':time.time()}
            self.store.put('system','nightingale_events',result);return result
        except Exception as exc:
            self.last_error=type(exc).__name__
            return dict(self.store.get('system','nightingale_events') or {'events':[]},connected=False,error=self.last_error)
