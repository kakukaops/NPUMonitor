#!/usr/bin/env python3
"""Derive a review index from the classified Markdown; no hardware certification."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'rules/docs/01-A3-NPU监控指标与告警规则说明表.md'
OUTPUT = DOC.with_suffix('.coverage.json')
COLUMNS = ['metric', 'trigger_and_recovery', 'meaning', 'alert_meaning', 'metric_source', 'rule_source']


def build():
    text = DOC.read_text(encoding='utf-8')
    declared_sources = set(re.findall(r'<a id="(source-[^"]+)"></a>', text))
    category = None
    path = None
    items = []
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.fullmatch(r'## ([1-9])\. (.+)', line)
        if heading:
            category = {'number': int(heading[1]), 'name': heading[2]}
            path = None
        heading = re.match(r'### ([EDX])：', line)
        if heading:
            path = heading[1]
        if 'metric_id：' not in line:
            continue
        cells = [value.strip() for value in line.strip().strip('|').split('|')]
        if len(cells) != 6 or category is None or path is None:
            raise ValueError(f'line {number}: invalid six-column classified row')
        match = re.search(r'metric_id：`(ascend\.[a-z0-9_]+)`', cells[0])
        if not match:
            raise ValueError(f'line {number}: missing stable metric id')
        metric_id = match[1]
        if metric_id in seen:
            raise ValueError(f'duplicate metric id: {metric_id}')
        seen.add(metric_id)
        if f'id="m-{metric_id}"' not in cells[0]:
            raise ValueError(f'missing anchor: {metric_id}')
        references = re.findall(r'\(#(source-[^)]+)\)', line)
        if not references or not set(references) <= declared_sources:
            raise ValueError(f'unknown/missing source: {metric_id}')
        if '候选，未启用' not in cells[1] or '恢复：' not in cells[1]:
            raise ValueError(f'missing lifecycle/recovery: {metric_id}')
        items.append({'metric_id': metric_id, 'category': dict(category), 'acquisition_path': path,
                      'line': number, **dict(zip(COLUMNS, cells))})
    if {item['category']['number'] for item in items} != set(range(1, 10)):
        raise ValueError('expected eight monitoring domains plus external inputs')
    if not items or {item['acquisition_path'] for item in items} != {'E', 'D', 'X'}:
        raise ValueError('missing acquisition paths')
    return {'schema_version': '0.2.0', 'lifecycle': 'research_draft',
            'source': str(DOC.relative_to(ROOT)),
            'source_sha256': hashlib.sha256(DOC.read_bytes()).hexdigest(),
            'count_unit': 'document_rows_not_individual_metrics',
            'counts': {key: sum(item['acquisition_path'] == key for item in items) for key in ('E', 'D', 'X')},
            'items': items}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    index = build()
    if args.check:
        if not OUTPUT.exists() or json.loads(OUTPUT.read_text(encoding='utf-8')) != index:
            raise SystemExit('FAIL: index missing/stale; run this script without --check')
    else:
        OUTPUT.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"PASS: {len(index['items'])} classified rows, paths={index['counts']}; no hardware or PromQL validation")


if __name__ == '__main__':
    main()
