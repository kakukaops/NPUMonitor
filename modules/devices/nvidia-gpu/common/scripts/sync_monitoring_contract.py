#!/usr/bin/env python3
"""Publish/check derived GPU contracts. Edit doc14 first, never this output."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
GPU=Path(__file__).resolve().parents[2]
ROOT=GPU.parents[2]
RULES=GPU/'rules'
DOC=RULES/'docs/14-GPU监控指标与告警规则说明表.md'
INDEX=DOC.with_suffix('.coverage.json')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    subprocess.run([sys.executable,str(RULES/'scripts/check_gpu_monitoring_master.py')],check=True)
    index=json.loads(INDEX.read_text());records=index['candidate_dispositions']+index['beyond_candidate_contracts'];by_id={r['metric_id']:r for r in records}
    category=None;categories={}
    for line in DOC.read_text().splitlines():
        if line.startswith('### ') and 'id="category-' in line:category=re.sub(r'^.*</a>[AB]\.\d+ ','',line).split('（')[0]
        if line.startswith('| <a id="m-'):
            mid=re.search(r'\*\*`([^`]+)`\*\*',line)[1];categories[mid]=category
    assert set(categories)==set(by_id),'Every metric requires a category'
    source={'document':str(DOC.relative_to(ROOT)),'revision':index['document_revision'],'sha256':hashlib.sha256(DOC.read_bytes()).hexdigest()}
    metrics={mid:dict(r,category=categories[mid]) for mid,r in sorted(by_id.items())}
    registry={'schema_version':1,'generated':True,'authority':source,'identity':['job','instance','UUID'],'metrics':metrics}
    names={name for r in records for name in r['names_and_aliases']}
    for path in [RULES/'monitoring/os-sre/catalog.json',RULES/'runtime/master/catalog.json',RULES/'runtime/production/catalog.json']:
        catalog=json.loads(path.read_text())
        assert all(not n.startswith('DCGM_') or n in names for n in catalog['metric_contracts']),f'Undeclared field in {path}'
    binding=json.loads((GPU/'ml/config/bindings.json').read_text());scenarios=json.loads((GPU/'ml/config/dcgm-scenarios.json').read_text())['scenarios'];features={}
    units={'°C':'celsius','W':'watts','MHz':'MHz','%':'percent','MiB':'MiB'}
    required=set()
    for scenario in scenarios.values():
        required.update(scenario['required']);required.update(scenario['targets']);required.update(scenario['features'])
    for feature in sorted(required):
        b=binding['metrics'][feature];r=by_id[b['metric_id']]
        assert r['requirement']!='排除',f'Excluded ML feature: {feature}'
        assert b['name'] in r['names_and_aliases'],f'Undeclared ML field: {feature}'
        assert units.get(b['unit'],b['unit'])==r['semantic_unit'],f'ML unit mismatch: {feature}'
        features[feature]={'metric_id':b['metric_id'],'name':b['name'],'unit':r['semantic_unit'],'category':categories[b['metric_id']],'source_anchor':r['doc_anchor']}
    ml={'schema_version':1,'generated':True,'authority':source,'features':features,'identity':registry['identity'],'legacy_binding_identity':binding['identity'],'identity_migration_required':binding['identity']!=registry['identity'],'scope':'Only active DCGM scenarios validated; legacy job-context templates excluded; no model retraining implied'}
    for path,data in [(GPU/'common/monitoring/catalog/monitoring-contract.json',registry),(GPU/'ml/config/monitoring-contract.json',ml)]:
        expected=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
        if args.check:
            assert path.exists() and path.read_text()==expected,f'Stale generated contract: {path}'
        else:path.write_text(expected)
    print(f'PASS: doc14 authority; {len(metrics)} classified metrics; three rule catalogs; {len(features)} active ML features')
    if ml['identity_migration_required']:print('PENDING: legacy ML identity migration; registry does not certify runtime alignment')
if __name__=='__main__':main()
