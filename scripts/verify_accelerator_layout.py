#!/usr/bin/env python3
"""Read-only before/after migration checks. Never prints credentials or modifies services."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def get(url, headers=None):
    with urlopen(Request(url, headers=headers or {}), timeout=20) as response:
        return json.load(response)


def snapshot():
    state = get('http://localhost:19460/api/gpu-ml/v1/state', {
        'Authorization': 'Bearer ' + (ROOT/'.local/gpu-ml-admin-token').read_text().strip()})
    info = get('http://localhost:19461/v1/info', {
        'Authorization': 'Bearer ' + (ROOT/'.local/gpu-ml-model-platform-token').read_text().strip()})
    headers = {'X-User-Token': (ROOT/'.local/n9e-token').read_text().strip()}
    groups = get('http://localhost:17000/api/n9e/busi-groups', headers)
    groups = groups.get('dat', groups.get('data', [])) if isinstance(groups, dict) else groups
    rules = {}
    for group in groups:
        rows = get(f'http://localhost:17000/api/n9e/busi-group/{group["id"]}/alert-rules', headers)
        rows = rows.get('dat', rows.get('data', [])) if isinstance(rows, dict) else rows
        for row in rows:
            rules[str(row['id'])] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    ids = subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=gpu-alert-lab']).decode().split()
    ids += subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=gpu-monitoring-ml']).decode().split()
    containers = json.loads(subprocess.check_output(['docker','inspect',*ids]))
    volumes = {c['Name']: sorted([m['Destination'], m['Name']] for m in c['Mounts'] if m['Type']=='volume')
               for c in containers if 'oneoff' not in c['Name'] and c['Config']['Labels'].get('com.docker.compose.oneoff')!='True'}
    return {'task_ids': sorted(t['id'] for t in state['tasks']),
            'active_models': {t['id']:t.get('active_model') for t in state['tasks']},
            'model_refs': {m['id']:m.get('backend') for m in state['models']},
            'platform_id': info['platform_id'], 'nightingale_rules': rules, 'volumes': volumes}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['capture','verify']);parser.add_argument('file',type=Path);args=parser.parse_args()
    current=snapshot()
    if args.command=='capture':
        args.file.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
        print(f'Captured {len(current["task_ids"])} tasks, {len(current["model_refs"])} models, {len(current["nightingale_rules"])} rules; no credentials included')
    else:
        assert current==json.loads(args.file.read_text()), 'Persistent identity changed during migration'
        print('PASS: tasks, model references, platform identity, complete Nightingale rules and named volumes unchanged')


if __name__=='__main__':main()
