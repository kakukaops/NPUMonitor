"""Streaming acceptance: real scrape, exact identities, Nightingale and local webhook."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time
import urllib.parse
from n9e import API, unique
from suite import request, notifications, tags

GROUP='H100草案模拟验收'
URL='http://gpu-simulator:9400/batch1/'
FIELD='DCGM_FI_DEV_SRAM_EXCEEDED'
UUID0, UUID1='GPU-BATCH1-0000','GPU-BATCH1-0001'


def select(name):
    request(URL+'scenario', {'name':name})
    print('场景：'+name, flush=True)


def pair(event):
    t=tags(event)
    return (t.get('rule_id'), t.get('UUID'), t.get('metric_name'))


def expected(name, uuid=None, field=None):
    return ('batch1_'+name,uuid,field)


class Runner:
    def __init__(self):
        self.api=API()
        bg=unique(self.api.call('GET','/busi-groups?all=true&limit=1000'),GROUP)
        if not bg: raise ValueError('先运行 batch1 import')
        self.gid=bg['id']
        rows=self.api.call('GET',f'/busi-group/{self.gid}/alert-rules')
        catalog=json.loads(Path('/rules/batch1-lab-catalog.json').read_text())
        self.ids=set()
        for item in catalog['rules']:
            row=unique(rows,item['name'])
            if not row or row['disabled']: raise ValueError('规则缺失/禁用：'+item['key'])
            actual=row['rule_config']['queries'][0]['prom_ql']
            if actual!=item['expression'] or row['prom_for_duration']!=item['for_seconds'] or row['prom_eval_interval']!=item['eval_interval_seconds']:
                raise ValueError('规则被修改；停止，不覆盖：'+item['key'])
            self.ids.add(row['id'])
        self.catalog=catalog

    def baseline(self):
        # Label changes on restart can leave old series visible for the 5m lookback.
        deadline=time.monotonic()+360
        while time.monotonic()<deadline:
            hits=[]
            for item in self.catalog['rules']:
                result=request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':item['expression']}))
                if result['data']['result']: hits.append(item['key'])
            if not hits and not self.active(): return
            time.sleep(2)
        raise ValueError('normal基线未清除：'+str(hits))

    def active(self):
        return [e for e in self.api.call('GET',f'/alert-cur-events/list?bgid={self.gid}&hours=24&limit=100')['list'] if e['rule_id'] in self.ids]

    def clear(self):
        deadline=time.monotonic()+130
        while self.active():
            if time.monotonic()>deadline: raise TimeoutError('批次告警未清除')
            time.sleep(2)

    def events(self,since):
        rows=[(at,e) for at,e in notifications(since) if e.get('rule_id') in self.ids]
        if any(tags(e).get('cluster_id')!='batch1-sim-lab' for _,e in rows):
            raise ValueError('通知集群身份不符')
        return rows

    def wait(self,since,wanted,recovered,timeout=160):
        deadline=time.monotonic()+timeout
        found={}
        while time.monotonic()<deadline:
            for at,e in self.events(since):
                p=pair(e)
                if not e.get('is_recovered') and p not in wanted:
                    raise ValueError('旁路误报：'+str(p))
                if p in wanted and e.get('is_recovered') is recovered:
                    found[p]={'identity':list(p),'hash':e['hash'],'received_at':at,
                              'raw_is_recovered':recovered}
            if set(found)==wanted: return found
            time.sleep(2)
        raise TimeoutError('通知缺失：'+str(wanted-set(found)))

    def fault(self,name,wanted,report):
        self.clear();started=time.time();select(name)
        case={'scenario':name,'started_at':started,'passed':False};report['cases'].append(case)
        fired=self.wait(started,wanted,False)
        delay=time.time()-started
        case.update(firing_after_seconds=round(delay,2),firing=list(fired.values()))
        if name not in ('sram','remap') and any(e['received_at']-started<58 for e in fired.values()):
            raise ValueError('未满足60秒持续时间即触发')
        since=time.time();select('normal')
        exited=self.wait(since,wanted,True,130)
        assert all(fired[p]['hash']==exited[p]['hash'] for p in wanted)
        self.clear()
        case.update(passed=True,firing_after_seconds=round(delay,2),
                    exit_after_seconds=round(time.time()-since,2),
                    firing=list(fired.values()),condition_exit=list(exited.values()))
        print('PASS: '+name+' 触发、结束、身份、无旁路误报',flush=True)

    def quiet(self,report):
        self.clear();since=time.time();select('transient_invalid');saw=False
        case={'scenario':'transient_invalid','passed':False};report['cases'].append(case)
        while time.time()-since<100:
            query='DCGM_FI_DEV_SRAM_EXCEEDED{job="h100-batch1-simulator",UUID="'+UUID0+'"}'
            values=request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':query}))['data']['result']
            saw |= any(v['value'][1]=='NaN' for v in values)
            if self.active() or any(not e.get('is_recovered') for _,e in self.events(since)):
                raise ValueError('15秒异常未被60秒for抑制')
            time.sleep(2)
        assert saw,'未采到NaN，不能判为抑制成功'
        case.update(passed=True,saw_invalid_sample=True,observed_seconds=round(time.time()-since,2))
        select('normal');print('PASS: 短暂异常被for抑制',flush=True)

    def lost_after_fault(self,report):
        self.clear();since=time.time();select('sram')
        hardware={expected('sram_threshold_exceeded',UUID0,FIELD)}
        fired=self.wait(since,hardware,False)
        since=time.time();select('field_missing')
        quality={expected('required_field_missing',UUID0,FIELD)}
        # Raw Nightingale recovery is explicitly an expression exit, not a repair assertion.
        deadline=time.monotonic()+160;exit_event=None;quality_event=None
        while time.monotonic()<deadline:
            for at,e in self.events(since):
                p=pair(e)
                if p not in hardware|quality: raise ValueError('旁路事件：'+str(p))
                if p in hardware and e.get('is_recovered'):
                    exit_event={'hash':e['hash'],'raw_is_recovered':True,'received_at':at}
                if p in quality and not e.get('is_recovered'):
                    quality_event={'hash':e['hash'],'received_at':at}
            if exit_event and quality_event: break
            time.sleep(2)
        assert exit_event and quality_event,'缺少硬件条件退出或质量触发事件'
        assert exit_event['hash']==next(iter(fired.values()))['hash']
        query='DCGM_FI_DEV_SRAM_EXCEEDED{job="h100-batch1-simulator",UUID="'+UUID0+'"}'
        values=request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':query}))['data']['result']
        assert not values,'缺数证据不成立'
        report['cases'].append({'scenario':'sram_then_field_missing','passed':True,
            'raw_exit':exit_event,'quality_trigger':quality_event,'current_field_query_result':[],
            'interpretation':'input_unjudgeable_not_hardware_recovered',
            'production_gate':'native_recovered_flag_is_not_safe_hardware_recovery_semantics'})
        since=time.time();select('normal');self.wait(since,quality,True,130);self.clear()
        print('PASS: 复现异常后缺数；原生结束不代表硬件恢复',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=['all','smoke','stale','lifecycle'],default='all');args=parser.parse_args()
    report={'started_at':datetime.now(timezone.utc).isoformat(),'selection':args.case,'cases':[],
            'scope':'streaming_simulation_only','passed':False,'real_h100_tests':'not_run'}
    changed=False
    try:
        assert request(URL+'state')['scenario']=='normal','已有手工场景，停止避免覆盖'
        runner=Runner();runner.baseline();report['catalog_version']=runner.catalog['catalog_version'];report['catalog_source_sha256']=runner.catalog['source_sha256']
        changed=True
        if args.case in ('all','smoke'):
            runner.fault('sram',{expected('sram_threshold_exceeded',UUID0,FIELD)},report)
            runner.fault('remap',{expected('row_remap_failed',UUID0,'DCGM_FI_DEV_ROW_REMAP_FAILURE')},report)
        if args.case=='all':
            runner.quiet(report)
            for name,wanted in [
                ('invalid',{expected('required_input_invalid',UUID0,FIELD)}),
                ('duplicate',{expected('duplicate_input_series',UUID0,FIELD)}),
                ('field_missing',{expected('required_field_missing',UUID0,FIELD)}),
                ('device_missing',{expected('expected_gpu_observation_missing',UUID1)}),
                ('empty',{expected('expected_gpu_observation_missing',UUID0),expected('expected_gpu_observation_missing',UUID1)}),
                ('scrape_error',{expected('collector_unavailable')})]:
                runner.fault(name,wanted,report)
        if args.case in ('all','stale'):
            runner.fault('stale',{expected('required_field_stale',UUID0,FIELD)},report)
        if args.case in ('all','lifecycle'): runner.lost_after_fault(report)
        report['passed']=True
    except Exception as error:
        report['error']=str(error);print('FAIL: '+str(error),flush=True)
    finally:
        if changed:
            try: select('normal')
            except Exception as error: report['cleanup_error']=str(error)
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        path=Path('/results/batch1-'+args.case+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('报告：.local/reports/'+path.name,flush=True)
    if report['passed'] and args.case=='all':
        try:
            import batch1_audit
        except Exception as error:
            report.update(passed=False,postflight_error=str(error))
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print('FAIL: postflight '+str(error),flush=True)
    return 0 if report['passed'] and not report.get('cleanup_error') else 1


if __name__=='__main__':
    def stop(signum,frame): raise RuntimeError('验收收到终止信号')
    signal.signal(signal.SIGTERM,stop)
    raise SystemExit(main())
