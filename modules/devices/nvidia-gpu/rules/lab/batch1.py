"""Import/inspect isolated batch1 simulation rules and select streaming fixtures."""
import json
from pathlib import Path
import sys
import n9e
from suite import request

n9e.GROUP = 'H100草案模拟验收'


def main():
    action = sys.argv[1] if len(sys.argv)>1 else 'state'
    if action == 'scenario':
        print(json.dumps(request('http://gpu-simulator:9400/batch1/scenario', {'name': sys.argv[2]})))
    elif action == 'state':
        print(json.dumps(request('http://gpu-simulator:9400/batch1/state')))
    elif action == 'import':
        n9e.install(n9e.API(), json.loads(Path('/rules/batch1-lab-catalog.json').read_text()))
    elif action == 'audit':
        import batch1_audit
    elif action == 'repair':
        import batch1_repair
    elif action == 'rules':
        api = n9e.API()
        bg = n9e.unique(api.call('GET','/busi-groups?all=true&limit=1000'), n9e.GROUP)
        rows = api.call('GET', f'/busi-group/{bg["id"]}/alert-rules')
        print(json.dumps([{'id': r['id'], 'name': r['name'], 'disabled': r['disabled'],
                           'interval': r['prom_eval_interval'], 'for':r['prom_for_duration']}
                          for r in rows], ensure_ascii=False, indent=2))
    else:
        raise ValueError('unknown batch1 action')


if __name__=='__main__':
    main()
