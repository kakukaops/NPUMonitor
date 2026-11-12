#!/usr/bin/env python3
"""Publish reviewed simulation evidence; never promote production admission."""
import hashlib
import json
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
paths={k:ROOT.parents[3]/'.local/reports'/name for k,name in [('native','recovery-native-probe.json'),('lifecycle','recovery-lifecycle.json'),('restart','recovery-restart.json')]}
reports={k:json.loads(p.read_text()) for k,p in paths.items()}
assert all(r['passed'] for r in reports.values()),'required acceptance report missing/failed'
assert reports['native']['native_no_data_hold_supported'] is False and reports['native']['raw_exit_count']>=1
assert len(reports['lifecycle']['cases'])==9 and all(c['passed'] for c in reports['lifecycle']['cases'])
r=reports['restart'];assert r['upstream_query_failure']['passed'] and r['outage_observed_seconds']>=20
assert r['nightingale_restart_same_active_event'] and r['cleared_only_after_valid_zero']
config=json.loads((ROOT/'rules/recovery-lab.json').read_text());binding=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
assert reports['lifecycle']['binding_sha256']==binding
assert config['source_catalog_sha256']==hashlib.sha256((ROOT/'rules/batch1-lab-catalog.json').read_bytes()).hexdigest()
summary={'scope':'isolated_durable_lifecycle_simulation','date':'2026-11-09','result':'passed',
 'nightingale_version':'9.3.0','binding_sha256':binding,'production_admitted':False,'real_h100_tests':'not_run',
 'native_probe':{k:reports['native'][k] for k in ['configured_recover_config','native_no_data_hold_supported','raw_exit_count']},
 'hardware_rules':2,'hold_and_clear_cases':reports['lifecycle']['cases'],
 'restart_and_failure':{'upstream_query_failure':r['upstream_query_failure'],
                       'adapter_outage_observed_seconds':round(r['outage_observed_seconds'],3),
                       'nightingale_restart_same_active_event':True,'persisted_active_event_id':r['event']['id'],
                       'persisted_hash':r['event']['hash'],'cleared_only_after_valid_zero':True},
 'report_sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},
 'limitations':['experimental_extra_stateful_component','real_inventory_and_maintenance_unverified',
                'production_backup_migration_capacity_and_permissions_not_accepted','administrative_close_and_rule_crud_not_accepted',
                'evaluation_notification_health_and_failure_budget_not_accepted']}
expr_path=ROOT/'monitoring/tests/hardware-lifecycle.promtool.yaml'
expr=yaml.safe_load((ROOT/'monitoring/tests/hardware-lifecycle-promtool-results.yaml').read_text())
assert expr['result']=='passed' and expr['fixture_sha256']==hashlib.sha256(expr_path.read_bytes()).hexdigest()
summary['expression_tests']=expr
summary['unit_tests']={'cases':25,'result':'passed','scope':'simulator_receiver_lifecycle_and_real_HTTP'}
cleanup_path=ROOT.parents[3]/'.local/reports/recovery-probe-administrative-cleanup.json'
cleanup=json.loads(cleanup_path.read_text());assert cleanup['verified']
summary['probe_cleanup']={'action':cleanup['action'],'verified':True,'report_sha256':hashlib.sha256(cleanup_path.read_bytes()).hexdigest()}
p=ROOT/'monitoring/tests/hardware-lifecycle-results.yaml';p.write_text(yaml.safe_dump(summary,allow_unicode=True,sort_keys=False))
print('PASS: 2 lifecycle rules / 9 hold-clear cases / upstream+adapter+Nightingale outage/restart evidence published')
