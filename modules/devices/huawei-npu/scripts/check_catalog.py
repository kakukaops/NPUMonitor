#!/usr/bin/env python3
"""Validate research contracts; does not certify PromQL or hardware support."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return yaml.safe_load((ROOT / path).read_text(encoding='utf-8'))

def main():
    sources = read('common/catalog/sources.yaml')['sources']
    metrics = read('common/catalog/metrics.yaml')['metrics']
    catalog = read('rules/candidates.yaml')
    rules = catalog['rules']
    errors = []
    def check(value, message):
        if not value:
            errors.append(message)
    source_ids = {s['id'] for s in sources}
    metric_ids = {m['id'] for m in metrics}
    check(len(source_ids) == len(sources), 'duplicate source id')
    check(len(metric_ids) == len(metrics), 'duplicate metric id')
    check(len({r['id'] for r in rules}) == len(rules), 'duplicate rule id')
    check(catalog['deployable'] is False, 'research rules must not be deployable')
    for metric in metrics:
        check(set(metric['sources']) <= source_ids, f"unknown source: {metric['id']}")
        check(metric['collection_verified'] is False, f"unexpected verified claim: {metric['id']}")
        for key in ('unit', 'validity', 'scope', 'a3_support', 'raw_type'):
            check(bool(metric.get(key)), f"missing {key}: {metric['id']}")
    for rule in rules:
        check(set(rule['inputs']) <= metric_ids, f"unknown input: {rule['id']}")
        check(set(rule['sources']) <= source_ids, f"unknown source: {rule['id']}")
        check(rule['enabled'] is False, f"research rule enabled: {rule['id']}")
        check(bool(rule['admission_gates']) and bool(rule['recovery']), f"missing gate/recovery: {rule['id']}")
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(sources)} sources, {len(metrics)} metrics, {len(rules)} disabled candidates; hardware/PromQL not tested')

if __name__ == '__main__':
    main()
