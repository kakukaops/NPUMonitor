"""Migrate only exact previous batch1 lab expressions; preserve user overrides."""
import json
from pathlib import Path
import urllib.parse
from n9e import API,unique
from suite import request
api=API()
bg=unique(api.call('GET','/busi-groups?all=true&limit=1000'),'H100草案模拟验收')
rows=api.call('GET',f'/busi-group/{bg["id"]}/alert-rules')
old={r['key']:r for r in json.loads(Path('/rules/batch1-lab-catalog.previous.json').read_text())['rules']}
new=json.loads(Path('/rules/batch1-lab-catalog.json').read_text())
updates=[]
for item in new['rules']:
 r=unique(rows,item['name'])
 assert r and r.get('annotations',{}).get('managed_by')=='gpu-alert-lab'
 q=r['rule_config']['queries'];assert len(q)==1
 assert q[0]['prom_ql'] in (old[item['key']]['expression'],item['expression']),'本地修改，停止'
 result=request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':item['expression']}))
 assert result['status']=='success'
 assert r['prom_for_duration'] in (old[item['key']]['for_seconds'],item['for_seconds']),'持续时间本地修改，停止'
 assert r['prom_eval_interval']==item['eval_interval_seconds'],'评估周期本地修改，停止'
 if q[0]['prom_ql']!=item['expression'] or r['prom_for_duration']!=item['for_seconds']:
  r['prom_for_duration']=item['for_seconds']
  q[0]['prom_ql']=item['expression']
  import hashlib
  r['annotations'].update(catalog_version=new['catalog_version'],catalog_sha256=hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
  updates.append(r)
for r in updates:
 api.call('PUT',f'/busi-group/{bg["id"]}/alert-rule/{r["id"]}',r)
 actual=api.call('GET',f'/alert-rule/{r["id"]}/pure')
 assert actual['rule_config']['queries']==r['rule_config']['queries']
 assert actual['prom_for_duration']==r['prom_for_duration']
 print('已修正并回读：'+r['name'])
