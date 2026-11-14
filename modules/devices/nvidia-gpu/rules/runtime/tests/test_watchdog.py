import json,tempfile,unittest
from pathlib import Path
from npumonitor_rules.watchdog import Watchdog

class Response:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return b'ok'
class Transport:
    def __init__(self):self.target=True;self.delivery=True;self.messages=[]
    def open(self,request,**kwargs):
        if isinstance(request,str):
            if not self.target:raise OSError('target down')
        else:
            self.messages.append(json.loads(request.data))
            if not self.delivery:raise OSError('receiver down')
        return Response()
class WatchdogTests(unittest.TestCase):
    def test_ordered_outbox_survives_restart_and_retries_same_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);token=root/'token';token.write_text('synthetic-unit-credential-only')
            cfg={'targets':[{'name':'runtime','url':'http://runtime/ready'}],'callback_url':'http://receiver/webhook','callback_token_file':str(token),'failure_count':2,'repeat_seconds':3600}
            path=root/'watchdog.sqlite';Watchdog.initialize(path,cfg,'test');transport=Transport();watch=Watchdog(path,cfg,'test');watch.opener=transport
            watch.tick();transport.target=False;transport.delivery=False
            self.assertEqual(watch.tick()['pending'],0)
            self.assertEqual(watch.tick()['pending'],1)
            event=transport.messages[-1];watch=Watchdog(path,cfg,'test');watch.opener=transport
            transport.target=True;self.assertEqual(watch.tick()['pending'],2)
            self.assertEqual(transport.messages[-1]['event_id'],event['event_id'])
            transport.delivery=True;watch.tick();watch.tick()
            self.assertEqual(watch.status()['pending'],0)
            self.assertEqual([m['status'] for m in transport.messages[-2:]],['firing','resolved'])
            self.assertEqual(transport.messages[-1]['episode'],event['episode'])
    def test_missing_database_and_changed_binding_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'watchdog.sqlite';cfg={'targets':[{'name':'runtime','url':'http://runtime/ready'}],'callback_url':'http://receiver/webhook'}
            with self.assertRaises(Exception):Watchdog(path,cfg,'test')
            Watchdog.initialize(path,cfg,'test')
            with self.assertRaises(ValueError):Watchdog(path,{**cfg,'failure_count':9},'test')
            path.unlink()
            with self.assertRaises(Exception):Watchdog(path,cfg,'test')
