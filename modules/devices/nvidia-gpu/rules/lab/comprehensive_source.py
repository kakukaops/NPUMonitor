"""Local synthetic collector, webhook fault injection, and read-only demonstration UI."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from comprehensive_model import Model
from n9e import API, unique
from receiver import Store

ROOT = Path('/rules')
RUNTIME = ROOT/'comprehensive-runtime.json'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = Model()
ATTEMPTS = Store('/data/comprehensive-attempts.jsonl')
COUNTER_PATH = Path('/data/comprehensive-notifications.json')
COUNTER_LOCK = threading.Lock()
COUNTERS = json.loads(COUNTER_PATH.read_text()) if COUNTER_PATH.exists() else {'failed':0,'delivered':0}
WATCH_LOCK = threading.Lock()
WATCH = {'engine_up':0,'prometheus_up':0,'adapter_up':0,'checked_at':0,'incidents':[]}


def request(url, data=None, timeout=4):
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                 headers={'Content-Type':'application/json'})
    with OPENER.open(req, timeout=timeout) as response:
        return json.load(response)


def runtime():
    return json.loads(RUNTIME.read_text()) if RUNTIME.exists() else {}


def record_attempt(payload, failed):
    status = 'failed' if failed else 'delivered'
    ATTEMPTS.append({'status':status,'events':payload})
    with COUNTER_LOCK:
        COUNTERS[status] += 1
        temporary=COUNTER_PATH.with_suffix('.tmp')
        temporary.write_text(json.dumps(COUNTERS))
        temporary.replace(COUNTER_PATH)


def watchdog():
    endpoints={'engine_up':'http://nightingale:17000/',
               'prometheus_up':'http://prometheus:9090/-/ready',
               'adapter_up':'http://comprehensive-lifecycle:9410/health'}
    while True:
        values={}
        for name,url in endpoints.items():
            try:
                with OPENER.open(url,timeout=2) as response:
                    values[name]=int(response.status==200)
            except Exception:
                values[name]=0
        with WATCH_LOCK:
            for name,value in values.items():
                if WATCH[name]!=value:
                    WATCH['incidents'].append({'component':name,'available':bool(value),'time':time.time()})
            WATCH.update(values,checked_at=time.time())
            WATCH['incidents']=WATCH['incidents'][-30:]
        time.sleep(2)


def event_summary(event):
    return {key:event.get(key) for key in ('id','rule_id','rule_name','is_recovered','trigger_value',
                                         'trigger_time','recover_time','hash','tags','tags_map','severity')}


def status():
    config=runtime()
    state={'rule_titles':{r['rule_id']:r['title'] for r in MODEL.catalog['rules']},'model':MODEL.state(),'scenarios':MODEL.modes(),'runtime':config,
           'notifications':ATTEMPTS.recent()[-25:]}
    with COUNTER_LOCK:
        state['notification_counts']=dict(COUNTERS)
    with WATCH_LOCK:
        state['watchdog']=dict(WATCH)
    try:
        state['lifecycle']=request('http://comprehensive-lifecycle:9410/state',timeout=1)
    except Exception:
        state['lifecycle']={'unavailable':True}
    if config.get('group_id'):
        try:
            api=API(timeout=3)
            current=api.call('GET',f'/alert-cur-events/list?bgid={config["group_id"]}&hours=24&limit=100')
            history=api.call('GET',f'/alert-his-events/list?bgid={config["group_id"]}&hours=24&limit=30')
            state['alerts']=[event_summary(e) for e in current['list'] if e['rule_id'] in config['managed_rule_ids']]
            state['history']=[event_summary(e) for e in history['list'] if e['rule_id'] in config['managed_rule_ids']]
        except Exception:
            state['api_error']='夜莺事件接口暂不可用'
    try:
        backup=request('http://notification-receiver:9080/events',timeout=1)['events']
        health_ids=set(config.get('health_rule_ids',{}).values())
        state['backup_notifications']=[{'received_at':r['received_at'],'events':[event_summary(e) for e in r['payload'] if e.get('rule_id') in health_ids]}
                                       for r in backup if isinstance(r['payload'],list) and any(e.get('rule_id') in health_ids for e in r['payload'])][-10:]
    except Exception:
        state['backup_notifications']=[]
    return state


def select(mode):
    if mode not in MODEL.modes():
        raise ValueError('unknown scenario')
    config=runtime()
    if config.get('probe_rule_id'):
        api=API()
        row=api.call('GET',f'/alert-rule/{config["probe_rule_id"]}/pure')
        if row.get('annotations',{}).get('managed_by')!='gpu-alert-lab':
            raise ValueError('probe owner mismatch')
        desired=3600 if mode=='evaluation_stall' else 5
        if row.get('cron_pattern','') not in ('','@every 5s','@every 3600s'):
            raise ValueError('probe schedule was locally edited')
        if row['prom_eval_interval'] not in (5,3600):
            raise ValueError('probe interval was locally edited')
        if row['prom_eval_interval']!=desired:
            row['prom_eval_interval']=desired
            row['cron_pattern']=f'@every {desired}s'
            api.call('PUT',f'/busi-group/{config["group_id"]}/alert-rule/{row["id"]}',row)
    return MODEL.select(mode)


class Handler(BaseHTTPRequestHandler):
    def reply(self,status,body,content_type='application/json'):
        data=body.encode() if isinstance(body,str) else json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parts=urllib.parse.urlsplit(self.path)
        if parts.path=='/health':
            self.reply(200,{'ok':True,'simulated':True})
        elif parts.path=='/metrics':
            with COUNTER_LOCK:
                counts=dict(COUNTERS)
            code,body=MODEL.snapshot(counts)
            if code==200:
                with WATCH_LOCK:
                    for name in ['engine_up','prometheus_up','adapter_up']:
                        body+=f'DEMO_{name.upper()} {WATCH[name]}\n'
            self.reply(code,body,'text/plain; version=0.0.4')
        elif parts.path=='/nightingale/metrics':
            if MODEL.state()['scenario']=='engine_metrics_failure':
                self.reply(503,'injected metrics transport failure','text/plain')
                return
            try:
                with OPENER.open('http://nightingale:17000/metrics',timeout=3) as response:
                    self.reply(200,response.read().decode(),'text/plain; version=0.0.4')
            except Exception:
                self.reply(503,'nightingale metrics unavailable','text/plain')
        elif parts.path=='/api/views':
            results=[]
            for view in json.loads((ROOT/'comprehensive-views.json').read_text())['views']:
                try:
                    query=urllib.parse.urlencode({'query':view['expression']})
                    result=request('http://prometheus:9090/api/v1/query?'+query)
                    results.append({'query_id':view['query_id'],'status':result['status'],
                                    'result':result.get('data',{}).get('result',[])})
                except Exception:
                    results.append({'query_id':view['query_id'],'status':'error','result':[]})
            self.reply(200,{'simulated':True,'views':results})
        elif parts.path=='/api/status':
            self.reply(200,status())
        elif parts.path=='/api/model':
            self.reply(200,MODEL.state())
        elif parts.path=='/api/attempts':
            self.reply(200,{'records':ATTEMPTS.recent(),'counts':dict(COUNTERS)})
        elif parts.path=='/api/v1/query':
            self.proxy_query(urllib.parse.parse_qs(parts.query))
        elif parts.path=='/':
            self.reply(200,Path('/app/comprehensive_demo.html').read_text(),'text/html; charset=utf-8')
        else:
            self.reply(404,{'error':'not found'})

    def proxy_query(self,params):
        query=params.get('query',[''])[0]
        allowed={'1+1','DEMO_PROBE_INPUT{job="h100-comprehensive"} > 1'}
        if query not in allowed:
            self.reply(422,{'status':'error','errorType':'bad_data','error':'unsupported probe query'})
            return
        if query!='1+1' and MODEL.state()['scenario']=='query_failure':
            self.reply(503,{'status':'error','error':'injected query backend outage'})
            return
        try:
            url='http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode(params,doseq=True)
            with OPENER.open(url,timeout=5) as response:
                self.reply(200,json.load(response))
        except Exception:
            self.reply(503,{'status':'error','error':'upstream unavailable'})

    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:
                self.reply(413,{'error':'bounded body required'})
                return
            body=self.rfile.read(length)
            path=urllib.parse.urlsplit(self.path).path
            if path=='/api/v1/query':
                self.proxy_query(urllib.parse.parse_qs(body.decode()))
            elif path=='/webhook':
                payload=json.loads(body)
                failed=MODEL.state()['scenario']=='notification_failure'
                record_attempt(payload,failed)
                self.reply(503 if failed else 200,{'ok':not failed})
            elif path=='/api/scenario':
                self.reply(200,select(json.loads(body)['name']))
            else:
                self.reply(404,{'error':'not found'})
        except (ValueError,KeyError,TypeError):
            self.reply(400,{'error':'invalid request'})
        except Exception:
            self.reply(503,{'error':'local demo operation failed'})

    def log_message(self,*args):
        pass


if __name__=='__main__':
    threading.Thread(target=watchdog,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',9430),Handler).serve_forever()
