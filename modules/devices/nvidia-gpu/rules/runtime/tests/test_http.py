import copy,json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from test_runtime import config,ROOT
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.store import Store
from npumonitor_rules.server import BoundedServer,Handler

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);(root/'admin').write_text('a'*40);(root/'viewer').write_text('v'*40)
        c=config();c['gateway'].update(admin_token_file=str(root/'admin'),viewer_token_file=str(root/'viewer'))
        b=compile_bundle(c,ROOT);Store.initialize(root/'state.sqlite',b);store=Store(root/'state.sqlite','unit')
        self.server=BoundedServer(('127.0.0.1',0),Handler);self.server.store=store;self.server.candidate=str(root/'candidate.json');(root/'candidate.json').write_text(json.dumps(b))
        class Engine:
            preflight={}
            def readiness(self):return {'ready':True}
        self.server.engine=Engine();self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def call(self,path,token=None,body=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        return urlopen(Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=3)
    def test_anonymous_liveness_only_and_reader_cannot_administer(self):
        self.assertEqual(self.call('/health').status,200)
        metrics=self.call('/metrics');self.assertIn('text/plain',metrics.headers['Content-Type']);self.assertIn(b'npumonitor_rules_ready 1',metrics.read())
        with self.assertRaises(HTTPError) as e:self.call('/state')
        self.assertEqual(e.exception.code,401)
        with self.assertRaises(HTTPError) as e:self.call('/admin/backup','v'*40,{})
        self.assertEqual(e.exception.code,403)
    def test_scalar_probe_and_reject_arbitrary_historical_queries(self):
        self.assertEqual(json.load(self.call('/api/v1/query?query=1%2B1','v'*40))['data']['result'][1],'2')
        with self.assertRaises(HTTPError) as e:self.call('/api/v1/query?query=up','v'*40)
        self.assertEqual(e.exception.code,422)
        with self.assertRaises(HTTPError):self.call('/api/v1/query?query=1%2B1&time=1','v'*40)
    def test_lost_database_returns_error_not_empty_success(self):
        self.server.store.path.unlink()
        with self.assertRaises(HTTPError) as e:self.call('/api/v1/query?query=1%2B1','v'*40)
        self.assertEqual(e.exception.code,503)
