"""Transactional SQLite metadata, online results and source-time lifecycle state."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid


class Conflict(ValueError):
    pass


def check_initialization(database,guard_file):
    """A missing established state volume must not become a fresh healthy install."""
    if not Path(database).exists() and Path(guard_file).read_text().strip()!='pending':
        raise ValueError('状态数据库缺失：请从备份恢复，不自动初始化健康状态')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT OR IGNORE INTO meta VALUES('schema','1');
            CREATE TABLE IF NOT EXISTS documents(kind TEXT,id TEXT,payload TEXT NOT NULL,
              revision INTEGER NOT NULL,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS results(task TEXT,source_time REAL,model TEXT,payload TEXT,
              PRIMARY KEY(task,source_time,model));
            CREATE INDEX IF NOT EXISTS result_time ON results(source_time);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at REAL,actor TEXT,action TEXT,
              object_id TEXT,details TEXT);
            ''')
            if db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] != '1':
                raise ValueError('数据库版本不兼容；需显式迁移')
        for job in self.list('job'):
            if job['status'] in ('queued','running'):
                job.update(status='pending_sync' if job.get('backend_request_id') else 'failed',error='监控重启，外部模型任务待同步' if job.get('backend_request_id') else '服务重启中断，在线模型保持不变')
                self.put('job',job['id'],job)

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=8)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA busy_timeout=8000')
            try:
                with db: yield db
            finally: db.close()

    def get(self,kind,key):
        with self.db() as db:
            row=db.execute('SELECT payload,revision FROM documents WHERE kind=? AND id=?',(kind,key)).fetchone()
            if row is None: return None
            return dict(json.loads(row['payload']),revision=row['revision'])

    def list(self,kind):
        with self.db() as db:
            rows=db.execute('SELECT payload,revision FROM documents WHERE kind=? ORDER BY id LIMIT 5000',(kind,)).fetchall()
            return [dict(json.loads(row['payload']),revision=row['revision']) for row in rows]

    def put(self,kind,key,payload,expected=None):
        payload=dict(payload,id=key);payload.pop('revision',None)
        with self.db() as db:
            old=db.execute('SELECT revision FROM documents WHERE kind=? AND id=?',(kind,key)).fetchone()
            revision=old['revision'] if old else 0
            if expected is not None and revision!=expected: raise Conflict('版本已变化，请刷新后重试')
            db.execute('INSERT INTO documents VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision',
                       (kind,key,json.dumps(payload,ensure_ascii=False,allow_nan=False),revision+1))
        return dict(payload,revision=revision+1)

    def audit(self,actor,action,key,details=None):
        with self.db() as db:
            db.execute('INSERT INTO audit(at,actor,action,object_id,details) VALUES(?,?,?,?,?)',
                       (time.time(),actor,action,key,json.dumps(details or {},ensure_ascii=False)))

    def bind_source(self,fingerprint):
        with self.db() as db:
            old=db.execute("SELECT value FROM meta WHERE key='source_binding'").fetchone()
            if old and old[0]!=fingerprint:raise ValueError('输入源或字段契约已变化，需要显式迁移或独立数据卷')
            db.execute("INSERT OR IGNORE INTO meta VALUES('source_binding',?)",(fingerprint,))

    def audits(self):
        with self.db() as db:
            return [dict(r,details=json.loads(r['details'])) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 150')]

    def history(self,task,start=0,end=None,limit=12000):
        with self.db() as db:
            rows=db.execute('SELECT payload FROM results WHERE task=? AND source_time>=? AND source_time<=? ORDER BY source_time DESC LIMIT ?',
                            (task,start,end or time.time()+1,limit)).fetchall()
            return list(reversed([json.loads(r['payload']) for r in rows]))

    def apply(self,task,result=None,quality='valid',now=None):
        now=time.time() if now is None else now
        with self.db() as db:
            row=db.execute("SELECT payload,revision FROM documents WHERE kind='state' AND id=?",(task,)).fetchone()
            state=json.loads(row['payload']) if row else {'id':task,'active':False,'quality':'unverified','last_source':0,'pending':0,'clear_count':0,'episode_id':None}
            state['attempt_at']=now
            if result is None or quality!='valid':
                state.update(quality=quality,pending=0,clear_count=0)
            elif result['t'] > state['last_source']:
                gap=result['t']-state['last_source']
                if gap>max(8,4*result.get('cadence_seconds',2)):
                    state.update(pending=0,clear_count=0)
                state.update(last_source=result['t'],quality='valid',score=result['score'],threshold=result['threshold'],model_id=result['model'])
                for key in ('contributions','reason_metric','reference_kind','joint_distance_score','detector_kind','capabilities','raw_score','calibrated_score','raw_score_semantics','pipeline_id','calibrator_id','decision_id','preprocessor_id','decision_config_revision','effective_task_factor','scenario','evidence'):
                    if key in result:state[key]=result[key]
                if result['anomaly']:
                    state['pending']+=1;state['clear_count']=0
                    if state['pending']>=3 and not state['active']:
                        state.update(active=True,episode_id=uuid.uuid4().hex,opened_at=result['t'],reason='confirmed_anomaly')
                else:
                    state['pending']=0
                    state['clear_count']+=1
                    if state['clear_count']>=3 and state['active']:
                        state.update(active=False,closed_at=result['t'],reason='fresh_normal_confirmed')
                result=dict(result,task=task,active=state['active'],episode_id=state['episode_id'])
                db.execute('INSERT OR IGNORE INTO results VALUES(?,?,?,?)',(task,result['t'],result['model'],json.dumps(result,allow_nan=False)))
            # A repeated held source sample never advances confirmation or recovery.
            revision=row['revision']+1 if row else 1
            db.execute("INSERT INTO documents VALUES('state',?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision",
                       (task,json.dumps(state,allow_nan=False),revision))
        return state

    def record_shadow(self,task,result):
        result=dict(result,task=task,run_type='shadow')
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO results VALUES(?,?,?,?)',('shadow:'+task,result['t'],result['model'],json.dumps(result,allow_nan=False)))
        self.put('shadow',task,result)

    def administrative_close(self,task,reason):
        state=self.get('state',task)
        if state:
            state.update(active=False,pending=0,clear_count=0,quality='paused',reason=reason,closed_at=time.time())
            self.put('state',task,state)

    def backup(self,target):
        with self.db() as db:
            output=sqlite3.connect(target)
            try:db.backup(output)
            finally:output.close()

    def prune(self,days=7):
        with self.db() as db:db.execute('DELETE FROM results WHERE source_time<?',(time.time()-days*86400,))
