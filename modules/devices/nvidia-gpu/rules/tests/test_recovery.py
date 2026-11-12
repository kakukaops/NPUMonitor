"""Persistence and fail-closed lifecycle invariants, independent of Nightingale."""
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
from http.server import ThreadingHTTPServer
LAB=Path('/app') if Path('/app/recovery_adapter.py').exists() else Path(__file__).resolve().parents[1]/'lab'
sys.path.insert(0,str(LAB))
from recovery_adapter import Store,parse_observation,Handler


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite'
        self.config={'scope':'simulation-only','production_admitted':False,'cluster_id':'fixture',
                     'uuids':['a','b'],'max_poll_age_seconds':30,'rules':[{'rule_id':'sram','metric_name':'flag'}]}
        self.store=Store(self.path,self.config,initialize=True)

    def test_fired_then_missing_invalid_query_error_never_clears_until_valid_zero(self):
        self.store.apply({'sram':{'a':1,'b':0}},now=100)
        for now,obs in [(105,{}),(110,{'a':float('nan')}),(115,None)]:
            self.store.apply({'sram':obs},now=now)
            self.assertEqual(len(self.store.vector('sram',now=now)),1)
        self.store.apply({'sram':{'a':0}},now=120)
        self.assertEqual(self.store.vector('sram',now=120),[])
        self.assertEqual(self.store.snapshot()['transitions'][-1]['reason'],'flag_asserted')

    def test_restart_and_unknown_preserve_state_and_device_isolation(self):
        self.store.apply({'sram':{'a':1,'b':0}},now=100)
        restarted=Store(self.path,self.config)
        restarted.apply({'sram':{'b':1}},now=110)
        self.assertEqual({v['metric']['UUID'] for v in restarted.vector('sram',now=110)},{'a','b'})
        restarted.apply({'sram':{'a':0}},now=115)
        self.assertEqual([v['metric']['UUID'] for v in restarted.vector('sram',now=115)],['b'])

    def test_missing_database_binding_change_and_double_init_refuse_reset(self):
        with self.assertRaises(sqlite3.OperationalError):Store(Path(self.tmp.name)/'missing.sqlite',self.config)
        with self.assertRaises(ValueError):Store(self.path,self.config,initialize=True)
        changed=dict(self.config,uuids=['a'])
        with self.assertRaises(ValueError):Store(self.path,changed)

    def test_running_store_rejects_binding_replacement_instead_of_returning_empty(self):
        self.store.apply({'sram':{'a':1}},now=100)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE meta SET value='other-binding' WHERE key='binding'")
        with self.assertRaises(ValueError):self.store.vector('sram',now=100)

    def test_rule_specific_entities_preserve_switch_identity(self):
        config=dict(self.config,uuids=['gpu','switch'],identity_label='entity_id',
                    entity_labels={'gpu':{'UUID':'gpu','entity_type':'gpu'},
                                   'switch':{'switch_id':'switch','entity_type':'nvswitch'}},
                    rules=[{'rule_id':'gpu_rule','metric_name':'flag','entity_ids':['gpu']},
                           {'rule_id':'switch_rule','metric_name':'flag','entity_ids':['switch']}])
        store=Store(Path(self.tmp.name)/'entities.sqlite',config,initialize=True)
        store.apply({'gpu_rule':{'gpu':1},'switch_rule':{'switch':1}},now=100)
        self.assertEqual(len(store.snapshot()['states']),2)
        labels=store.vector('switch_rule',now=100)[0]['metric']
        self.assertEqual(labels['switch_id'],'switch')
        self.assertNotIn('UUID',labels)
        payload={'status':'success','data':{'resultType':'vector','result':[
            {'metric':{'entity_id':'switch','cluster_id':'fixture','metric_name':'flag'},'value':[100,'1']}]}}
        self.assertEqual(parse_observation(payload,config,config['rules'][1]),{'switch':1})
        with self.assertRaises(ValueError):parse_observation(payload,config,config['rules'][0])

    def test_confirmation_requires_continuous_valid_observations_and_survives_restart(self):
        config=dict(self.config,maximum_confirmation_gap_seconds=6,
                    rules=[{'rule_id':'sram','metric_name':'flag','confirm_seconds':10}])
        path=Path(self.tmp.name)/'confirmation.sqlite'
        store=Store(path,config,initialize=True)
        store.apply({'sram':{'a':1}},now=100)
        store.apply({'sram':{'a':1}},now=105)
        self.assertEqual(store.vector('sram',now=105),[])
        restarted=Store(path,config)
        restarted.apply({'sram':{'a':1}},now=110)
        self.assertEqual(len(restarted.vector('sram',now=110)),1)
        restarted.apply({'sram':{}},now=112)
        self.assertEqual(len(restarted.vector('sram',now=112)),1)
        restarted.apply({'sram':{'a':0}},now=115)
        self.assertEqual(restarted.vector('sram',now=115),[])
        restarted.apply({'sram':{'a':1}},now=120)
        restarted.apply({'sram':{}},now=125)
        self.assertFalse(restarted.snapshot()['pending'])
        restarted.apply({'sram':{'a':1}},now=130)
        restarted.apply({'sram':{'a':1}},now=140)
        self.assertEqual(restarted.vector('sram',now=140),[])

    def test_old_or_future_poller_heartbeat_is_error_not_empty_success(self):
        self.store.apply({'sram':{'a':1}},now=100)
        for now in [99,131]:
            with self.assertRaises(RuntimeError):self.store.vector('sram',now=now)

    def test_real_http_get_post_probe_and_storage_failure_contract(self):
        self.store.apply({'sram':{'a':1,'b':0}})
        handler=type('TestHandler',(Handler,),{'store':self.store,'stop':threading.Event()})
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)+'/api/v1/query'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            data=urllib.parse.urlencode({'query':'gpu_lifecycle_active{lifecycle_rule_id="sram"}'}).encode()
            for req in [urllib.request.Request(base+'?'+data.decode()),urllib.request.Request(base,data=data)]:
                with opener.open(req,timeout=3) as response:result=json.load(response)
                self.assertEqual(result['data']['result'][0]['metric']['UUID'],'a')
                self.assertEqual(result['data']['result'][0]['value'][1],'1')
            with opener.open(base+'?'+urllib.parse.urlencode({'query':'1+1'})) as response:
                self.assertEqual(json.load(response)['data']['result'][1],'2')
            with self.assertRaises(urllib.error.HTTPError) as error:
                opener.open(base+'?'+urllib.parse.urlencode({'query':'unsupported'}))
            self.assertEqual(error.exception.code,422)
            moved=self.path.with_suffix('.backup');self.path.rename(moved)
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:opener.open(base+'?'+data.decode())
                self.assertEqual(error.exception.code,503)
            finally:moved.rename(self.path)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

    def test_duplicate_unknown_identity_nan_and_warnings_reject_observation(self):
        rule=self.config['rules'][0]
        def payload(rows,warnings=None):
            p={'status':'success','data':{'resultType':'vector','result':rows}}
            if warnings:p['warnings']=warnings
            return p
        row={'metric':{'UUID':'a','cluster_id':'fixture','metric_name':'flag'},'value':[1,'1']}
        self.assertEqual(parse_observation(payload([row]),self.config,rule),{'a':1})
        for p in [payload([row,row]),payload([dict(row,metric=dict(row['metric'],UUID='other'))]),
                  payload([dict(row,value=[1,'NaN'])]),payload([row],['partial data'])]:
            with self.assertRaises(ValueError):parse_observation(p,self.config,rule)


if __name__=='__main__':unittest.main()
