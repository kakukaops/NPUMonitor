"""Fixed simulation lifecycle adapter. Query-only upstream; explicit SQLite init."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request

CONFIG=os.environ.get('LIFECYCLE_CONFIG','/rules/recovery-lab.json')
DB=os.environ.get('LIFECYCLE_DB','/data/lifecycle.sqlite')


def digest(config):return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self,path,config,initialize=False):
        self.path=Path(path);self.config=config;self.lock=threading.Lock()
        assert config['scope']=='simulation-only' and config['production_admitted'] is False
        self.rules={r['rule_id']:r for r in config['rules']}
        self.confirmation=any(r.get('confirm_seconds',0)>0 for r in self.rules.values())
        self.expected={(rule_id, entity) for rule_id, rule in self.rules.items()
                       for entity in rule.get('entity_ids', config['uuids'])}
        if initialize:
            if self.path.exists():raise ValueError('database exists; initialization refuses overwrite')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(self.path) as db:
                db.executescript('''CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE states(rule_id TEXT,uuid TEXT,active INTEGER NOT NULL,quality TEXT NOT NULL,
                  last_value REAL,last_valid_at REAL,last_attempt_at REAL,PRIMARY KEY(rule_id,uuid));
                CREATE TABLE transitions(id INTEGER PRIMARY KEY,at REAL,rule_id TEXT,uuid TEXT,
                  active INTEGER,quality TEXT,reason TEXT);''')
                db.executemany('INSERT INTO meta VALUES (?,?)',[('schema','1'),('binding',digest(config)),('last_poll','0')])
                db.execute('CREATE TABLE pending(rule_id TEXT,uuid TEXT,first_seen REAL,last_seen REAL,PRIMARY KEY(rule_id,uuid))')
                db.executemany('INSERT INTO states VALUES (?,?,0,\'unverified\',NULL,NULL,NULL)',
                    sorted(self.expected))
        # Missing/lost volume is a startup error, never a fresh healthy state.
        with self.connect() as db:
            meta=dict(db.execute('SELECT key,value FROM meta'))
            if meta.get('schema')!='1' or meta.get('binding')!=digest(config):raise ValueError('schema/binding mismatch; explicit migration required')
            expected=self.expected
            if {tuple(row) for row in db.execute('SELECT rule_id,uuid FROM states')}!=expected:raise ValueError('state inventory mismatch')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,timeout=3)
        db.row_factory=sqlite3.Row
        try:
            with db:
                meta=dict(db.execute('SELECT key,value FROM meta'))
                if meta.get('schema')!='1' or meta.get('binding')!=digest(self.config):
                    raise ValueError('state store binding/schema changed')
                rows=db.execute('SELECT rule_id,uuid,active,quality,last_value FROM states').fetchall()
                if {(r['rule_id'],r['uuid']) for r in rows}!=self.expected:
                    raise ValueError('state inventory changed')
                if any(r['active'] not in (0,1) or r['quality'] not in ('unverified','valid','unjudgeable','query_error') or
                       r['last_value'] is not None and r['last_value'] not in (0,1) for r in rows):
                    raise ValueError('invalid persisted state values')
                yield db
        finally:
            db.close()

    def apply(self,observations,now=None):
        now=time.time() if now is None else now
        # observations maps each rule to a unique set of valid 0/1 inputs, or None on query failure.
        with self.lock,self.connect() as db:
            for row in db.execute('SELECT * FROM states').fetchall():
                obs=observations.get(row['rule_id'])
                value=None if obs is None else obs.get(row['uuid'])
                valid=isinstance(value,(float,int)) and math.isfinite(value) and value in (0,1)
                quality='valid' if valid else ('query_error' if obs is None else 'unjudgeable')
                active,reason=self.transition(db,row,value,valid,now)
                if active!=row['active'] or quality!=row['quality']:
                    db.execute('INSERT INTO transitions(at,rule_id,uuid,active,quality,reason) VALUES (?,?,?,?,?,?)',
                               (now,row['rule_id'],row['uuid'],active,quality,reason))
                db.execute('UPDATE states SET active=?,quality=?,last_value=?,last_valid_at=?,last_attempt_at=? WHERE rule_id=? AND uuid=?',
                           (active,quality,value if valid else row['last_value'],now if valid else row['last_valid_at'],now,row['rule_id'],row['uuid']))
            db.execute('UPDATE meta SET value=? WHERE key=\'last_poll\'',(str(now),))

    def transition(self,db,row,value,valid,now):
        hold=self.rules[row['rule_id']].get('confirm_seconds',0)
        if not hold or row['active']:
            return (int(value) if valid else row['active'],
                    ('flag_asserted' if value==1 else 'flag_cleared') if valid else 'hold_previous_active_state')
        key=(row['rule_id'],row['uuid'])
        if not valid or value==0:
            db.execute('DELETE FROM pending WHERE rule_id=? AND uuid=?',key)
            return 0,'confirmation_reset'
        pending=db.execute('SELECT first_seen,last_seen FROM pending WHERE rule_id=? AND uuid=?',key).fetchone()
        gap=self.config.get('maximum_confirmation_gap_seconds',6)
        first=pending['first_seen'] if pending and 0<=now-pending['last_seen']<=gap else now
        if now-first>=hold:
            db.execute('DELETE FROM pending WHERE rule_id=? AND uuid=?',key)
            return 1,'confirmed_duration'
        db.execute('INSERT INTO pending VALUES (?,?,?,?) ON CONFLICT(rule_id,uuid) DO UPDATE SET first_seen=excluded.first_seen,last_seen=excluded.last_seen',key+(first,now))
        return 0,'confirming'

    def snapshot(self):
        with self.lock,self.connect() as db:
            return {'binding_sha256':digest(self.config),'last_poll':float(dict(db.execute('SELECT key,value FROM meta'))['last_poll']),
                    'states':[dict(r) for r in db.execute('SELECT * FROM states ORDER BY rule_id,uuid')],
                    'pending':[dict(r) for r in db.execute('SELECT * FROM pending')] if self.confirmation else [],
                    'transitions':[dict(r) for r in db.execute('SELECT * FROM transitions ORDER BY id DESC LIMIT 30')]}

    def vector(self,rule,now=None):
        now=time.time() if now is None else now
        state=self.snapshot();age=now-state['last_poll']
        if not 0<=age<=self.config['max_poll_age_seconds']:raise RuntimeError('poller heartbeat unavailable')
        result=[]
        for entry in state['states']:
            if entry['rule_id']!=rule or not entry['active']:
                continue
            labels={'cluster_id':self.config['cluster_id'],'metric_name':self.rules[rule]['metric_name'],
                    'lifecycle_rule_id':rule,'simulated':'true'}
            metadata=self.config.get('entity_labels',{}).get(entry['uuid'])
            if metadata is None:
                labels['UUID']=entry['uuid']
            else:
                labels.update(metadata)
                labels['entity_id']=entry['uuid']
            result.append({'metric':labels,'value':[now,'1']})
        return result



def parse_observation(payload,config,rule):
    if payload.get('status')!='success' or payload.get('warnings') or payload.get('data',{}).get('resultType')!='vector':
        raise ValueError('query error/warning/type')
    found={}
    for item in payload['data']['result']:
        labels=item['metric'];uuid=labels.get(config.get('identity_label','UUID'))
        if labels.get('cluster_id')!=config['cluster_id'] or uuid not in rule.get('entity_ids',config['uuids']) or labels.get('metric_name')!=rule['metric_name']:
            raise ValueError('unexpected input identity')
        if uuid in found:raise ValueError('duplicate observation')
        value=float(item['value'][1])
        if not math.isfinite(value) or value not in (0,1):raise ValueError('invalid boolean')
        found[uuid]=value
    return found


def poll(store,stop):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while not stop.is_set():
        observations={}
        for rule in store.config['rules']:
            try:
                url=store.config['upstream_url']+'/api/v1/query?'+urllib.parse.urlencode({'query':rule['observation_expression']})
                with opener.open(url,timeout=5) as response:payload=json.load(response)
                observations[rule['rule_id']]=parse_observation(payload,store.config,rule)
            except Exception:
                observations[rule['rule_id']]=None
        try:store.apply(observations)
        except Exception:
            # Stop serving rather than publish an empty vector on storage errors.
            print('ERROR: lifecycle storage update failed',flush=True)
            stop.set();return
        stop.wait(store.config['poll_seconds'])


class Handler(BaseHTTPRequestHandler):
    store=None
    stop=None

    def reply(self,status,value):
        body=json.dumps(value,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path!='/api/v1/query':
            self.reply(404,{'error':'not found'});return
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=4096:
            self.reply(413,{'error':'bounded query form required'});return
        body=self.rfile.read(length).decode('utf-8')
        self.path='/api/v1/query?'+body
        self.do_GET()

    def do_GET(self):
        try:
            parts=urllib.parse.urlsplit(self.path)
            if parts.path=='/state':
                self.reply(200,self.store.snapshot());return
            if self.stop.is_set():raise RuntimeError('poller stopped')
            if parts.path=='/health':
                self.store.vector(next(iter(self.store.rules)))
                self.reply(200,{'ok':True,'scope':'simulation-only'});return
            if parts.path=='/api/v1/query':
                params=urllib.parse.parse_qs(parts.query);query=params.get('query',[''])[0]
                # Nightingale validates Prometheus datasource URLs using this fixed scalar probe.
                if query=='1+1':
                    self.store.vector(next(iter(self.store.rules)))
                    self.reply(200,{'status':'success','data':{'resultType':'scalar','result':[time.time(),'2']}});return
                match=re.fullmatch(r'gpu_lifecycle_active\{lifecycle_rule_id="([a-z0-9_.]+)"\}',query)
                if not match or match[1] not in self.store.rules:
                    self.reply(422,{'status':'error','errorType':'bad_data','error':'only fixed lifecycle queries supported'});return
                query_time=time.time()
                if 'time' in params:
                    try:query_time=float(params['time'][0])
                    except ValueError:query_time=datetime.fromisoformat(params['time'][0].replace('Z','+00:00')).timestamp()
                if abs(query_time-time.time())>10:
                    self.reply(422,{'status':'error','error':'historical evaluation unsupported'});return
                self.reply(200,{'status':'success','data':{'resultType':'vector','result':self.store.vector(match[1])}});return
            self.reply(404,{'error':'not found'})
        except Exception:
            self.reply(503,{'status':'error','errorType':'unavailable','error':'lifecycle state unavailable; no empty success response'})

    def log_message(self,*args):pass


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['init','serve']);args=parser.parse_args()
    config=json.loads(Path(CONFIG).read_text());store=Store(DB,config,initialize=args.action=='init')
    if args.action=='init':print('initialized simulation lifecycle store');return
    stop=threading.Event();Handler.store=store;Handler.stop=stop
    threading.Thread(target=poll,args=(store,stop),daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',9410),Handler).serve_forever()


if __name__=='__main__':main()
