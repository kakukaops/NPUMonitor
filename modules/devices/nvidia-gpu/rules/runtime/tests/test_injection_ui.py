import copy,importlib.util,json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from test_runtime import ROOT

class InjectionUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name)
        catalog=p/'catalog.json';catalog.write_text((ROOT/'runtime/master/catalog.json').read_text())
        token=p/'token';token.write_text('private-test-token')
        self.env=patch.dict(os.environ,{'FIXTURE_UI':'true','FIXTURE_DATA':str(p),'FIXTURE_CATALOG_FILE':str(catalog),'FIXTURE_TOKEN_FILE':str(token),'FIXTURE_MODE':'source'});self.env.start()
        spec=importlib.util.spec_from_file_location('ui_fixture',ROOT/'runtime/reference/fixture.py');self.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mod)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.mod.Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop();self.tmp.cleanup()
    def request(self,path,body=None,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        req=Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with urlopen(req,timeout=5) as r:return r.status,r.read().decode()
        except HTTPError as e:return e.code,e.read().decode()
    def test_ui_does_not_expose_token_or_open_existing_admin_api(self):
        code,text=self.request('/');self.assertEqual(code,200);self.assertIn('手动故障注入',text);self.assertNotIn('private-test-token',text)
        self.assertEqual(self.request('/state')[0],401)
        self.assertEqual(self.request('/control',{'scenario':'xid'})[0],401)
        self.assertEqual(self.request('/ui/control',{'scenario':'xid'})[0],403)
        self.assertEqual(self.request('/ui/control',{'scenario':'xid'},'http://evil.example')[0],403)
        with patch.dict(os.environ,{'FIXTURE_UI':'false'}):self.assertEqual(self.request('/')[0],401)
    def test_selected_gpu_xid_repeated_event_and_stop(self):
        for count in [1,2]:
            code,_=self.request('/ui/control',{'scenario':'xid','target_index':1},self.base);self.assertEqual(code,200)
            state=json.loads(self.request('/ui/state')[1]);self.assertEqual(len(state['events']),count);self.assertEqual(state['events'][-1]['UUID'],'GPU-CONTRACT-0001')
        text=self.request('/metrics')[1]
        self.assertIn('DCGM_FI_DEV_XID_ERRORS{UUID="GPU-CONTRACT-0000"} 0',text)
        self.assertIn('DCGM_FI_DEV_XID_ERRORS{UUID="GPU-CONTRACT-0001"} 79',text)
        self.assertEqual(self.request('/ui/control',{'scenario':'baseline','target_index':1},self.base)[0],200)
        self.assertEqual(len(json.loads(self.request('/ui/state')[1])['events']),2)
    def test_precise_counter_and_invalid_target(self):
        payload={'scenario':'baseline','target_index':0,'counter_activity':[{'metric':'DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL','identity':{'UUID':'GPU-CONTRACT-0000'},'rate_per_second':2}]}
        self.assertEqual(self.request('/ui/control',payload,self.base)[0],200)
        self.assertEqual(json.loads(self.request('/ui/state')[1])['counter_activity'][0]['rate_per_second'],2)
        self.assertEqual(self.request('/ui/control',{'target_index':999},self.base)[0],422)
