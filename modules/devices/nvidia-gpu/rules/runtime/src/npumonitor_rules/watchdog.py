"""Independent failure detector with a durable ordered notification outbox."""
from contextlib import contextmanager
import json,sqlite3,threading,time,uuid
from pathlib import Path
from urllib.request import Request,ProxyHandler,build_opener
from .bundle import canonical,digest,url
from .source import NoRedirect

class Watchdog:
    @staticmethod
    def initialize(path,config,deployment):
        path=Path(path)
        if path.exists():Watchdog(path,config,deployment);return {'existing':True}
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb'):pass
        path.chmod(0o600)
        with sqlite3.connect(path) as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE targets(name TEXT PRIMARY KEY,failures INTEGER,active INTEGER,episode TEXT,last_repeat REAL);
            CREATE TABLE outbox(id INTEGER PRIMARY KEY,event_id TEXT UNIQUE,created REAL,payload TEXT,delivered REAL,attempts INTEGER DEFAULT 0);
            ''')
            db.executemany('INSERT INTO meta VALUES(?,?)',[('schema','1'),('binding',digest({'config':config,'deployment':deployment})),('last_tick','0')])
        return {'initialized':True}
    def __init__(self,path,config,deployment):
        self.path=Path(path);self.config=config;self.deployment=deployment;self.lock=threading.RLock();self.stop=threading.Event();self.opener=build_opener(ProxyHandler({}),NoRedirect())
        if not config.get('targets') or len(config['targets'])>20:raise ValueError('bounded watchdog targets required')
        for target in config['targets']:url(target['url'])
        url(config['callback_url'])
        with self.db() as db:pass
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:
                meta=dict(db.execute('SELECT key,value FROM meta'))
                if meta.get('schema')!='1' or meta.get('binding')!=digest({'config':self.config,'deployment':self.deployment}):raise ValueError('watchdog schema/binding mismatch; refusing reset')
                yield db
        finally:db.close()
    def tick(self):
        now=time.time();results={}
        for target in self.config['targets']:
            try:
                with self.opener.open(target['url'],timeout=self.config.get('timeout_seconds',3)) as response:response.read(1024)
                results[target['name']]=True
            except Exception:results[target['name']]=False
        with self.lock,self.db() as db:
            for name,healthy in results.items():
                row=db.execute('SELECT * FROM targets WHERE name=?',(name,)).fetchone()
                failures=0 if healthy else (row['failures']+1 if row else 1);was=row['active'] if row else 0
                active=0 if healthy else int(failures>=self.config.get('failure_count',3));episode=row['episode'] if row else None
                repeat=row['last_repeat'] if row else 0;event=None
                if active and not was:episode=uuid.uuid4().hex;event='firing'
                elif was and not active:event='resolved'
                elif active and now-repeat>=self.config.get('repeat_seconds',3600):event='repeat'
                if event:
                    if db.execute('SELECT count(*) FROM outbox WHERE delivered IS NULL').fetchone()[0]>=10000:raise RuntimeError('watchdog outbox quota exceeded; no messages discarded')
                    payload={'event_id':uuid.uuid4().hex,'episode':episode,'kind':'npumonitor_watchdog','status':event,'deployment':self.deployment,'target':name,'at':now,'note':'component availability; not GPU hardware recovery'}
                    db.execute('INSERT INTO outbox(event_id,created,payload) VALUES(?,?,?)',(payload['event_id'],now,canonical(payload)));repeat=now
                db.execute('INSERT INTO targets VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET failures=excluded.failures,active=excluded.active,episode=excluded.episode,last_repeat=excluded.last_repeat',(name,failures,active,episode,repeat))
            db.execute('UPDATE meta SET value=? WHERE key="last_tick"',(str(now),))
        with self.lock,self.db() as db:pending=db.execute('SELECT * FROM outbox WHERE delivered IS NULL ORDER BY id LIMIT 1').fetchone()
        if pending:
            ok=False
            try:
                token=Path(self.config['callback_token_file']).read_text().strip()
                req=Request(self.config['callback_url'],data=pending['payload'].encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                with self.opener.open(req,timeout=self.config.get('timeout_seconds',3)) as response:response.read(1024)
                ok=True
            except Exception:pass
            with self.lock,self.db() as db:db.execute('UPDATE outbox SET attempts=attempts+1,delivered=? WHERE id=?',(time.time() if ok else None,pending['id']))
        return self.status()
    def status(self):
        with self.lock,self.db() as db:
            meta=dict(db.execute('SELECT key,value FROM meta'))
            return {'last_tick':float(meta['last_tick']),'targets':[dict(r) for r in db.execute('SELECT * FROM targets')],
                    'pending':db.execute('SELECT count(*) FROM outbox WHERE delivered IS NULL').fetchone()[0],
                    'delivered':db.execute('SELECT count(*) FROM outbox WHERE delivered IS NOT NULL').fetchone()[0]}
    def run(self):
        while not self.stop.is_set():
            try:self.tick()
            except Exception:pass  # Liveness/readiness will fail if the persisted heartbeat stops.
            self.stop.wait(self.config.get('interval_seconds',5))


def serve_watchdog(path,config,deployment):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    watch=Watchdog(path,config,deployment)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            try:
                state=watch.status();fresh=0<=time.time()-state['last_tick']<=max(15,config.get('interval_seconds',5)*4)
                body=json.dumps({'alive':fresh,'pending_deliveries':state['pending']}).encode();self.send_response(200 if fresh else 503);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            except Exception:self.send_error(503)
    threading.Thread(target=watch.run,daemon=True).start();ThreadingHTTPServer(('0.0.0.0',9481),Handler).serve_forever()
