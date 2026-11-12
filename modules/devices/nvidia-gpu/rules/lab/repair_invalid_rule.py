"""Targeted lab-0.1.0 -> 0.1.1 NaN-rule expression fix; preserves other fields."""
import hashlib
import json
from pathlib import Path
from n9e import API, GROUP, unique

catalog = json.loads(Path('/rules/lab-catalog.json').read_text())
item = next(r for r in catalog['rules'] if r['key'] == 'gpu_lab_invalid_temp')
new_expr = item['expression']
# Only migrate the exact old test expression; never replace another local expression.
old_expr = new_expr.removeprefix('(').removesuffix(') == 1').replace(' != bool ', ' != ')
api = API()
bg = unique(api.call('GET', '/busi-groups?all=true&limit=1000'), GROUP)
rule = unique(api.call('GET', f'/busi-group/{bg["id"]}/alert-rules'), item['name'])
if not rule or rule.get('annotations', {}).get('managed_by') != 'gpu-alert-lab':
    raise SystemExit('FAIL: 未找到本实验管理的规则')
queries = rule['rule_config']['queries']
if len(queries) != 1:
    raise SystemExit('FAIL: 规则结构已修改，停止自动修正')
if queries[0]['prom_ql'] == new_expr:
    print('PASS: 无效温度规则已是修正版')
elif queries[0]['prom_ql'] != old_expr:
    raise SystemExit('FAIL: 表达式已有本地改动，停止避免覆盖')
else:
    queries[0]['prom_ql'] = new_expr
    rule['annotations'].update(catalog_version=catalog['catalog_version'], catalog_sha256=
        hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
    api.call('PUT', f'/busi-group/{bg["id"]}/alert-rule/{rule["id"]}', rule)
    verified = api.call('GET', f'/alert-rule/{rule["id"]}/pure')
    if verified['rule_config']['queries'][0]['prom_ql'] != new_expr:
        raise SystemExit('FAIL: 修正后回读不一致')
    print('PASS: 只更新无效温度检测表达式，已回读确认')
