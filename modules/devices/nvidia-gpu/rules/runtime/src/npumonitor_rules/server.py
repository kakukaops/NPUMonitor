"""Authenticated, bounded current-state Prometheus gateway and administration API."""
import base64,hmac,json,os,re,signal,ssl,threading,time,uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from . import __version__
from .bundle import validate_bundle
from .engine import Engine
from .store import Store,Conflict


def token(path):
    value=Path(path).read_text().strip()
    if len(value)<24 or '\n' in value:raise ValueError('private role credential missing or too short')
    return value

class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True;request_queue_size=64;allow_reuse_address=True
    def __init__(self,*a,**k):self.slots=threading.BoundedSemaphore(64);super().__init__(*a,**k)
    def get_request(self):
        connection,address=super().get_request();connection.settimeout(10);return connection,address
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            try:request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,*a):
        try:super().process_request_thread(*a)
        finally:self.slots.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def role(self):
        b,_=self.server.store.current();g=b['config']['gateway'];value=self.headers.get('Authorization','')
        if value.startswith('Bearer '):
            candidate=value[7:]
            if hmac.compare_digest(candidate,token(g['admin_token_file'])):return 'admin'
            if hmac.compare_digest(candidate,token(g['viewer_token_file'])):return 'viewer'
        if value.startswith('Basic '):
            try:user,password=base64.b64decode(value[6:],validate=True).decode().split(':',1)
            except Exception:return None
            if user=='monitor' and hmac.compare_digest(password,token(g['viewer_token_file'])):return 'viewer'
        return None
    def reply(self,status,value):
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        if len(raw)>32*1024*1024:raise ValueError('response quota exceeded')
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def body(self):
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=256*1024:raise ValueError('bounded request body required')
        return self.rfile.read(length)
    def do_GET(self):self.handle_request(False)
    def do_POST(self):self.handle_request(True)
    def handle_request(self,post):
        try:
            path=urlsplit(self.path).path;store=self.server.store;engine=self.server.engine
            if path=='/metrics' and not post:
                store.current();ready=int(bool(engine.readiness()['ready']))
                raw=('# HELP npumonitor_rules_ready Rule gateway readiness.\n# TYPE npumonitor_rules_ready gauge\nnpumonitor_rules_ready '+str(ready)+'\n').encode()
                self.send_response(200);self.send_header('Content-Type','text/plain; version=0.0.4');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            if path=='/health' and not post:
                store.current();self.reply(200,{'alive':True,'version':__version__});return
            if path=='/ready' and not post:
                result=engine.readiness();self.reply(200 if result['ready'] else 503,{'ready':result['ready'],'version':__version__});return
            role=self.role()
            if role is None:self.reply(401,{'error':'authentication_required'});return
            if path=='/api/v1/query':
                params=parse_qs(self.body().decode() if post else urlsplit(self.path).query)
                query=params.get('query',[''])[0];at=time.time()
                if 'time' in params:
                    try:requested=float(params['time'][0])
                    except ValueError:requested=datetime.fromisoformat(params['time'][0].replace('Z','+00:00')).timestamp()
                    if abs(at-requested)>10:raise ValueError('historical evaluation unsupported; use the original metrics source')
                if query=='1+1':result={'resultType':'scalar','result':[at,'2']}
                elif query.strip()=='sre_gateway_unhealthy':
                    unhealthy=not engine.readiness()['ready'];result={'resultType':'vector','result':[{'metric':{'deployment':store.deployment_id},'value':[at,'1']}] if unhealthy else []}
                else:
                    match=re.fullmatch(r'sre_rule_active\{sre_rule_id="([a-zA-Z0-9_.-]+)"\}(?:\s*==\s*1)?',query.strip())
                    if not match:raise ValueError('only managed instantaneous state queries supported')
                    result={'resultType':'vector','result':store.vector(match[1],at)}
                self.reply(200,{'status':'success','data':result});return
            if not post and path in ('/status','/preflight','/state','/releases','/plan'):
                if path=='/status':value=engine.readiness()
                elif path=='/preflight':value=engine.preflight or {'status':'not_checked'}
                elif path=='/state':
                    args=parse_qs(urlsplit(self.path).query);limit=min(1000,max(1,int(args.get('limit',['1000'])[0])));offset=max(0,int(args.get('offset',['0'])[0]));value=store.snapshot(limit,offset)
                elif path=='/plan':value=store.plan(validate_bundle(json.loads(Path(self.server.candidate).read_text())))
                else:
                    with store.lock,store.db() as db:value={'generation':store.current()[1],'releases':[dict(r) for r in db.execute('SELECT sha,created FROM releases ORDER BY created DESC')]}
                self.reply(200,value);return
            if role!='admin':self.reply(403,{'error':'admin_role_required'});return
            if post and path.startswith('/admin/'):
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON body required')
                body=json.loads(self.body());action=path.rsplit('/',1)[-1]
                if action in ('recovery','retire','unretire'):
                    result=store.administer(action,body['rule_id'],body['identity'],body['expected_revision'],body['reason'])
                elif action in ('activate','rollback'):
                    if not 4<=len(body.get('reason',''))<=1000:raise ValueError('activation reason required')
                    if action=='activate':candidate=validate_bundle(json.loads(Path(self.server.candidate).read_text()))
                    else:
                        with store.lock,store.db() as db:row=db.execute('SELECT payload FROM releases WHERE sha=?',(body['sha256'],)).fetchone()
                        if not row:raise ValueError('unknown installed release')
                        candidate=validate_bundle(json.loads(row[0]))
                    for key in ('admin_token_file','viewer_token_file'):token(candidate['config']['gateway'][key])
                    result=store.activate(candidate,body['expected_generation'],'admin',body['reason'])
                elif action=='backup':
                    folder=store.path.parent/'backups';folder.mkdir(exist_ok=True);result=store.backup(folder/('state-'+uuid.uuid4().hex+'.sqlite'))
                else:raise ValueError('unknown administrative API')
                self.reply(200,result);return
            self.reply(404,{'error':'not_found'})
        except Conflict:self.reply(409,{'error':'revision_or_identity_conflict'})
        except (ValueError,KeyError,TypeError) as exc:self.reply(422,{'error':str(exc)[:200]})
        except Exception:self.reply(503,{'status':'error','error':'state_or_service_unavailable; no empty success response'})


def serve(bundle_path,data_dir):
    candidate=validate_bundle(json.loads(Path(bundle_path).read_text()));deployment=candidate['config']['deployment_id']
    store=Store(Path(data_dir)/'state.sqlite',deployment);active,_=store.current();g=active['config']['gateway']
    for key in ('admin_token_file','viewer_token_file'):token(g[key])
    engine=Engine(store);server=BoundedServer((g.get('listen','0.0.0.0'),int(g.get('port',9480))),Handler)
    server.store=store;server.engine=engine;server.candidate=str(bundle_path)
    cert=g.get('tls_cert_file');key=g.get('tls_key_file')
    if bool(cert)!=bool(key):raise ValueError('TLS certificate and key must be provided together')
    if cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=engine.run,name='sre-poller',daemon=True);thread.start()
    def stop(*a):engine.stop.set();threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:server.serve_forever(poll_interval=.25)
    finally:engine.stop.set();thread.join(timeout=active['config']['limits']['query_timeout_seconds']+1);server.server_close()
