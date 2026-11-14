#!/usr/bin/env python3
"""Offline provenance completeness and scope checks; no network or rule changes."""
import hashlib
import json
from pathlib import Path
import re
import yaml

BASE=Path(__file__).resolve().parents[1]/'monitoring/os-sre'


def main():
    c=json.loads((BASE/'catalog.json').read_text());d=yaml.safe_load((BASE/'provenance.yaml').read_text())
    fixtures=yaml.safe_load((BASE/'tests.promtool.yaml').read_text())['tests'];names={t['name'] for t in fixtures}
    assert len(c['rules'])==46 and len(c['views'])==25 and len(d['rules'])==46
    assert len({r['rule_id'] for r in c['rules']})==46
    assert len(d['fields'])==37
    text=(BASE/'provenance.md').read_text()
    assert len(re.findall(r'^\| <a id=',text,re.M))==46
    refs=set(c['provenance_sources']);params=set(c['parameter_origins']);assert len(params)==12
    for rule in c['rules']:
        p=rule['provenance'];assert p['official_support'] and p['project_criterion'] and p['limitations']
        assert set(rule['source_ids'])<=refs and set(p['semantic_source_ids'])<=refs
        assert all(r['parameter_id'] in params for r in p['parameters'])
        assert set(p['test_case_ids'])<=names
        assert not p['production_case_evidence'] and p['real_hardware_validation']=='not_run'
        if rule['expression']:
            assert p['test_case_ids'],rule['rule_id']
            assert p['expression_sha256']==hashlib.sha256(rule['expression'].encode()).hexdigest()
        else:
            assert rule['status']=='blocked_missing_input' and not p['test_case_ids']
        card=(BASE/'cards'/(rule['rule_id']+'.md')).read_text()
        assert '## 来源与参数依据' in card and '../provenance.md#' in card
    for view in c['views']:
        assert view['provenance']['test_case_ids'] and not view['provenance']['production_case_evidence']
        assert set(view['provenance']['source_ids'])<=refs
    reviewed=json.loads((BASE/'evidence/source-review.json').read_text())
    retrieved={r['id']:r for r in reviewed if r.get('retrieved')}
    fixed=json.loads((BASE.parent/'tests/comprehensive/source-field-check.json').read_text())
    assert retrieved['fixed_fields']['sha256']==fixed['source_sha256']
    for k,v in c['provenance_sources'].items():
        if 'path' in v:assert (BASE/v['path']).is_file(),(k,v['path'])
        assert v['supports'] and v['does_not_support'] and v['locator'] and v['version']
    notify=next(r for r in c['rules'] if r['rule_id']=='os_sre.platform_notify_failure')
    assert not notify['expression'] and '源码' in notify['note']
    print('PASS: 46 per-rule origin rows, 25 views, 19 sources, 37 field locators, 12 parameter origins; evidence boundaries explicit')


if __name__=='__main__':main()
