"""End-to-end acceptance of every training rule through real Nightingale callbacks."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import signal
import time

from n9e import API
from suite import request, tags
from comprehensive_control import SOURCE, GATEWAY, CATALOG, GROUP

BINDING=json.loads(Path('/rules/comprehensive-runtime.json').read_text())


class Runner:
    def __init__(self):
        self.api=API()
        self.group=BINDING['group_id']
        self.ids=set(BINDING['managed_rule_ids'])
        self.catalog={r['rule_id']:r for r in CATALOG['rules']}

    def scenario(self,name):
        result=request(SOURCE+'/api/scenario',{'name':name})
        print('场景 '+name,flush=True)
        return result

    def active(self):
        rows=self.api.call('GET',f'/alert-cur-events/list?bgid={self.group}&hours=24&limit=100')['list']
        return [r for r in rows if r['rule_id'] in self.ids]

    def notifications(self,since):
        events=[]
        for record in request(SOURCE+'/api/attempts')['records']:
            if datetime.fromisoformat(record['received_at']).timestamp()<since:
                continue
            if record['payload']['status']=='delivered':
                events.extend(record['payload']['events'])
        for record in request('http://notification-receiver:9080/events')['events']:
            if datetime.fromisoformat(record['received_at']).timestamp()<since:
                continue
            if isinstance(record['payload'],list):
                events.extend(record['payload'])
        return [e for e in events if e.get('rule_id') in self.ids]

    def wait(self,predicate,description,timeout=100):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=predicate()
            if value:
                return value
            time.sleep(1)
        raise TimeoutError(description)

    def baseline(self):
        self.scenario('recover')
        self.wait(lambda:not self.active(),'baseline has active alerts',timeout=110)
        state=self.wait(lambda:self.valid_state(),'baseline state is unverified')
        return state

    def valid_state(self):
        state=request(GATEWAY+'/state')
        if all(s['quality']=='valid' and not s['active'] for s in state['states']) and not state['pending']:
            return state
        return None

    def assert_active(self,expected):
        active=self.active()
        unexpected={e['rule_id'] for e in active}-set(expected)
        if unexpected:
            raise ValueError('unexpected active rules '+str(unexpected))
        return active

    def fault(self,scenario,rule_id,report,entity=None):
        self.baseline()
        started=time.time()
        case={'scenario':scenario,'rule_id':rule_id,'started_at':started,'passed':False}
        report['cases'].append(case)
        self.scenario(scenario)
        def fired():
            rows=self.assert_active([rule_id])
            return next((e for e in rows if e['rule_id']==rule_id),None)
        event=self.wait(fired,'missing firing event '+scenario)
        case.update(active_event_id=event['id'],hash=event['hash'],firing_after_seconds=round(time.time()-started,3))
        if entity is not None:
            assert tags(event).get('entity_id')==entity,(scenario,tags(event))
        self.wait(lambda:any(not e.get('is_recovered') and e['hash']==event['hash'] for e in self.notifications(started)),
                  'missing firing callback '+scenario)
        native_start=event['trigger_time']-started
        definition=next((r for r in CATALOG['rules'] if BINDING['rule_ids'][r['rule_id']]==rule_id),None)
        if definition and definition['desired_for_seconds']:
            assert native_start>=definition['desired_for_seconds']-1,(scenario,'fired before duration',native_start)
        recovered_at=time.time()
        self.scenario('recover')
        self.wait(lambda:not self.active(),'missing recovery '+scenario,timeout=110)
        exited=self.wait(lambda:next((e for e in self.notifications(recovered_at) if e.get('is_recovered') and e['hash']==event['hash']),None),
                         'missing recovery callback '+scenario)
        assert exited['hash']==event['hash']
        case.update(passed=True,exit_after_seconds=round(time.time()-recovered_at,3),native_trigger_after_seconds=round(native_start,3))
        print('PASS '+scenario+' 触发/持续/对象/通知/解除',flush=True)

    def quiet(self,scenario,report,seconds=18):
        self.baseline();started=time.time();self.scenario(scenario)
        case={'scenario':scenario,'passed':False};report['cases'].append(case)
        saw_fault=False
        while time.time()-started<seconds:
            if scenario=='thermal_transient':
                query='DCGM_FI_DEV_GPU_TEMP{job="h100-comprehensive",entity_id="GPU-DEMO-0000"}'
                import urllib.parse
                samples=request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':query}))['data']['result']
                saw_fault=saw_fault or any(float(s['value'][1])==96 for s in samples)
            assert not self.active(),scenario+' unexpected alert'
            assert not any(not e.get('is_recovered') for e in self.notifications(started)),scenario+' unexpected notification'
            time.sleep(1)
        if scenario=='thermal_transient':assert saw_fault,'transient was never actually sampled'
        case.update(passed=True,observed_seconds=round(time.time()-started,3),sampled_transient=saw_fault if scenario=='thermal_transient' else None)
        self.scenario('recover')
        print('PASS '+scenario+' 抑制误报',flush=True)

    def hold_after_missing(self,report):
        self.baseline();key='training.gpu_thermal';rid=BINDING['rule_ids'][key]
        self.scenario('gpu_thermal')
        event=self.wait(lambda:next((e for e in self.active() if e['rule_id']==rid),None),'thermal start')
        started=time.time();self.scenario('entity_missing')
        quality=BINDING['rule_ids']['training.entity_missing']
        self.wait(lambda:any(e['rule_id']==quality for e in self.active()),'missing quality alert')
        for _ in range(12):
            current=next((e for e in self.active() if e['rule_id']==rid),None)
            assert current and current['id']==event['id'] and current['hash']==event['hash']
            assert not any(e.get('is_recovered') and e['hash']==event['hash'] for e in self.notifications(started))
            time.sleep(1)
        self.scenario('recover')
        self.wait(lambda:not self.active(),'held thermal did not clear')
        report['cases'].append({'scenario':'thermal_then_missing','passed':True,'active_event_id':event['id'],
                                 'hash':event['hash'],'held_seconds':round(time.time()-started,3)})
        print('PASS 温度异常后缺数保持同一事件',flush=True)

    def hysteresis(self,report):
        self.baseline();rid=BINDING['rule_ids']['training.gpu_thermal'];self.scenario('gpu_thermal')
        event=self.wait(lambda:next((e for e in self.active() if e['rule_id']==rid),None),'hysteresis start')
        self.scenario('thermal_hysteresis');time.sleep(12)
        current=next((e for e in self.active() if e['rule_id']==rid),None)
        assert current and current['id']==event['id']
        self.scenario('recover');self.wait(lambda:not self.active(),'hysteresis clear')
        report['cases'].append({'scenario':'thermal_hysteresis_band','passed':True,'active_event_id':event['id']})
        print('PASS 温度解除回差',flush=True)

    def xid_context(self,report):
        self.baseline();rid=BINDING['rule_ids']['training.xid_node'];self.scenario('xid_node')
        event=self.wait(lambda:next((e for e in self.active() if e['rule_id']==rid),None),'xid start')
        started=time.time();self.scenario('xid_context');time.sleep(12)
        current=next((e for e in self.active() if e['rule_id']==rid),None)
        assert current and current['id']==event['id']
        assert not any(e.get('is_recovered') and e['hash']==event['hash'] for e in self.notifications(started))
        self.scenario('normal');time.sleep(8)
        assert any(e['id']==event['id'] for e in self.active()),'code zero without recovery confirmation resolved incident'
        self.scenario('recover');self.wait(lambda:not self.active(),'xid confirmed clear')
        report['cases'].append({'scenario':'xid79_then45_then_zero_requires_confirmation','passed':True,'active_event_id':event['id']})
        print('PASS XID事件关联与恢复确认',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',default='all',help='all, hardware, quality, platform, semantics, or a rule scenario')
    args=parser.parse_args()
    report={'scope':'H100_training_comprehensive_simulation','selection':args.case,'passed':False,
            'catalog_sha256':BINDING['catalog_sha256'],'cases':[],'started_at':time.time(),
            'nightingale_version':'9.3.0','real_h100_tests':'not_run'}
    runner=Runner()
    try:
        if args.case in ('all','hardware') or args.case in [r['scenario'] for r in CATALOG['rules']]:
            for row in CATALOG['rules']:
                if row['kind']!='stateful':continue
                if args.case not in ('all','hardware',row['scenario']):continue
                entity=row['entity_ids'][0]
                runner.fault(row['scenario'],BINDING['rule_ids'][row['rule_id']],report,entity)
        if args.case in ('all','quality'):
            for scenario,key in [('field_missing','field_missing'),('entity_missing','entity_missing'),
                                 ('input_invalid','input_invalid'),('input_stale','input_stale'),
                                 ('input_duplicate','input_duplicate'),('collector_down','collector_down'),
                                 ('missing_link','entity_missing'),('hbm_limit_missing','field_missing'),('switch_unknown','input_invalid'),('switch_missing','entity_missing'),('thermal_pending_missing','entity_missing')]:
                runner.fault(scenario,BINDING['rule_ids']['training.'+key],report)
        if args.case in ('all','platform'):
            for scenario,key in [('query_failure','platform_query_failure'),
                                 ('evaluation_stall','platform_evaluation_stall'),
                                 ('notification_failure','platform_notify_failure'),('engine_metrics_failure','platform_nightingale_metrics_missing')]:
                runner.fault(scenario,BINDING['health_rule_ids'][key],report)
        if args.case in ('all','semantics'):
            runner.quiet('thermal_transient',report)
            runner.quiet('unused_port',report)
            runner.quiet('idle_pcie',report)
            runner.hold_after_missing(report)
            runner.hysteresis(report)
            runner.xid_context(report)
        report['passed']=True
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        print('FAIL '+report['error'],flush=True)
    finally:
        try:
            runner.scenario('recover')
            runner.wait(lambda:not runner.active(),'cleanup has active events',timeout=110)
        except Exception as error:
            report['cleanup_error']=str(error)
        report['finished_at']=time.time()
        path=Path('/results/comprehensive-'+args.case+'.json')
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('报告 .local/reports/'+path.name,flush=True)
    return 0 if report['passed'] and not report.get('cleanup_error') else 1


if __name__=='__main__':
    def stop(signum,frame):raise RuntimeError('测试收到终止信号')
    signal.signal(signal.SIGTERM,stop)
    raise SystemExit(main())
