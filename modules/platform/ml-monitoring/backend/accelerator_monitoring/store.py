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


def advance_detector_state(state, result, quality, now, confirmation_samples, recovery_samples):
    """Apply one observation in memory and report whether the source sample advanced."""
    state['attempt_at']=now
    if result is None or quality!='valid':
        state.update(quality=quality,pending=0,clear_count=0)
    elif result['t'] > state['last_source']:
        if result.get('decision_config_revision') is not None and state.get('decision_config_revision')!=result['decision_config_revision']:
            state.update(pending=0,clear_count=0)
        gap=result['t']-state['last_source']
        if gap>max(8,4*result.get('cadence_seconds',2)):
            state.update(pending=0,clear_count=0)
        state.update(last_source=result['t'],quality='valid',score=result['score'],threshold=result['threshold'],model_id=result['model'])
        for key in ('raw_components','calibrated_components','expected','bounds','values','contributions','reason_metric','reference_kind','joint_distance_score','detector_kind','capabilities','raw_score','calibrated_score','raw_score_semantics','pipeline_id','calibrator_id','decision_id','preprocessor_id','decision_config_revision','effective_task_factor','scenario','evidence'):
            if key in result:state[key]=result[key]
        if result['anomaly']:
            state['pending']+=1;state['clear_count']=0
            if state['pending']>=confirmation_samples and not state['active']:
                state.update(active=True,episode_id=uuid.uuid4().hex,opened_at=result['t'],reason='confirmed_anomaly')
        else:
            state['pending']=0
            state['clear_count']+=1
            if state['clear_count']>=recovery_samples and state['active']:
                state.update(active=False,closed_at=result['t'],reason='fresh_normal_confirmed')
        return True
    return False


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
        CREATE TABLE IF NOT EXISTS recovered_episode(id TEXT PRIMARY KEY,task TEXT,closed_at REAL,payload TEXT);
        CREATE INDEX IF NOT EXISTS recovered_episode_time ON recovered_episode(closed_at);
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

    def recovered_episodes(self, start, end, limit=200, cluster=''):
        with self.db() as db:
            query = 'SELECT r.payload FROM recovered_episode r'
            args = [start, end]
            if cluster:
                query += (" JOIN documents t ON t.kind='task' AND t.id=r.task"
                          " JOIN documents e ON e.kind='entity' AND e.id=json_extract(t.payload,'$.entity')")
            query += ' WHERE r.closed_at BETWEEN ? AND ?'
            if cluster:
                query += " AND json_extract(e.payload,'$.cluster')=?"
                args.append(cluster)
            rows = db.execute(query + ' ORDER BY r.closed_at DESC LIMIT ?', (*args, limit)).fetchall()
            return [json.loads(row['payload']) for row in rows]

    def recovered_episode(self, key):
        with self.db() as db:
            row = db.execute('SELECT payload FROM recovered_episode WHERE id=?', (key,)).fetchone()
            return json.loads(row['payload']) if row else None

    def apply(self,task,result=None,quality='valid',now=None,confirmation_samples=3,recovery_samples=3):
        for count in (confirmation_samples,recovery_samples):
            if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=30:raise ValueError('确认/恢复样本数须为1至30的整数')
        now=time.time() if now is None else now
        with self.db() as db:
            row=db.execute("SELECT payload,revision FROM documents WHERE kind='state' AND id=?",(task,)).fetchone()
            state=json.loads(row['payload']) if row else {'id':task,'active':False,'quality':'unverified','last_source':0,'pending':0,'clear_count':0,'episode_id':None}
            was_active = state['active']
            if advance_detector_state(state,result,quality,now,confirmation_samples,recovery_samples):
                result=dict(result,task=task,active=state['active'],episode_id=state['episode_id'],
                            confirmation_samples=confirmation_samples,recovery_samples=recovery_samples)
                db.execute('INSERT OR IGNORE INTO results VALUES(?,?,?,?)',(task,result['t'],result['model'],json.dumps(result,allow_nan=False)))
                if was_active and not state['active'] and state.get('episode_id'):
                    episode = {**state, 'confirmation_samples': confirmation_samples, 'recovery_samples': recovery_samples}
                    db.execute('INSERT OR IGNORE INTO recovered_episode VALUES(?,?,?,?)',
                               (state['episode_id'], task, state['closed_at'], json.dumps(episode, allow_nan=False)))
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
        cutoff = time.time() - days * 86400
        with self.db() as db:
            db.execute('DELETE FROM results WHERE source_time<?', (cutoff,))
            db.execute('DELETE FROM recovered_episode WHERE closed_at<?', (cutoff,))
