#!/usr/bin/env python3
"""Verify candidate contracts, source bindings, test coverage and generated cards."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml
ROOT=Path(__file__).resolve().parents[1]

def main():
    catalog=json.loads((ROOT/'rules/comprehensive-catalog.json').read_text())
    lifecycle=json.loads((ROOT/'rules/comprehensive-lifecycle.json').read_text())
    health=json.loads((ROOT/'rules/comprehensive-health.json').read_text())
    assert len(catalog['fields'])==42 and len(catalog['rules'])==40 and len(health)==5
    assert len({r['rule_id'] for r in catalog['rules']})==40
    for rule in catalog['rules']:
        assert set(rule['input_fields'])<=set(catalog['fields']),rule['rule_id']
        assert rule['production_default']=='disabled'
        if rule['kind']=='stateful':
            state=next(r for r in lifecycle['rules'] if r['rule_id']==rule['rule_id'])
            assert set(state['entity_ids'])<=set(catalog['entities'])
            assert state['confirm_seconds']==rule['desired_for_seconds']
            for eid in state['entity_ids']:
                if eid.startswith('SWITCH'):assert 'UUID' not in catalog['entities'][eid]
    for script in ['build_h100_training.py','build_h100_training_tests.py','render_h100_training.py']:
        subprocess.run([sys.executable,str(ROOT/'scripts'/script),'--check'],check=True)
    source=json.loads((ROOT/'monitoring/tests/comprehensive/source-field-check.json').read_text())
    checked={r['input_name']:r for r in source['checked_fields']}
    for name,spec in catalog['fields'].items():
        if spec['dcgm_field_id'] is not None:
            assert checked[name]['passed'] and checked[name]['field_id']==spec['dcgm_field_id']
    tests=yaml.safe_load((ROOT/'monitoring/tests/h100-training.promtool.yaml').read_text())['tests']
    cases=len(tests);assertions=sum(len(t.get('promql_expr_test',[])) for t in tests)
    evidence=ROOT/'monitoring/h100-training/acceptance-results.yaml'
    if evidence.exists():
        report=yaml.safe_load(evidence.read_text())
        expected={r['rule_id'] for r in catalog['rules']}|{r['key'] for r in health}
        assert set(report['verified_rule_ids'])==expected
        assert report['catalog_sha256']==hashlib.sha256((ROOT/'rules/comprehensive-catalog.json').read_bytes()).hexdigest()
        assert report['real_h100_tests']=='not_run'
        assert report['live_cases']==sum(i['passed_cases'] for i in report['reports'])
        for item in report['reports']:
            path=ROOT/item['path'];assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],item['path']
            original=json.loads(path.read_text());assert original['passed'] and all(c['passed'] for c in original['cases'])
    print(f'PASS: 42 metric contracts, 45 rules, {cases} new cases / {assertions} assertions, cards and evidence bindings')

if __name__=='__main__':main()
