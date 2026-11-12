"""Platform-only operations; no running monitor or Prometheus is required."""
import argparse,hashlib,json,os,re,shutil,sqlite3,tarfile,tempfile
from pathlib import Path
from urllib.request import Request,urlopen

def restore(archive,target):
    target=Path(target)
    if target.exists() and any(target.iterdir()):raise ValueError('恢复目标必须为空目录')
    with tempfile.TemporaryDirectory() as tmp:
        stage=Path(tmp)
        with tarfile.open(archive) as tar:
            for m in tar.getmembers():
                p=Path(m.name)
                if p.is_absolute() or '..' in p.parts or m.issym() or m.islnk():raise ValueError('备份路径无效')
            tar.extractall(stage,filter='data')
        db=sqlite3.connect(stage/'registry.sqlite')
        try:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('平台数据库完整性失败')
            metadata=db.execute("SELECT payload FROM objects WHERE kind='meta' AND id='platform'").fetchone()
            if not metadata or not json.loads(metadata[0]).get('platform_id'):raise ValueError('平台身份缺失')
            records=[json.loads(r[0]) for r in db.execute("SELECT payload FROM objects WHERE kind='model'")]
            for record in records:
                if Path(record['artifact']).name!=record['artifact'] or not re.fullmatch('[a-f0-9]{64}',record['dataset_sha256']):raise ValueError('平台制品路径无效')
                if hashlib.sha256((stage/'models'/record['artifact']).read_bytes()).hexdigest()!=record['artifact_sha256']:raise ValueError('平台制品摘要不匹配')
                if hashlib.sha256((stage/'datasets'/(record['dataset_sha256']+'.json')).read_bytes()).hexdigest()!=record['dataset_sha256']:raise ValueError('平台数据摘要不匹配')
        finally:db.close()
        target.mkdir(parents=True,exist_ok=True)
        for p in stage.iterdir():
            if p.is_dir():shutil.copytree(p,target/p.name)
            else:shutil.copy2(p,target/p.name)
    return {'restored_to':str(target),'models':len(records),'scope':'reference model platform only'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['info','backup','restore']);parser.add_argument('archive',nargs='?');parser.add_argument('target',nargs='?');args=parser.parse_args()
    if args.command=='restore':print(json.dumps(restore(args.archive,args.target)))
    else:
        token=Path(os.environ.get('MODEL_PLATFORM_TOKEN_FILE','/run/secrets/model-platform-token')).read_text().strip()
        req=Request('http://localhost:9470/v1/'+('backups' if args.command=='backup' else 'info'),data=b'{}' if args.command=='backup' else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        print(json.dumps(json.load(urlopen(req,timeout=60))))
