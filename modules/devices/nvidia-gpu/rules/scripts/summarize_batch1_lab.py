#!/usr/bin/env python3
"""Publish a bounded acceptance summary after successful streaming tests."""
import hashlib
import json
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
report_path=ROOT.parents[3]/'.local/reports/batch1-all.json'
report=json.loads(report_path.read_text())
assert report['passed'] and not report.get('cleanup_error'), 'streaming suite has not passed'
assert report.get('postflight_audit',{}).get('passed'), 'native timestamps / exit contract not audited'
assert len(report['cases'])==11 and all(c['passed'] for c in report['cases'])
catalog_path=ROOT/'rules/batch1-lab-catalog.json'
catalog=json.loads(catalog_path.read_text())
assert report['catalog_version']==catalog['catalog_version']
assert report['catalog_source_sha256']==catalog['source_sha256']
assert report['catalog_source_sha256']==hashlib.sha256((ROOT/'monitoring/catalog/rules.yaml').read_bytes()).hexdigest()
summary={'scope':'nightingale_streaming_simulation_only','date':'2026-11-09',
 'catalog_version':catalog['catalog_version'],'catalog_sha256':hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
 'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
 'started_at':report['started_at'],'finished_at':report['finished_at'],
 'rules':8,'cases':11,'result':'passed','real_h100_tests':'not_run',
 'production_admitted':False,'desired_quality_for_seconds':60,'native_quality_for_seconds':90,
 'eval_interval_seconds':30,'cases_detail':[],
 'native_trigger_timings':report['postflight_audit']['native_trigger_timings'],
 'input_loss_exit_notification':report['postflight_audit']['hardware_input_loss_exit_notification'],
 'production_blockers':['native_recovered_does_not_mean_hardware_repaired','verified_inventory_and_maintenance_binding',
                       'real_h100_field_software_and_entity_admission','evaluation_and_notification_self_health']}
for case in report['cases']:
 item={k:case[k] for k in ['scenario','passed','firing_after_seconds','exit_after_seconds','observed_seconds','interpretation'] if k in case}
 summary['cases_detail'].append(item)
path=ROOT/'monitoring/tests/h100_batch1-streaming-results.yaml'
path.write_text(yaml.safe_dump(summary,allow_unicode=True,sort_keys=False))
print('PASS: 11 streaming cases / 8 Nightingale simulation rules; published '+str(path.relative_to(ROOT)))
