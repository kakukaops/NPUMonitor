#!/usr/bin/env python3
"""Bind reviewed expression snapshots to an isolated streaming simulation job."""
import hashlib
import json
from pathlib import Path
import sys
import yaml
ROOT = Path(__file__).resolve().parents[1]
source = ROOT/'monitoring/catalog/rules.yaml'
rules = yaml.safe_load(source.read_text())['rules']
replacements = {'fixture-cluster': 'batch1-sim-lab', 'fixture-node:9400': 'gpu-simulator:9400',
                'GPU-FIXTURE-0000': 'GPU-BATCH1-0000', 'GPU-FIXTURE-0001': 'GPU-BATCH1-0001',
                '"dcgm"': '"h100-batch1-simulator"'}
items = []
for r in rules:
    if not r.get('binding'):
        continue
    expression = r['expression']
    for old, new in replacements.items():
        expression = expression.replace(old, new)
    assert 'fixture-' not in expression and 'GPU-FIXTURE' not in expression
    items.append({'key': 'batch1_'+r['rule_id'].split('.',1)[1],
                  'name': 'H100草案模拟-'+r['rule_id'].split('.',1)[1],
                  'expression': expression, 'for_seconds': (r['parameters']['for_seconds']['value']+r['parameters']['eval_interval_seconds']['value'] if r['parameters']['for_seconds']['value'] else 0),
                  'desired_for_seconds': r['parameters']['for_seconds']['value'],
                  'duration_adapter': 'n9e_9.3.0_counts_first_eval_as_one_interval',
                  'eval_interval_seconds': r['parameters']['eval_interval_seconds']['value'],
                  'severity': r['severity']['nightingale'],
                  'note': '仅合成联调。结束表示条件退出，不能解释为硬件修复；缺数/无效需检查质量告警。',
                  'source_rule_id': r['rule_id'],
                  'source_expression_sha256': hashlib.sha256(r['expression'].encode()).hexdigest()})
assert len(items)==8
catalog={'catalog_version':'batch1-lab-0.1.2','scope':'simulation-only',
         'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'rules':items}
path=ROOT/'rules/batch1-lab-catalog.json'
content=json.dumps(catalog, ensure_ascii=False, indent=2)+'\n'
if '--check' in sys.argv:
    assert path.read_text()==content, 'batch1 catalog drift; rebuild then review'
    print('PASS: 8 batch1 lab expressions match reviewed source and label substitutions')
else:
    path.write_text(content)
