"""Install, inspect, version, synchronize and recover a rules deployment."""
import argparse,hashlib,json,os,shutil,sqlite3,sys
from pathlib import Path
from urllib.request import Request,urlopen
from .bundle import compile_bundle,validate_bundle
from .store import Store


def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',default=os.environ.get('NPUMONITOR_RULES_BUNDLE','/etc/npumonitor/bundle.json'));p.add_argument('--data',default=os.environ.get('NPUMONITOR_RULES_DATA','/data'));p.add_argument('--api',default=os.environ.get('NPUMONITOR_RULES_API','http://127.0.0.1:9480'));p.add_argument('--token-file')
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('credentials');q.add_argument('--target',required=True)
    q=sub.add_parser('inspect-source');q.add_argument('--config',required=True);q.add_argument('--require-ready',action='store_true')
    q=sub.add_parser('compile');q.add_argument('--config',required=True);q.add_argument('--output',required=True)
    for name in ('init','serve','status','preflight','state','plan','backup','sync-plan','sync','source-auth','watchdog-init','watchdog'):sub.add_parser(name)
    q=sub.add_parser('activate');q.add_argument('--expected-generation',type=int,required=True);q.add_argument('--reason',required=True)
    q=sub.add_parser('rollback');q.add_argument('--sha256',required=True);q.add_argument('--expected-generation',type=int,required=True);q.add_argument('--reason',required=True)
    for name in ('recovery','retire','unretire'):
        q=sub.add_parser(name);q.add_argument('--rule',required=True);q.add_argument('--identity',required=True,help='JSON collector/hardware identity');q.add_argument('--expected-revision',type=int,required=True);q.add_argument('--reason',required=True)
    q=sub.add_parser('restore');q.add_argument('--archive',required=True);q.add_argument('--sha256',required=True);q.add_argument('--target',required=True)

    for name in ('sync-rollback','sync-recover'):
        q=sub.add_parser(name);q.add_argument('--operation',required=True)
    args=p.parse_args()
    if args.command=='credentials':
        import secrets
        folder=Path(args.target);folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o700)
        for name in ('admin-token','viewer-token'):
            path=folder/name
            if not path.exists():
                with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:f.write(secrets.token_urlsafe(36)+'\n')
            path.chmod(0o600)
        print(json.dumps({'credentials_prepared':True,'existing_credentials_preserved':True}));return
    if args.command=='inspect-source':
        from .source import Source
        value=Source(compile_bundle(json.loads(Path(args.config).read_text()))).preflight();print(json.dumps(value,ensure_ascii=False,indent=2))
        if args.require_ready and not (value.get('production_contract') or {}).get('ready'):raise SystemExit(2)
        return
    if args.command=='compile':
        value=compile_bundle(json.loads(Path(args.config).read_text()));output=Path(args.output);temporary=output.with_suffix('.tmp');
        with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        temporary.chmod(0o600);temporary.replace(output);print(json.dumps({'compiled':True,'sha256':value['sha256'],'rules':len(value['rules'])}));return
    if args.command=='restore':
        archive=Path(args.archive);target=Path(args.target)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=args.sha256:raise ValueError('backup checksum mismatch')
        if target.exists() and any(target.iterdir()):raise ValueError('restore target must be empty')
        with sqlite3.connect('file:'+str(archive.resolve())+'?mode=ro',uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('invalid backup database')
            deployment=db.execute('SELECT value FROM meta WHERE key="deployment"').fetchone()[0]
        target.mkdir(parents=True,exist_ok=True);destination=target/'state.sqlite'
        with os.fdopen(os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(archive.read_bytes())
        destination.chmod(0o600);Store(destination,deployment).current();print(json.dumps({'restored':True,'deployment_id':deployment}));return
    candidate=validate_bundle(json.loads(Path(args.bundle).read_text()));data=Path(args.data);deployment=candidate['config']['deployment_id']
    if args.command=='init':print(json.dumps(Store.initialize(data/'state.sqlite',candidate)));return
    if args.command in ('watchdog-init','watchdog'):
        from .watchdog import Watchdog,serve_watchdog
        cfg=candidate['config']['watchdog']
        if args.command=='watchdog-init':print(json.dumps(Watchdog.initialize(data/'watchdog.sqlite',cfg,deployment)))
        else:serve_watchdog(data/'watchdog.sqlite',cfg,deployment)
        return
    if args.command=='serve':
        from .server import serve
        serve(args.bundle,args.data);return
    if args.command.startswith('sync') or args.command=='source-auth':
        from .nightingale import Sync
        store=Store(data/'state.sqlite',deployment);sync=Sync(store)
        if args.command=='sync-plan':
            plan=sync.plan();value={k:v for k,v in plan.items() if k!='items'};value['items']=[{k:r[k] for k in ('rule_id','action')} for r in plan['items']]
        elif args.command=='sync':value=sync.apply()
        elif args.command=='source-auth':value=sync.rotate_source_auth()
        elif args.command=='sync-recover':value=sync.recover(args.operation)
        else:value=sync.rollback(args.operation)
        print(json.dumps(value,ensure_ascii=False));return
    file=args.token_file or candidate['config']['gateway']['admin_token_file'];token=Path(file).read_text().strip()
    body=None;path='/'+args.command
    if args.command in ('activate','rollback'):
        body={'expected_generation':args.expected_generation,'reason':args.reason};path='/admin/'+args.command
        if args.command=='rollback':body['sha256']=args.sha256
    elif args.command in ('recovery','retire','unretire'):
        body={'rule_id':args.rule,'identity':json.loads(args.identity),'expected_revision':args.expected_revision,'reason':args.reason};path='/admin/'+args.command
    elif args.command=='backup':body={};path='/admin/backup'
    request=Request(args.api.rstrip('/')+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urlopen(request,timeout=30) as response:print(json.dumps(json.load(response),ensure_ascii=False))

if __name__=='__main__':main()
