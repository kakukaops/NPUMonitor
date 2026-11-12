"""Install, inspect and control the local H100 training acceptance demonstration."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.parse

import n9e
from n9e import API, unique, make_rule
from suite import request

GROUP='H100训练综合演示'
SOURCE='http://comprehensive-source:9430'
GATEWAY='http://comprehensive-lifecycle:9410'
ROOT=Path('/rules')
CATALOG=json.loads((ROOT/'comprehensive-catalog.json').read_text())
PROBE_QUERY='DEMO_PROBE_INPUT{job="h100-comprehensive"} > 1'


def datasource(api,name,identifier,url):
    rows=api.call('POST','/datasource/list',{'plugin_type':'prometheus'})
    row=unique(rows,name)
    if row is None:
        api.call('POST','/datasource/upsert',{
            'name':name,'identifier':identifier,'plugin_type':'prometheus','plugin_type_name':'Prometheus',
            'category':'timeseries','status':'enabled','cluster_name':'default',
            'settings':{'prometheus_cluster_name':'default'},
            'http':{'url':url,'timeout':10000,'dial_timeout':3000},'auth':{'basic_auth':False},
            'description':'H100综合模拟验收专用'})
        row=unique(api.call('POST','/datasource/list',{'plugin_type':'prometheus'}),name)
    if not row or row.get('http',{}).get('url')!=url:
        raise ValueError('实验数据源配置不符 '+name)
    return row


def notification(api):
    name='H100综合演示-主通知'
    url=SOURCE+'/webhook'
    channel=unique(api.call('GET','/notify-channel-configs'),name)
    if channel is None:
        api.call('POST','/notify-channel-configs',[{
            'name':name,'ident':'callback','enable':True,'request_type':'http',
            'description':'本地综合演示投递，支持失败注入',
            'request_config':{'http_request_config':{'url':url,'method':'POST',
                'headers':{'Content-Type':'application/json'},'timeout':5000,'concurrency':2,
                'retry_times':1,'retry_interval':100,'request':{'body':'{{ jsonMarshal $events }}'}}}}])
        channel=unique(api.call('GET','/notify-channel-configs'),name)
    if channel['request_config']['http_request_config']['url']!=url:
        raise ValueError('演示通知目标已修改')
    team=unique(api.call('GET','/user-groups'),'GPU模拟-测试用户组')
    rule=unique(api.call('GET','/notify-rules'),name)
    if rule is None:
        api.call('POST','/notify-rules',[{'name':name,'description':'本地综合演示通知',
            'enable':True,'user_group_ids':[team['id']],
            'notify_configs':[{'channel_id':channel['id'],'template_id':0,'params':{},'type':'all',
                               'severities':[1,2,3],'time_ranges':[],'label_keys':[],'attributes':[]}]}])
        rule=unique(api.call('GET','/notify-rules'),name)
    if not rule.get('enable') or len(rule['notify_configs'])!=1 or rule['notify_configs'][0]['channel_id']!=channel['id']:
        raise ValueError('演示通知规则已修改')
    backup=unique(api.call('GET','/notify-rules'),'GPU模拟-通知规则')
    backup_config=backup['notify_configs'][0]
    backup_channel=next(c for c in api.call('GET','/notify-channel-configs') if c['id']==backup_config['channel_id'])
    if backup_channel['request_config']['http_request_config']['url']!='http://notification-receiver:9080/webhook':
        raise ValueError('备用通知目标已修改')
    return rule,backup


def install_one(api,group,source_id,notify_id,item):
    existing=unique(api.call('GET',f'/busi-group/{group}/alert-rules'),item['name'])
    desired=make_rule(item,group,source_id,notify_id,'training-demo-0.1.0')
    if existing:
        if existing.get('annotations',{}).get('managed_by')!='gpu-alert-lab':
            raise ValueError('同名规则归属不符 '+item['key'])
        old=existing['rule_config']['queries'][0]['prom_ql']
        if old!=item['expression'] or existing['prom_for_duration']!=item['for_seconds']:
            raise ValueError('已有规则内容不同，需显式迁移 '+item['key'])
        if existing['disabled']:
            raise ValueError('已有规则已禁用 '+item['key'])
        return existing
    api.call('POST',f'/busi-group/{group}/alert-rules',[desired])
    result=unique(api.call('GET',f'/busi-group/{group}/alert-rules'),item['name'])
    if not result:
        raise ValueError('规则回读失败 '+item['key'])
    print('已创建 '+item['name']+' id='+str(result['id']),flush=True)
    return result


def health_rules(probe_id,managed_ids):
    ids='|'.join(str(i) for i in sorted(set(managed_ids+[probe_id])))
    target='up{job="nightingale-self"} == 1'
    query=f'n9e_alert_eval_query_series_count{{job="nightingale-self",rule_id=~"{ids}"}}'
    attempts=f'n9e_alert_query_data_total{{job="nightingale-self",rule_id="{probe_id}"}}'
    return [
      {'key':'platform_query_failure','name':'H100平台-查询或评估失败','expression':f'({query} < 0) and on(job,instance) ({target}) and on() (DEMO_ADAPTER_UP{{job="h100-comprehensive"}} == 1)',
       'severity':1,'for_seconds':10,'eval_interval_seconds':5,'desired_for_seconds':5,
       'note':'实际夜莺评估结果为负值，保存rule_id及原始错误。备用通道发送。'},
      {'key':'platform_evaluation_stall','name':'H100平台-评估调度停滞',
       'expression':f'((increase({attempts}[20s]) == 0) and (count_over_time({attempts}[20s]) >= 2)) and on(job,instance) ({target})',
       'severity':1,'for_seconds':10,'eval_interval_seconds':5,'desired_for_seconds':5,
       'note':'固定5秒调度的探针在20秒窗口无新查询尝试。故障演练将探针周期改为3600秒，恢复时回到5秒。'},
      {'key':'platform_notify_failure','name':'H100平台-主通知投递失败',
       'expression':'increase(DEMO_NOTIFY_FAILURES_TOTAL{job="h100-comprehensive"}[30s]) > 0',
       'severity':1,'for_seconds':0,'eval_interval_seconds':5,'desired_for_seconds':0,
       'note':'实际Night POST失败记录的累计计数，备用独立本地接收通道发送，窗口退出表示近期无失败。'},
      {'key':'platform_adapter_down','name':'H100平台-状态适配器不可用',
       'expression':'DEMO_ADAPTER_UP{job="h100-comprehensive"} == 0',
       'severity':1,'for_seconds':10,'eval_interval_seconds':5,'desired_for_seconds':5,
       'note':'独立看门狗检测状态适配器健康，错误不按成功空结果处理。'},
      {'key':'platform_nightingale_metrics_missing','name':'H100平台-夜莺自监控抓取不可用',
       'expression':'up{job="nightingale-self"} == 0',
       'severity':1,'for_seconds':10,'eval_interval_seconds':5,'desired_for_seconds':5,
       'note':'外部演示看门狗另记录组件不可达，夜莺进程停止时通过独立页面观察。'}]


def install():
    api=API()
    n9e.GROUP=GROUP
    n9e.install(api,{'catalog_version':'training-demo-0.1.0','rules':[]})
    group=unique(api.call('GET','/busi-groups?all=true&limit=1000'),GROUP)['id']
    primary,backup=notification(api)
    probe_ds=datasource(api,'H100综合演示-查询探针','h100-demo-probe',SOURCE)
    state_ds=datasource(api,'H100综合演示-持久状态','h100-demo-state',GATEWAY)
    prom_ds=datasource(api,'H100综合演示-Prometheus','h100-demo-prom','http://prometheus:9090')
    probe={'key':'comprehensive_probe','name':'H100平台-实际投递与评估探针','expression':PROBE_QUERY,
           'severity':3,'for_seconds':0,'eval_interval_seconds':5,
           'note':'本地实际查询、评估和通知失败注入用探针。'}
    probe_row=install_one(api,group,probe_ds['id'],primary['id'],probe)
    rule_ids={}
    for entry in CATALOG['rules']:
        expression=entry['observation_expression'] if entry['kind']=='direct' else (
            'gpu_lifecycle_active{lifecycle_rule_id="'+entry['rule_id']+'"}')
        item={'key':'comprehensive_'+entry['rule_id'].split('.',1)[1],'name':'H100训练-'+entry['title'],
              'expression':expression,'severity':entry['severity'],
              'for_seconds':entry['native_for_seconds'],'eval_interval_seconds':5,
              'note':entry['trigger']+'；解除 '+entry['clear']+'。'+entry['reason']+' 仅模拟验收。'}
        source_id=prom_ds['id'] if entry['kind']=='direct' else state_ds['id']
        row=install_one(api,group,source_id,primary['id'],item)
        rule_ids[entry['rule_id']]=row['id']
    health=health_rules(probe_row['id'],list(rule_ids.values()))
    health_ids={}
    for item in health:
        row=install_one(api,group,prom_ds['id'],backup['id'],item)
        health_ids[item['key']]=row['id']
    result={'group_id':group,'group_name':GROUP,'probe_rule_id':probe_row['id'],
            'rule_ids':rule_ids,'health_rule_ids':health_ids,
            'managed_rule_ids':list(rule_ids.values())+list(health_ids.values()),
            'primary_notify_rule_id':primary['id'],'backup_notify_rule_id':backup['id'],
            'datasource_ids':{'probe':probe_ds['id'],'state':state_ds['id'],'prometheus':prom_ds['id']},
            'catalog_sha256':hashlib.sha256((ROOT/'comprehensive-catalog.json').read_bytes()).hexdigest()}
    path=ROOT/'comprehensive-runtime.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)
    (ROOT/'comprehensive-health.json').write_text(json.dumps(health,ensure_ascii=False,indent=2)+'\n')
    print('PASS: 综合规则已接入 '+str(group)+'，硬件/数据质量 '+str(len(rule_ids))+'，平台 '+str(len(health_ids)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['install','state','scenario','rules'])
    parser.add_argument('name',nargs='?')
    args=parser.parse_args()
    if args.action=='install':
        install()
    elif args.action=='scenario':
        print(json.dumps(request(SOURCE+'/api/scenario',{'name':args.name}),ensure_ascii=False))
    elif args.action=='state':
        result=request(SOURCE+'/api/status')
        print(json.dumps({'model':result['model'],'alerts':result.get('alerts',[]),
                          'notification_counts':result['notification_counts']},ensure_ascii=False,indent=2))
    else:
        binding=json.loads((ROOT/'comprehensive-runtime.json').read_text())
        api=API()
        rows=api.call('GET',f'/busi-group/{binding["group_id"]}/alert-rules')
        print(json.dumps([{'id':r['id'],'name':r['name'],'disabled':r['disabled'],
                           'for_seconds':r['prom_for_duration'],'eval_seconds':r['prom_eval_interval']}
                          for r in rows],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
