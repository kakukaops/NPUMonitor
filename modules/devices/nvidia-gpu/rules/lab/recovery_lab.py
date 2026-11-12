"""Isolated Nightingale integration for durable flag lifecycle state."""
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.parse
from n9e import API,unique,make_rule
from suite import request,notifications,tags

GROUP='H100恢复策略实验'
ADAPTER='http://recovery-adapter:9410'
NAME='H100恢复状态-只读适配器'
CONFIG=json.loads(Path('/rules/recovery-lab.json').read_text())


def items():
    return [{'key':'lifecycle_'+r['rule_id'].split('.',1)[1],
             'name':'持久恢复实验-'+r['rule_id'].split('.',1)[1],
             'expression':'gpu_lifecycle_active{lifecycle_rule_id="'+r['rule_id']+'"}',
             'severity':1,'for_seconds':0,'eval_interval_seconds':5,
             'note':'仅实验：缺数/无效保持活动；有效新鲜唯一标志0才解除。解除不表示硬件已修复。'} for r in CONFIG['rules']]


def context(create=False):
    api=API();bg=unique(api.call('GET','/busi-groups?all=true&limit=1000'),GROUP)
    if not bg and create:
        import n9e
        n9e.GROUP=GROUP
        n9e.install(api,{'catalog_version':'lifecycle-lab-0.1.0','rules':[]})
        bg=unique(api.call('GET','/busi-groups?all=true&limit=1000'),GROUP)
    if not bg:raise ValueError('先执行 recovery install 建立隔离业务组')
    nr=unique(api.call('GET','/notify-rules'),'GPU模拟-通知规则')
    channels=api.call('GET','/notify-channel-configs')
    assert nr and nr['enable'] and len(nr['notify_configs'])==1
    channel=next(c for c in channels if c['id']==nr['notify_configs'][0]['channel_id'])
    assert channel['request_config']['http_request_config']['url']=='http://notification-receiver:9080/webhook'
    ds=unique(api.call('POST','/datasource/list',{'plugin_type':'prometheus'}),NAME)
    return api,bg,nr,ds


def install():
    api,bg,nr,ds=context(create=True)
    assert api.call('GET','/self/profile').get('admin')
    if ds is None:
        api.call('POST','/datasource/upsert',{'name':NAME,'identifier':'h100-recovery-lab','plugin_type':'prometheus',
            'plugin_type_name':'Prometheus','category':'timeseries','status':'enabled','cluster_name':'default',
            'settings':{'prometheus_cluster_name':'default'},'http':{'url':ADAPTER,'timeout':10000,'dial_timeout':3000},
            'auth':{'basic_auth':False},'description':'固定查询的模拟状态适配器；非通用Prometheus，不可用于生产'})
        ds=unique(api.call('POST','/datasource/list',{'plugin_type':'prometheus'}),NAME)
    assert ds and ds['http']['url']==ADAPTER
    rows=api.call('GET',f'/busi-group/{bg["id"]}/alert-rules')
    for item in items():
        result=request(ADAPTER+'/api/v1/query?'+urllib.parse.urlencode({'query':item['expression']}))
        assert result['status']=='success'
        old=unique(rows,item['name'])
        if old:
            assert old.get('annotations',{}).get('managed_by')=='gpu-alert-lab'
            print('保留已有实验规则：'+item['name']);continue
        row=make_rule(item,bg['id'],ds['id'],nr['id'],'lifecycle-lab-0.1.0')
        api.call('POST',f'/busi-group/{bg["id"]}/alert-rules',[row])
        print('已创建：'+item['name'])
    # Native probe stays available for evidence but does not run during lifecycle tests.
    probe=unique(api.call('GET',f'/busi-group/{bg["id"]}/alert-rules'),'恢复能力实验-缺数不恢复')
    if probe and not probe['disabled']:
        assert probe.get('annotations',{}).get('managed_by')=='gpu-alert-lab'
        assert probe['rule_config']['queries'][0]['recover_config']=={'judge_type':1}
        probe['disabled']=1
        api.call('PUT',f'/busi-group/{bg["id"]}/alert-rule/{probe["id"]}',probe)
    print(json.dumps({'group_id':bg['id'],'datasource_id':ds['id'],'adapter':ADAPTER}))


class Runner:
    def __init__(self):
        self.api,self.bg,_,ds=context();assert ds and ds['http']['url']==ADAPTER
        rows=self.api.call('GET',f'/busi-group/{self.bg["id"]}/alert-rules')
        self.rows={}
        for item in items():
            row=unique(rows,item['name']);assert row and not row['disabled']
            assert row['rule_config']['queries'][0]['prom_ql']==item['expression']
            assert row['prom_for_duration']==0 and row['prom_eval_interval']==5
            self.rows[item['key']]=row
        self.ids={r['id'] for r in self.rows.values()}

    def active(self):
        return [e for e in self.api.call('GET',f'/alert-cur-events/list?bgid={self.bg["id"]}&hours=24&limit=100')['list'] if e['rule_id'] in self.ids]

    def select(self,name):
        request('http://gpu-simulator:9400/batch1/scenario',{'name':name})
        print('持久状态场景：'+name,flush=True)

    def wait(self,predicate,timeout=80):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=predicate()
            if value:return value
            time.sleep(2)
        raise TimeoutError('lifecycle condition timeout')

    def find(self,key,uuid='GPU-BATCH1-0000'):
        return next((e for e in self.active() if e['rule_id']==self.rows[key]['id'] and tags(e).get('UUID')==uuid),None)

    def records(self,since):return [e for _,e in notifications(since) if e.get('rule_id') in self.ids]

    def start(self,mode,key):
        self.select('normal');self.wait(lambda:not self.active())
        self.select(mode);print('等待原生活动事件：'+key,flush=True);event=self.wait(lambda:self.find(key))
        print('已触发，等待通知：'+str(event['id']),flush=True)
        self.wait(lambda:any(not e.get('is_recovered') and e['hash']==event['hash'] for e in self.records(event['trigger_time']-2)))
        return event

    def hold(self,mode,key,event,seconds=38):
        since=time.time();self.select(mode)
        # Wait until the adapter itself has observed uncertainty, then span several Nightingale evaluations.
        state=self.wait(lambda:self.unknown_state(key))
        while time.time()-since<seconds:
            current=self.find(key)
            assert current and current['id']==event['id'] and current['hash']==event['hash'],'active incident was lost/reopened'
            assert not any(e.get('is_recovered') and e['hash']==event['hash'] for e in self.records(since)),'false exit notification'
            time.sleep(2)
        return {'scenario':mode,'held_seconds':round(time.time()-since,2),'active_event_id':event['id'],
                'hash':event['hash'],'quality':state['quality'],'passed':True}

    def unknown_state(self,key):
        rid='nvidia.'+key.removeprefix('lifecycle_')
        state=request(ADAPTER+'/state')
        return next((s for s in state['states'] if s['rule_id']==rid and s['uuid']=='GPU-BATCH1-0000' and s['active']==1 and s['quality']!='valid'),None)

    def clear(self,key,event):
        since=time.time();self.select('normal');self.wait(lambda:not self.find(key))
        exited=self.wait(lambda:next((e for e in self.records(since) if e.get('is_recovered') and e['hash']==event['hash']),None))
        return exited


def suite():
    report={'scope':'durable_simulated_lifecycle','cases':[],'passed':False,'started_at':time.time(),
            'binding_sha256':hashlib.sha256(json.dumps(CONFIG,sort_keys=True).encode()).hexdigest(),
            'real_h100_tests':'not_run','production_admitted':False}
    changed=False
    try:
        assert request('http://gpu-simulator:9400/batch1/state')['scenario']=='normal','其他场景正在运行'
        runner=Runner();changed=True
        key='lifecycle_sram_threshold_exceeded';event=runner.start('sram',key)
        for mode in ['field_missing','invalid','duplicate','stale','scrape_error','empty']:
            report['cases'].append(runner.hold(mode,key,event))
        runner.clear(key,event)
        report['cases'].append({'scenario':'sram_valid_zero_clears','passed':True,'hash':event['hash']})
        key='lifecycle_row_remap_failed';event=runner.start('remap',key)
        report['cases'].append(runner.hold('empty',key,event))
        runner.clear(key,event)
        report['cases'].append({'scenario':'remap_valid_zero_clears','passed':True,'hash':event['hash']})
        report['passed']=True
    except Exception as error:
        report['error']=str(error);print('FAIL: '+str(error),flush=True)
    finally:
        if changed:request('http://gpu-simulator:9400/batch1/scenario',{'name':'normal'})
        report['finished_at']=time.time();Path('/results/recovery-lifecycle.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:raise SystemExit(1)
    print('PASS: durable lifecycle hold/clear scenarios',flush=True)


if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'state'
    if action=='install':install()
    elif action=='suite':suite()
    elif action=='restart-prepare':
        assert request('http://gpu-simulator:9400/batch1/state')['scenario']=='normal'
        runner=Runner();key='lifecycle_sram_threshold_exceeded';event=runner.start('sram',key)
        case=runner.hold('field_missing',key,event,seconds=12)
        Path('/results/recovery-restart.json').write_text(json.dumps({'started_at':time.time(),'key':key,'event':event,'before':case,'passed':False},ensure_ascii=False,indent=2))
        print('READY: existing active event retained with missing input',flush=True)
    elif action=='restart-outage':
        report=json.loads(Path('/results/recovery-restart.json').read_text());runner=Runner();since=time.time()
        for _ in range(10):
            current=runner.find(report['key'])
            assert current and current['id']==report['event']['id']
            assert not any(e.get('is_recovered') and e['hash']==current['hash'] for e in runner.records(report['started_at']))
            time.sleep(2)
        report['outage_observed_seconds']=time.time()-since
        Path('/results/recovery-restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('PASS: adapter outage does not resolve Nightingale active incident',flush=True)
    elif action=='restart-upstream-outage':
        report=json.loads(Path('/results/recovery-restart.json').read_text());runner=Runner();since=time.time()
        state=runner.wait(lambda:next((s for s in request(ADAPTER+'/state')['states'] if s['rule_id']=='nvidia.sram_threshold_exceeded' and s['uuid']=='GPU-BATCH1-0000' and s['active']==1 and s['quality']=='query_error'),None))
        for _ in range(10):
            current=runner.find(report['key']);assert current and current['id']==report['event']['id']
            assert not any(e.get('is_recovered') and e['hash']==current['hash'] for e in runner.records(report['started_at']))
            time.sleep(2)
        report['upstream_query_failure']={'observed_seconds':time.time()-since,'state':state,'passed':True}
        Path('/results/recovery-restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('PASS: upstream query failure holds native event with query_error state',flush=True)
    elif action=='restart-nightingale-verify':
        report=json.loads(Path('/results/recovery-restart.json').read_text());runner=Runner()
        runner.hold('field_missing',report['key'],report['event'],seconds=22)
        report['nightingale_restart_same_active_event']=True
        Path('/results/recovery-restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('PASS: Nightingale restart retained the same active incident',flush=True)
    elif action=='restart-finish':
        report=json.loads(Path('/results/recovery-restart.json').read_text());runner=Runner()
        current=runner.wait(lambda:runner.find(report['key']))
        assert current['id']==report['event']['id'] and current['hash']==report['event']['hash']
        state=runner.wait(lambda:runner.unknown_state(report['key']))
        assert state['last_value']==1 and state['active']==1
        runner.hold('field_missing',report['key'],report['event'],seconds=12)
        runner.clear(report['key'],report['event'])
        report.update(passed=True,after_restart_state=state,finished_at=time.time(),cleared_only_after_valid_zero=True)
        Path('/results/recovery-restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('PASS: SQLite state and same native event survived adapter restart; valid zero then cleared',flush=True)
    elif action=='state':print(json.dumps(request(ADAPTER+'/state'),ensure_ascii=False,indent=2))
    else:raise ValueError('unknown lifecycle action')
