#!/usr/bin/env python3
"""Check formal card/scope/fixture consistency. Requires documentation PyYAML."""
import hashlib
import json
from pathlib import Path
import re
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]/'monitoring'


def read(name):return yaml.safe_load((ROOT/name).read_text())


def main():
    metrics=read('catalog/metrics.yaml')['metrics']
    rules=read('catalog/rules.yaml')['rules']
    sources={r['source_id'] for r in read('catalog/sources.yaml')['sources']}
    mid={m['metric_id'] for m in metrics};rid={r['rule_id'] for r in rules}
    assert len(mid)==len(metrics) and len(rid)==len(rules)
    binding=read('catalog/batch1-binding.yaml')
    digest=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
    assert binding['production_admitted'] is False
    uuids=[u for t in binding['targets'] for u in t['expected_gpu_uuids']]
    assert len(uuids)==len(set(uuids)) and len(binding['required_fields'])==len(set(binding['required_fields']))
    checks=0
    for m in metrics:
        assert set(m['source_ids'])<=sources
        assert set(m['related_rule_ids'])<=rid
        assert (ROOT/'catalog'/m['documentation']).is_file()
        assert m['verification']['real_cluster_tests']=='not_run'
    for r in rules:
        assert set(r['metric_ids'])<=mid
        assert set(r['dependencies']['source_ids'])<=sources
        assert set(r['dependencies'].get('companion_rules',[]))<=rid
        assert r['default_policy']=='disabled' and r['lifecycle']=='draft'
        assert r['tests']['nightingale_tests']=='not_run' and r['tests']['real_cluster_tests']=='not_run'
        text=(ROOT/'catalog'/r['documentation']).read_text()
        assert re.search(r'```promql\n(.*?)\n```',text,re.S).group(1)==r['expression'],r['rule_id']
        fixture=read('catalog/'+r['tests']['fixture'])
        expected_prefix=('group by ('+','.join(r['identity'])+') (') if r.get('binding') else 'group by (cluster_id, UUID) ('
        expected=expected_prefix+r['expression']+')'
        found=[a for t in fixture['tests'] for a in t['promql_expr_test'] if a['expr']==expected]
        assert found,r['rule_id']
        if r.get('binding'):
            assert r['binding']['sha256']==digest
            assert r['binding']['production_admitted'] is False
            assert len(found)==len(fixture['tests']),r['rule_id']
            # timestamp must apply to raw selectors, never label_replace/vector results.
            assert 'timestamp(label_replace' not in r['expression']
        checks+=len(found)
    for path in ROOT.rglob('*.md'):
        path = path.resolve()
        for link in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            target=link.strip('<>')
            if '://' not in target and not target.startswith('#'):
                assert (path.parent/target.split('#')[0]).is_file(),(path,target)
    result=read('tests/h100_batch1-results.yaml')
    assert result['fixture_sha256']==hashlib.sha256((ROOT/'tests/h100_batch1.promtool.yaml').read_bytes()).hexdigest()
    assert result['binding_sha256']==digest
    recovery=json.loads((ROOT.parent/'rules/recovery-lab.json').read_text())
    assert recovery['production_admitted'] is False
    recovery_fixture=read('tests/hardware-lifecycle.promtool.yaml')
    for rule in recovery['rules']:
        expected='max by (cluster_id,UUID,metric_name) ('+rule['observation_expression']+')'
        found=[a for t in recovery_fixture['tests'] for a in t['promql_expr_test'] if a['expr']==expected]
        assert len(found)==len(recovery_fixture['tests'])
        checks+=len(found)
    lifecycle=read('tests/hardware-lifecycle-results.yaml')
    assert lifecycle['result']=='passed' and lifecycle['production_admitted'] is False
    expr_result=read('tests/hardware-lifecycle-promtool-results.yaml')
    assert expr_result['result']=='passed' and expr_result['fixture_sha256']==hashlib.sha256((ROOT/'tests/hardware-lifecycle.promtool.yaml').read_bytes()).hexdigest()
    assert lifecycle['binding_sha256']==hashlib.sha256(json.dumps(recovery,sort_keys=True).encode()).hexdigest()
    review_result=read('tests/ecc-xid-review-results.yaml')
    review_catalog=read('catalog/ecc-xid-review-queries.yaml')
    review_fixture=read('tests/ecc-xid-review.promtool.yaml')
    assert review_result['result']=='passed' and review_catalog['production_admitted'] is False
    for key,name in [('fixture_sha256','tests/ecc-xid-review.promtool.yaml'),
                     ('catalog_sha256','catalog/ecc-xid-review-queries.yaml')]:
        assert review_result[key]==hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    review_expressions={f"max by (cluster_id,UUID) ({q['expression']})"
                        for q in review_catalog['queries'] if q['default_policy']=='disabled'}
    assertions=[a for case in review_fixture['tests'] for a in case['promql_expr_test']]
    assert {a['expr'] for a in assertions}==review_expressions
    assert len(assertions)==review_result['assertions']
    assert len(review_fixture['tests'])==review_result['cases']
    assert len(review_expressions)==review_result['queries']
    checks+=len(assertions)
    thermal_result=read('tests/thermal-links-review-results.yaml')
    thermal_catalog=read('catalog/thermal-links-review-queries.yaml')
    thermal_fixture=read('tests/thermal-links-review.promtool.yaml')
    thermal_json=json.loads((ROOT/'catalog/thermal-links-review-queries.json').read_text())
    assert thermal_catalog==thermal_json and thermal_catalog['production_admitted'] is False
    assert thermal_result['result']=='passed' and thermal_result['streaming']['result']=='passed'
    for key,name in [('fixture_sha256','tests/thermal-links-review.promtool.yaml'),
                     ('catalog_sha256','catalog/thermal-links-review-queries.yaml'),
                     ('json_catalog_sha256','catalog/thermal-links-review-queries.json')]:
        assert thermal_result[key]==hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    thermal_expressions={f"max by (cluster_id,UUID) ({q['expression']})"
                         for q in thermal_catalog['queries'] if q['default_policy']=='disabled'}
    thermal_assertions=[a for case in thermal_fixture['tests'] for a in case['promql_expr_test']]
    assert {a['expr'] for a in thermal_assertions}==thermal_expressions
    assert len(thermal_assertions)==thermal_result['assertions']
    assert len(thermal_fixture['tests'])==thermal_result['cases']
    assert len(thermal_expressions)==thermal_result['queries']
    checks+=len(thermal_assertions)
    print(f'PASS: {len(metrics)}指标/输入卡、{len(rules)}draft规则、2个实验保持/解除判据、{len(review_expressions)}个ECC/XID查询、{len(thermal_expressions)}个维护/热/互联查询、{checks}一致的求值断言；正式默认禁用，现场绑定夜莺/H100未测；实验副本另记录')
    return 0


if __name__=='__main__':
    try: sys.exit(main())
    except (AssertionError,OSError,ValueError,KeyError,TypeError) as error:
        print('FAIL: '+str(error),file=sys.stderr);sys.exit(1)
