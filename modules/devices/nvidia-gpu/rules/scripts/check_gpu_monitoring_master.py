#!/usr/bin/env python3
"""Check the normative Markdown against candidate and implemented inventories.

The JSON file is a derived index: edit the Markdown first, then refresh it.
Coverage passing does not certify deployment or official semantic correctness.
"""
import argparse, copy, hashlib, html, json, re, sys
from collections import Counter
from pathlib import Path
import yaml

MODULE = Path(__file__).resolve().parents[1]
DOCUMENT = MODULE / 'docs/14-GPU监控指标与告警规则说明表.md'
INDEX = DOCUMENT.with_suffix('.coverage.json')
CANDIDATES = MODULE.parent / 'common/monitoring/catalog/metric-inventory.yaml'
CATALOG = MODULE / 'monitoring/os-sre/catalog.json'
REQUIREMENTS = {'必选', '条件必选', '可选', '外部', '排除'}
STATES = {'current_contract', 'current_feature', 'partial_metadata', 'planned', 'blocked', 'external_gap', 'excluded', 'production_contract', 'metadata_contract', 'production_feature'}
FEATURE_RULES = {
    'prometheus.target_up': 'os_sre.collector_down',
    'inventory.expected_devices': 'os_sre.entity_missing',
    'inventory.expected_links': 'os_sre.gpu_link_down',
    'prometheus.field_quality': 'os_sre.input_invalid',
    'platform.evaluation_status': 'os_sre.platform_evaluation_stall',
}
GATES = ('gate-nvlink-state-policy', 'gate-unit-contract', 'gate-implementation-parity')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def cells(line):
    return [html.unescape(c.strip()) for c in line.strip().strip('|').split('|')]


def marked(cell, label):
    found = re.search(r'\*\*' + re.escape(label) + r'：\*\*(.*?)(?:<br>|$)', cell)
    require(found is not None and bool(found[1].strip()), 'missing contract attribute: ' + label)
    return found[1].strip()


def extract(text):
    require('本模块权威基线' in text, 'master authority declaration missing')
    revision = re.search(r'规范修订：([^（\s]+)', text)
    require(revision, 'document revision missing')
    anchors = re.findall(r'<a id="([^"]+)"></a>', text)
    require(len(anchors) == len(set(anchors)), 'duplicate document anchor')
    main, appendix = text.split('## 附录A：', 1)
    part_a, rest = appendix.split('## 附录B：', 1)
    part_b = rest.split('### 外部输入', 1)[0]
    records = []
    for part, origin in ((part_a, 'candidate'), (part_b, 'beyond_candidate')):
        category_heading = None
        for line in part.splitlines():
            if line.startswith('### ') and 'id="category-' in line:
                category_heading = line
            if not line.startswith('| <a id='):
                continue
            require(category_heading, 'contract row must belong to a visible category section')
            row = cells(line)
            require(len(row) == 6, 'contract table must have six columns')
            match = re.search(r'<a id="([^"]+)"></a>\*\*`([^`]+)`\*\*', row[0])
            require(match, 'contract anchor or stable metric ID missing')
            field = re.search(r'字段ID：([^<]+)', row[0])
            require(field, 'field identifier or non-DCGM declaration missing')
            field_id = int(field[1]) if field[1].strip().isdigit() else None
            names = sorted(set(re.findall(r'`(DCGM_[A-Z0-9_]+)`', row[0])))
            record = {
                'metric_id': match[2], 'origin': origin, 'doc_anchor': match[1],
                'field_id': field_id, 'names_and_aliases': names,
                'requirement': marked(row[1], '生产要求'),
                'implementation_status': marked(row[1], '实现状态'),
                'enablement': marked(row[1], '启用条件'),
                'semantic_type': marked(row[2], '语义类型'),
                'semantic_unit': marked(row[2], '语义单位'),
                'entity': marked(row[2], '实体'), 'identity': marked(row[2], '身份'),
                'validity': marked(row[2], '有效性'), 'applicability': marked(row[2], '适用性'),
                'rationale': marked(row[3], '采用理由'), 'rule_and_recovery': marked(row[3], '规则与恢复'),
                'sources': re.findall(r'\]\(([^)]+)\)', row[4]),
            }
            records.append(record)
    main_rule_ids = re.findall(r'`(os_sre\.[a-z_]+)`', '\n'.join(l for l in main.splitlines() if l.startswith('| ')))
    gates = []
    for gate in GATES:
        pattern = r'<a id="' + gate + r'"></a>\s*\n### [^\n]+\n\n\*\*门禁状态：\*\*(open|closed)'
        match = re.search(pattern, text)
        require(match, 'explicit semantic gate status missing: ' + gate)
        gates.append({'gate': gate, 'status': match[1]})
    return {'revision': revision[1], 'records': records, 'rule_ids': main_rule_ids, 'gates': gates, 'anchors': anchors}


def validate(model, candidate_ids, catalog):
    records = model['records']; ids = [r['metric_id'] for r in records]
    require(len(ids) == len(set(ids)), 'duplicate metric ID')
    reviewed = {r['metric_id'] for r in records if r['origin'] == 'candidate'}
    require(reviewed == set(candidate_ids), 'candidate inventory mismatch: missing=' + str(sorted(set(candidate_ids)-reviewed)) + '; extra=' + str(sorted(reviewed-set(candidate_ids))))
    production_path=MODULE/'runtime/production/catalog.json'
    production=json.loads(production_path.read_text()) if production_path.exists() else {'rules':[],'metric_contracts':{}}
    production_names={n for n in production['metric_contracts'] if n.startswith('DCGM_')}
    required_rule_ids = {r['rule_id'] for r in catalog['rules']}|{r['rule_id'] for r in production['rules']}
    require(len(model['rule_ids']) == len(set(model['rule_ids'])), 'duplicate rule ID in main table')
    require(set(model['rule_ids']) == required_rule_ids, 'implemented rules and master main table differ')
    current_names = {n for n in catalog['metric_contracts'] if n.startswith('DCGM_')}
    covered = set()
    field_ids = []
    for record in records:
        mid = record['metric_id']; status = record['implementation_status']; names = set(record['names_and_aliases'])
        if record['origin'] == 'candidate':
            require(record['field_id'] == candidate_ids[mid], 'candidate field ID mismatch: ' + mid)
        require(record['requirement'] in REQUIREMENTS, 'unknown requirement: ' + mid)
        require(status in STATES, 'unknown implementation state: ' + mid)
        require(record['doc_anchor'] in model['anchors'], 'missing document anchor: ' + mid)
        require(record['sources'], 'contract has no cited source: ' + mid)
        if record['field_id'] is not None:
            require(names, 'DCGM field has no canonical/alias name: ' + mid)
            field_ids.append(record['field_id'])
        if status == 'current_contract':
            require(bool(names & current_names), 'false implemented metric claim: ' + mid)
            covered.update(names & current_names)
        elif status=='production_contract':
            require(bool(names & production_names), 'false production contract claim: '+mid)
            covered.update(names & current_names)
        elif status=='metadata_contract':
            require(mid in ('nvidia.driver_version','nvidia.gpu_name','nvidia.gpu_uuid'), 'unproved metadata contract: '+mid)
        elif status=='production_feature':
            require(mid=='inventory.hardware_stack', 'unproved production feature: '+mid)
        elif names & current_names:
            require(status == 'blocked', 'current field incorrectly classified as unimplemented: ' + mid)
            covered.update(names & current_names)
        if status == 'current_feature':
            require(mid in FEATURE_RULES and FEATURE_RULES[mid] in required_rule_ids, 'unproved current feature: ' + mid)
        if status == 'partial_metadata':
            require(mid == 'nvidia.gpu_uuid' and any('UUID' in c['identity_labels'] for c in catalog['metric_contracts'].values()), 'unproved metadata support: ' + mid)
        if record['requirement'] == '排除':
            require(status == 'excluded', 'excluded item must not claim implementation: ' + mid)
        if record['requirement'] == '外部':
            require(record['field_id'] is None and status == 'external_gap', 'external item misrepresented as DCGM/current: ' + mid)
    require(len(field_ids) == len(set(field_ids)), 'same DCGM field ID counted twice')
    require(covered == current_names, 'implemented fields not fully traced: ' + str(sorted(current_names-covered)))
    gaps = [r['metric_id'] for r in records if r['requirement'] == '必选' and r['implementation_status'] not in ('current_contract', 'current_feature', 'production_contract', 'metadata_contract', 'production_feature')]
    blockers = [g['gate'] for g in model['gates'] if g['status'] != 'closed']
    return {'mandatory_implementation_gaps': gaps, 'open_semantic_gates': blockers, 'production_ready': not (gaps or blockers)}


def authority_paths():
    docs = [p for p in sorted((MODULE/'docs').glob('*.md')) if p != DOCUMENT]
    entries = [MODULE/'README.md', MODULE/'monitoring/README.md', MODULE/'monitoring/os-sre/README.md', MODULE/'rules/README.md', MODULE/'runtime/README.md']
    return docs + entries


def load():
    text = DOCUMENT.read_text(); model = extract(text)
    candidates = yaml.safe_load(CANDIDATES.read_text())['metrics']
    raw_ids = [r['metric_id'] for r in candidates]
    require(len(raw_ids) == len(set(raw_ids)), 'duplicate ID in source candidate inventory')
    candidate_ids = {r['metric_id']: r.get('dcgm_field_id') for r in candidates}
    catalog = json.loads(CATALOG.read_text())
    parity = validate(model, candidate_ids, catalog)
    for p in authority_paths():
        require(DOCUMENT.name in p.read_text(), 'subordinate document authority link missing: ' + str(p.relative_to(MODULE)))
    result = {
        'schema_version': 1, 'derived_from': DOCUMENT.name, 'document_revision': model['revision'],
        'document_sha256': sha(DOCUMENT.read_bytes()), 'candidate_inventory_sha256': sha(CANDIDATES.read_bytes()),
        'implementation_catalog_sha256': sha(CATALOG.read_bytes()),
        'scope': 'H100 physical baseline; conditional capabilities/version contracts; not universal NVIDIA field coverage',
        'candidate_dispositions': [r for r in model['records'] if r['origin']=='candidate'],
        'beyond_candidate_contracts': [r for r in model['records'] if r['origin']=='beyond_candidate'],
        'implemented_dcgm_fields': sorted(n for n in catalog['metric_contracts'] if n.startswith('DCGM_')),
        'production_contract_dcgm_fields':sorted(n for n in json.loads((MODULE/'runtime/production/catalog.json').read_text())['metric_contracts'] if n.startswith('DCGM_')),
        'implemented_rule_ids': sorted(model['rule_ids']), 'semantic_gates': model['gates'],
        'requirements_summary': dict(Counter(r['requirement'] for r in model['records'] if r['origin']=='candidate')),
        'production_alignment': parity,
    }
    return model, candidate_ids, catalog, result


def self_test(model, ids, catalog):
    mutations = []
    bad = copy.deepcopy(model); bad['records'] = bad['records'][1:]; mutations.append(('omitted candidate', bad))
    bad = copy.deepcopy(model); bad['records'].append(copy.deepcopy(bad['records'][0])); mutations.append(('duplicate metric', bad))
    bad = copy.deepcopy(model); bad['anchors'].remove(bad['records'][0]['doc_anchor']); mutations.append(('missing anchor', bad))
    bad = copy.deepcopy(model); next(r for r in bad['records'] if r['implementation_status'] in ('planned','production_contract') and r['names_and_aliases'])['implementation_status']='current_contract'; mutations.append(('false implemented claim', bad))
    bad = copy.deepcopy(model); bad['records'][0]['sources']=[]; mutations.append(('missing source', bad))
    bad = copy.deepcopy(model); bad['rule_ids'].pop(); mutations.append(('omitted implemented rule', bad))
    bad = copy.deepcopy(model); next(r for r in bad['records'] if r['origin']=='candidate' and r['field_id'] is not None)['field_id']=999999; mutations.append(('wrong candidate field ID', bad))
    for name, bad in mutations:
        try: validate(bad, ids, catalog)
        except ValueError: pass
        else: raise ValueError('negative check did not reject: ' + name)
    print('PASS: 7 negative checks (omission, duplicate, anchor, false support, source, rule, field ID).')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-index', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--require-production-alignment', action='store_true')
    args = parser.parse_args()
    try:
        model, ids, catalog, result = load()
        if args.refresh_index:
            if INDEX.exists():
                previous = json.loads(INDEX.read_text())
                upstream_changed = any(previous.get(key) != result[key] for key in ('candidate_inventory_sha256', 'implementation_catalog_sha256'))
                require(not (upstream_changed and previous.get('document_sha256') == result['document_sha256']), 'source/catalog changed without a reviewed master document update; do not only refresh the index')
            INDEX.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        require(INDEX.exists() and json.loads(INDEX.read_text())==result, 'derived index is stale or altered; review master then --refresh-index')
        if args.self_test: self_test(model, ids, catalog)
        print(f'PASS: normative coverage: {len(ids)} candidates, {len(result["beyond_candidate_contracts"])} beyond-candidate contracts, {len(result["implemented_dcgm_fields"])} legacy core DCGM fields, {len(result["production_contract_dcgm_fields"])} declared production fields, {len(result["implemented_rule_ids"])} declared rules.')
        parity = result['production_alignment']
        if not parity['production_ready']:
            print(f'BLOCKED: production alignment: {len(parity["mandatory_implementation_gaps"])} mandatory implementation gaps, {len(parity["open_semantic_gates"])} open semantic gates. Document coverage passing is not release approval.')
            if args.require_production_alignment: return 2
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        print('FAIL: '+str(exc), file=sys.stderr); return 1

if __name__=='__main__':
    sys.exit(main())
