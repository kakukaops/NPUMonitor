"""One explicit, guarded migration of the owned query-failure suppression policy."""
import json
from pathlib import Path
from n9e import API
from comprehensive_control import health_rules
binding=json.loads(Path('/rules/comprehensive-runtime.json').read_text())
previous=json.loads(Path('/rules/comprehensive-health.json').read_text())
old=next(r for r in previous if r['key']=='platform_query_failure')
new=next(r for r in health_rules(binding['probe_rule_id'],list(binding['rule_ids'].values())) if r['key']==old['key'])
api=API();rid=binding['health_rule_ids'][old['key']]
row=api.call('GET',f'/alert-rule/{rid}/pure')
assert row['annotations']['managed_by']=='gpu-alert-lab'
assert row['rule_config']['queries'][0]['prom_ql'] in (old['expression'],new['expression'])
row['rule_config']['queries'][0]['prom_ql']=new['expression']
api.call('PUT',f'/busi-group/{binding["group_id"]}/alert-rule/{rid}',row)
print('PASS: only owned query-failure rule updated; component outage suppresses derivative query alerts')
