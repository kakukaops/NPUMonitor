#!/usr/bin/env python3
"""Publish bounded simulation evidence and regenerate candidate cards."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import yaml
ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    runtime=json.loads((ROOT/'rules/comprehensive-runtime.json').read_text())
    reverse={v:k for k,v in (runtime['rule_ids']|runtime['health_rule_ids']).items()}
    out=ROOT/'monitoring/tests/comprehensive';out.mkdir(parents=True,exist_ok=True)
    reports=[];verified=set();cases=0
    for name in ['hardware','quality','platform','semantics','restart']:
        source=ROOT.parents[3]/f'.local/reports/comprehensive-{name}.json'
        data=json.loads(source.read_text())
        assert data['passed'] and not data.get('cleanup_error'),name
        assert all(case['passed'] for case in data['cases']),name
        if data.get('catalog_sha256'):assert data['catalog_sha256']==runtime['catalog_sha256']
        for case in data['cases']:
            if case.get('rule_id'):verified.add(reverse[case['rule_id']])
        verified.update(data.get('verified_rule_ids',[]));cases+=len(data['cases'])
        destination=out/source.name;shutil.copyfile(source,destination)
        reports.append({'selection':name,'path':str(destination.relative_to(ROOT)),'sha256':digest(destination),'passed_cases':len(data['cases'])})
    assert verified==set(runtime['rule_ids'])|set(runtime['health_rule_ids']),sorted((set(runtime['rule_ids'])|set(runtime['health_rule_ids']))-verified)
    for name in ['comprehensive-promtool.txt','comprehensive-unit.txt']:
        shutil.copyfile(ROOT.parents[3]/'.local/reports'/name,out/name)
    prom=(out/'comprehensive-promtool.txt').read_text();assert prom.count('SUCCESS')==6
    units=(out/'comprehensive-unit.txt').read_text();assert 'Ran 27 tests' in units and 'OK' in units
    data={'schema_version':'0.1.0','scope':'H100 physical training, CPU-only simulation',
          'recorded_at':datetime.now(timezone.utc).isoformat(),'passed':True,
          'production_admitted':False,'real_h100_tests':'not_run','nightingale_version':'9.3.0',
          'catalog_sha256':runtime['catalog_sha256'],'metric_contracts':42,'candidate_rules':45,
          'read_only_views':25,'verified_rule_ids':sorted(verified),'live_cases':cases,
          'offline':{'promtool_files':6,'cases':351,'assertions':830,'unit_tests':27},
          'reports':reports,
          'limitations':['No real H100, NVSwitch or Fabric Manager was exercised.',
                         'GPU modelName explicitly SIMULATED; software and topology admission remain unknown.',
                         'Demo counter window is 30 seconds; proposed production 300 seconds requires site approval.',
                         'Last-XID metric is not an ordered event log; no hardware repair or reset is performed.',
                         'Production packaging, upgrade/override lifecycle and external HA monitoring remain separate gates.']}
    (ROOT/'monitoring/h100-training/acceptance-results.yaml').write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False))
    subprocess.run([sys.executable,str(ROOT/'scripts/render_h100_training.py')],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/check_h100_training.py')],check=True)
    print(f'PASS: {cases} live cases, 45 rules; frozen bounded simulation evidence')

if __name__=='__main__':main()
