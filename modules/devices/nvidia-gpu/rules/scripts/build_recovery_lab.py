#!/usr/bin/env python3
"""Generate fixed, simulation-only lifecycle bindings; no production admission."""
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'rules/batch1-lab-catalog.json';source=json.loads(p.read_text())
rules=[]
for r in source['rules']:
 if r['key'] not in ('batch1_sram_threshold_exceeded','batch1_row_remap_failed'):continue
 expr=r['expression'];assert ' == 1) and' in expr
 clear=expr.replace(' == 1) and',' == 0) and',1)
 rules.append({'rule_id':r['source_rule_id'],'metric_name':('DCGM_FI_DEV_SRAM_EXCEEDED' if 'sram' in r['key'] else 'DCGM_FI_DEV_ROW_REMAP_FAILURE'),
               'trigger_expression':expr,'clear_expression':clear,
               'observation_expression':'('+expr+') or ('+clear+')'})
config={'schema_version':1,'scope':'simulation-only','production_admitted':False,
        'source_catalog_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'cluster_id':'batch1-sim-lab','uuids':['GPU-BATCH1-0000','GPU-BATCH1-0001'],
        'upstream_url':'http://prometheus:9090','poll_seconds':5,'max_poll_age_seconds':30,'rules':rules}
content=json.dumps(config,ensure_ascii=False,indent=2)+'\n';dest=ROOT/'rules/recovery-lab.json'
if '--check' in sys.argv:
 assert dest.read_text()==content,'recovery binding drift'
 print('PASS: 2 lifecycle trigger/clear expressions match batch1 source')
else:dest.write_text(content)
