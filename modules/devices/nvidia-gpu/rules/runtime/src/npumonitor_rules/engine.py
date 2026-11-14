"""Bounded polling, paired source clocks and explicit deployment coverage."""
from concurrent.futures import ThreadPoolExecutor
import threading,time
from .bundle import expand_recovery
from .source import Source,normalize
from .store import Conflict

class Engine:
    def __init__(self,store):
        self.store=store;self.stop=threading.Event();self.lock=threading.RLock();self.source=None;self.sha=None;self.preflight=None;self.fatal=None;self.last_duration=0
    def cycle(self):
        began=time.time();bundle,generation=self.store.current();config=bundle['config'];limits=config['limits']
        with self.lock:
            if self.sha!=bundle['sha256']:
                self.source=Source(bundle);self.sha=bundle['sha256'];self.preflight=None
            source=self.source
        if self.preflight is None or began-self.preflight.get('checked_at',0)>=limits['preflight_seconds']:
            try:self.preflight=source.preflight()
            except Exception as exc:
                self.preflight={'checked_at':began,'error':type(exc).__name__,'rules':{},'has_device_data':False}
        preflight=self.preflight
        def fetch(rule):
            if not rule['enabled']:return {'rule_id':rule['rule_id'],'samples':[]}
            if preflight.get('error'):return {'rule_id':rule['rule_id'],'samples':None,'error':'upstream_unavailable'}
            status=preflight['rules'][rule['rule_id']]['status']
            if status!='ready':return {'rule_id':rule['rule_id'],'samples':None,'unavailable':status}
            try:
                expression=expand_recovery(rule,self.store.actions(rule['rule_id'],began))
                at=time.time()
                if rule['kind']=='stateful':
                    expression='label_replace(('+expression+'),"sre_result_kind","value","__name__",".*") or label_replace(('+rule['clock_expression']+'),"sre_result_kind","clock","__name__",".*")'
                rows=source.query(expression,at)
                return {'rule_id':rule['rule_id'],'samples':normalize(rule,rows,at)}
            except Exception as exc:return {'rule_id':rule['rule_id'],'samples':None,'error':type(exc).__name__}
        with ThreadPoolExecutor(max_workers=limits['query_workers'],thread_name_prefix='sre-query') as pool:results=list(pool.map(fetch,bundle['rules']))
        self.store.apply_cycle(results,generation,time.time());self.last_duration=time.time()-began;self.fatal=None
        return {'generation':generation,'duration_seconds':self.last_duration,'rules':len(results),'query_errors':sum(bool(r.get('error')) for r in results)}
    def run(self):
        while not self.stop.is_set():
            began=time.monotonic()
            try:self.cycle()
            except Conflict:continue
            except Exception as exc:self.fatal=type(exc).__name__
            try:delay=self.store.current()[0]['config']['limits']['poll_seconds']
            except Exception:delay=5
            self.stop.wait(max(.1,delay-(time.monotonic()-began)))
    def readiness(self):
        h=self.store.health();p=self.preflight or {}
        ready=(p.get('production_contract') or {'ready':True})['ready'] and h['cycle_fresh'] and not self.fatal and not h['errors'] and p.get('has_device_data',False)
        return {'ready':ready,'state':h,'coverage':p,'fatal':self.fatal,'last_cycle_seconds':self.last_duration,'source_stats':self.source.stats if self.source else {}}
