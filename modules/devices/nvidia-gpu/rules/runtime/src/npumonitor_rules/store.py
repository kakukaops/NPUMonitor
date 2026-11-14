"""Durable source-clock state, explicit releases and optimistic administrative actions."""
from contextlib import contextmanager
import json,os,sqlite3,threading,time,uuid
from pathlib import Path
from .bundle import canonical,digest,validate_bundle

class Conflict(ValueError):pass

class Store:
    def __init__(self,path,deployment_id):
        self.path=Path(path);self.deployment_id=deployment_id;self.lock=threading.RLock()
        with self.db() as db:self._bundle(db)
    @staticmethod
    def initialize(path,bundle):
        validate_bundle(bundle);path=Path(path)
        if path.exists():
            Store(path,bundle['config']['deployment_id']);return {'initialized':False,'existing':True}
        path.parent.mkdir(parents=True,exist_ok=True)
        # O_EXCL prevents two first-install processes from replacing an established DB.
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        try:
            with sqlite3.connect(path) as db:
                db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE releases(sha TEXT PRIMARY KEY,payload TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE activations(generation INTEGER PRIMARY KEY,sha TEXT NOT NULL,at REAL,actor TEXT,reason TEXT);
                CREATE TABLE states(rule_id TEXT NOT NULL,entity_key TEXT NOT NULL,identity TEXT NOT NULL,
                  active INTEGER NOT NULL DEFAULT 0,quality TEXT NOT NULL,last_source REAL,last_attempt REAL,
                  last_valid REAL,value REAL,pending_first REAL,pending_last REAL,episode TEXT,revision INTEGER NOT NULL DEFAULT 0,
                  retired INTEGER NOT NULL DEFAULT 0,reason TEXT,PRIMARY KEY(rule_id,entity_key));
                CREATE TABLE transitions(id INTEGER PRIMARY KEY,at REAL,rule_id TEXT,entity_key TEXT,episode TEXT,active INTEGER,reason TEXT,generation INTEGER);
                CREATE TABLE actions(id TEXT PRIMARY KEY,rule_id TEXT,entity_key TEXT,episode TEXT,at REAL,expires REAL,actor TEXT,reason TEXT,consumed INTEGER DEFAULT 0);
                CREATE TABLE audit(id INTEGER PRIMARY KEY,at REAL,actor TEXT,action TEXT,payload TEXT);
                CREATE TABLE projections(key TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE sync_operations(id TEXT PRIMARY KEY,at REAL,payload TEXT NOT NULL);''')
                db.executemany('INSERT INTO meta VALUES(?,?)', [('schema','1'),('deployment',bundle['config']['deployment_id']),('generation','1'),('active_sha',bundle['sha256']),('last_poll','0'),('last_errors','{}')])
                db.execute('INSERT INTO releases VALUES(?,?,?)',(bundle['sha256'],canonical(bundle),time.time()))
                db.execute('INSERT INTO activations VALUES(1,?,?,?,?)',(bundle['sha256'],time.time(),'installer','explicit initialization'))
        except Exception:
            # Keep the partial file so a later process fails closed rather than reinitializing.
            raise
        return {'initialized':True,'generation':1}
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:
                meta=dict(db.execute('SELECT key,value FROM meta'))
                if meta.get('schema')!='1' or meta.get('deployment')!=self.deployment_id:raise ValueError('state schema/deployment mismatch')
                yield db
        finally:db.close()
    def _bundle(self,db):
        meta=dict(db.execute('SELECT key,value FROM meta'));row=db.execute('SELECT payload FROM releases WHERE sha=?',(meta['active_sha'],)).fetchone()
        if row is None:raise ValueError('active release missing')
        b=json.loads(row[0]);validate_bundle(b)
        if b['sha256']!=meta['active_sha']:raise ValueError('release identity mismatch')
        return b,int(meta['generation'])
    def current(self):
        with self.lock,self.db() as db:return self._bundle(db)
    def plan(self,candidate):
        validate_bundle(candidate);old,generation=self.current()
        if old['config']['deployment_id']!=candidate['config']['deployment_id']:raise Conflict('deployment identity cannot change')
        if old['config']['upstream']['url']!=candidate['config']['upstream']['url']:raise Conflict('upstream migration requires a separate explicit deployment; existing incidents cannot silently rebind')
        before={r['rule_id']:r for r in old['rules']};after={r['rule_id']:r for r in candidate['rules']}
        return {'generation':generation,'current_sha':old['sha256'],'candidate_sha':candidate['sha256'],
                'changed':sorted(k for k in before.keys()&after.keys() if before[k]['signature']!=after[k]['signature'] or before[k]['enabled']!=after[k]['enabled']),
                'added':sorted(after.keys()-before.keys()),'removed':sorted(before.keys()-after.keys()),'active_incidents_preserved':True}
    def activate(self,candidate,expected_generation,actor,reason):
        plan=self.plan(candidate)
        with self.lock,self.db() as db:
            old,generation=self._bundle(db)
            if generation!=expected_generation or generation!=plan['generation']:raise Conflict('active revision changed')
            if old['sha256']==candidate['sha256']:return plan
            now=time.time();newgen=generation+1
            db.execute('INSERT OR IGNORE INTO releases VALUES(?,?,?)',(candidate['sha256'],canonical(candidate),now))
            db.execute('INSERT INTO activations VALUES(?,?,?,?,?)',(newgen,candidate['sha256'],now,actor,reason))
            db.execute('UPDATE meta SET value=? WHERE key="generation"',(str(newgen),));db.execute('UPDATE meta SET value=? WHERE key="active_sha"',(candidate['sha256'],))
            db.execute('UPDATE states SET pending_first=NULL,pending_last=NULL,quality="release_changed",revision=revision+1 WHERE retired=0')
            enabled={r['rule_id'] for r in candidate['rules'] if r['enabled']}
            for row in db.execute('SELECT * FROM states').fetchall():
                if row['rule_id'] not in enabled:
                    if row['active']:db.execute('INSERT INTO transitions(at,rule_id,entity_key,episode,active,reason,generation) VALUES(?,?,?,?,0,?,?)',(now,row['rule_id'],row['entity_key'],row['episode'],'administrative_rule_disable',newgen))
                    db.execute('UPDATE states SET active=0,quality="disabled",reason="administrative_rule_disable",revision=revision+1 WHERE rule_id=? AND entity_key=?',(row['rule_id'],row['entity_key']))
            self._audit(db,actor,'activate',{'from':old['sha256'],'to':candidate['sha256'],'generation':newgen,'reason':reason})
            return dict(plan,generation=newgen,activated=True)
    @staticmethod
    def _audit(db,actor,action,payload):db.execute('INSERT INTO audit(at,actor,action,payload) VALUES(?,?,?,?)',(time.time(),actor,action,canonical(payload)))
    def actions(self,rule_id,now=None):
        now=time.time() if now is None else now
        with self.lock,self.db() as db:
            return [dict(r,identity=json.loads(r['identity'])) for r in db.execute('''SELECT a.*,s.identity FROM actions a JOIN states s
                ON a.rule_id=s.rule_id AND a.entity_key=s.entity_key AND a.episode=s.episode
                WHERE a.rule_id=? AND a.consumed=0 AND a.expires>=? AND s.active=1 AND s.retired=0''',(rule_id,now))]
    def administer(self,action,rule_id,identity,expected_revision,reason,actor='admin',now=None):
        now=time.time() if now is None else now
        if action not in ('recovery','retire','unretire'):raise ValueError('unknown administrative operation')
        if not isinstance(reason,str) or not 4<=len(reason)<=1000:raise ValueError('bounded administrative reason required')
        key=digest(identity)
        with self.lock,self.db() as db:
            bundle,generation=self._bundle(db);row=db.execute('SELECT * FROM states WHERE rule_id=? AND entity_key=?',(rule_id,key)).fetchone()
            if not row or row['revision']!=expected_revision:raise Conflict('state revision changed or identity not known')
            if action=='recovery':
                if not (rule_id.startswith('os_sre.xid_') or rule_id.startswith('os_sre.sxid_')) or not row['active'] or row['retired']:raise ValueError('recovery evidence applies only to an active XID/SXid episode')
                ident=uuid.uuid4().hex;ttl=bundle['config']['limits']['recovery_ttl_seconds']
                db.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,0)',(ident,rule_id,key,row['episode'],now,now+ttl,actor,reason))
                result={'id':ident,'episode':row['episode'],'expires':now+ttl,'forced_clear':False}
            else:
                retired=int(action=='retire')
                if row['active']:db.execute('INSERT INTO transitions(at,rule_id,entity_key,episode,active,reason,generation) VALUES(?,?,?,?,0,?,?)',(now,rule_id,key,row['episode'],'administrative_'+action,generation))
                db.execute('UPDATE states SET retired=?,active=0,quality=?,pending_first=NULL,pending_last=NULL,reason=?,revision=revision+1 WHERE rule_id=? AND entity_key=?',(retired,'retired' if retired else 'unverified','administrative_'+action,rule_id,key))
                db.execute('UPDATE actions SET consumed=1 WHERE rule_id=? AND entity_key=?',(rule_id,key));result={'retired':bool(retired),'hardware_recovered':False}
            self._audit(db,actor,action,{'rule_id':rule_id,'identity':identity,'reason':reason,'result':result});return result
    def apply_cycle(self,results,generation,now=None):
        now=time.time() if now is None else now
        with self.lock,self.db() as db:
            bundle,currentgen=self._bundle(db)
            if currentgen!=generation:raise Conflict('discarded in-flight cycle from an older release')
            specs={r['rule_id']:r for r in bundle['rules']};limits=bundle['config']['limits'];fresh=bundle['config']['profile']['freshness_seconds'];errors={}
            count=db.execute('SELECT count(*) FROM states').fetchone()[0]
            for result in results:
                rid=result['rule_id'];spec=specs[rid]
                if not spec['enabled']:continue
                samples=result.get('samples');error=result.get('error') or result.get('unavailable');known={r['entity_key']:dict(r) for r in db.execute('SELECT * FROM states WHERE rule_id=?',(rid,))}
                if result.get('error'):errors[rid]=result['error']
                incoming={digest(v['identity']):v for v in (samples or [])}
                if len(incoming)!=len(samples or []):raise ValueError('duplicate normalized identities')
                for key,point in incoming.items():
                    if key not in known:
                        count+=1
                        if count>limits['max_states']:raise ValueError('state cardinality quota exceeded')
                        db.execute('INSERT INTO states(rule_id,entity_key,identity,active,quality,revision) VALUES(?,?,?,0,"unverified",0)',(rid,key,canonical(point['identity'])))
                        known[key]=dict(db.execute('SELECT * FROM states WHERE rule_id=? AND entity_key=?',(rid,key)).fetchone())
                for key,row in known.items():
                    if row['retired']:continue
                    point=incoming.get(key);quality='valid';value=None;stamp=None
                    if error:quality=error
                    elif point is None:
                        if spec['kind']=='direct':value=0;stamp=now
                        else:quality='unknown'
                    else:
                        if canonical(point['identity'])!=row['identity']:raise ValueError('identity hash collision')
                        value=point['value'];stamp=point['source_time']
                        if spec['kind']=='stateful' and not 0<=now-stamp<=fresh:quality='stale';value=None
                        elif row['last_source'] is not None and stamp<=row['last_source']:
                            quality='valid_unchanged' if stamp==row['last_source'] else 'out_of_order';value=None
                    active=row['active'];first=row['pending_first'];last=row['pending_last'];episode=row['episode'];reason=row['reason']
                    if value is None:
                        if quality!='valid_unchanged':first=last=None
                    elif value==0:
                        active=0;first=last=None
                        reason='operator_confirmed_zero_code' if rid.startswith(('os_sre.xid_','os_sre.sxid_')) else 'recent_activity_quiet' if rid in {"os_sre."+n for n in ('ecc_new','thermal_time','pcie_replay','nvlink_crc','nvlink_recovery','nvlink_replay','switch_replay','switch_recovery')} else 'condition_exit_or_valid_clear'
                    elif value==1:
                        if not active:
                            if first is None or last is None or not 0<stamp-last<=limits['max_source_gap_seconds']:first=stamp
                            last=stamp
                            if stamp-first>=spec['for_seconds']:
                                active=1;first=last=None;episode=uuid.uuid4().hex;reason='confirmed_evidence'
                            else:reason='confirming'
                    else:raise ValueError('state observation must be boolean')
                    if active!=row['active']:
                        db.execute('INSERT INTO transitions(at,rule_id,entity_key,episode,active,reason,generation) VALUES(?,?,?,?,?,?,?)',(now,rid,key,episode,active,reason,generation))
                        if not active:db.execute('UPDATE actions SET consumed=1 WHERE rule_id=? AND entity_key=?',(rid,key))
                    db.execute('''UPDATE states SET active=?,quality=?,last_source=?,last_attempt=?,last_valid=?,value=?,pending_first=?,pending_last=?,episode=?,revision=revision+1,reason=?
                        WHERE rule_id=? AND entity_key=?''',(active,quality,stamp if value is not None else row['last_source'],now,now if value is not None else row['last_valid'],value if value is not None else row['value'],first,last,episode,reason,rid,key))
            db.execute('UPDATE meta SET value=? WHERE key="last_poll"',(str(now),));db.execute('UPDATE meta SET value=? WHERE key="last_errors"',(canonical(errors),))
    def health(self,now=None):
        now=time.time() if now is None else now
        with self.lock,self.db() as db:
            bundle,generation=self._bundle(db);meta=dict(db.execute('SELECT key,value FROM meta'));age=now-float(meta['last_poll'])
            errors=json.loads(meta['last_errors']);counts={r[0]:r[1] for r in db.execute('SELECT quality,count(*) FROM states GROUP BY quality')}
            return {'generation':generation,'bundle_sha':bundle['sha256'],'cycle_fresh':0<=age<=bundle['config']['limits']['max_poll_age_seconds'],
                    'last_poll':float(meta['last_poll']),'errors':errors,'qualities':counts,'active':db.execute('SELECT count(*) FROM states WHERE active=1 AND retired=0').fetchone()[0]}
    def vector(self,rule_id,now=None):
        now=time.time() if now is None else now;health=self.health(now)
        if not health['cycle_fresh']:raise RuntimeError('poller heartbeat unavailable; refusing a healthy empty vector')
        with self.lock,self.db() as db:
            known=db.execute('SELECT 1 FROM states WHERE rule_id=? LIMIT 1',(rule_id,)).fetchone();bundle,generation=self._bundle(db)
            if rule_id not in {r['rule_id'] for r in bundle['rules']} and not known:raise ValueError('unknown managed rule')
            return [{'metric':dict(json.loads(r['identity']),sre_rule_id=rule_id),'value':[now,'1']} for r in db.execute('SELECT identity FROM states WHERE rule_id=? AND active=1 AND retired=0',(rule_id,))]
    def snapshot(self,limit=1000,offset=0):
        with self.lock,self.db() as db:
            return {'health':self.health(),'states':[dict(r,identity=json.loads(r['identity'])) for r in db.execute('SELECT * FROM states ORDER BY rule_id,entity_key LIMIT ? OFFSET ?',(limit,offset))],
                    'transitions':[dict(r) for r in db.execute('SELECT * FROM transitions ORDER BY id DESC LIMIT 100')],
                    'audit':[dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]}
    def get_projection(self,key):
        with self.lock,self.db() as db:
            row=db.execute('SELECT payload FROM projections WHERE key=?',(key,)).fetchone();return json.loads(row[0]) if row else None
    def put_projection(self,key,value):
        with self.lock,self.db() as db:db.execute('INSERT INTO projections VALUES(?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',(key,canonical(value)))
    def put_operation(self,ident,value):
        with self.lock,self.db() as db:db.execute('INSERT INTO sync_operations VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(ident,time.time(),canonical(value)))
    def get_operation(self,ident):
        with self.lock,self.db() as db:
            row=db.execute('SELECT payload FROM sync_operations WHERE id=?',(ident,)).fetchone();return json.loads(row[0]) if row else None
    def backup(self,target):
        target=Path(target)
        if target.exists():raise ValueError('backup destination exists')
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        with self.lock,self.db() as db:
            dest=sqlite3.connect(target)
            try:db.backup(dest)
            finally:dest.close()
        target.chmod(0o600)
        return {'file':str(target),'sha256':__import__('hashlib').sha256(target.read_bytes()).hexdigest(),'includes':'state, releases, audit, recovery actions and projection journal; secrets are separate files'}
