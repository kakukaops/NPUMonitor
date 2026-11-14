#!/usr/bin/env python3
"""Read-only proof of the production compiler against the existing synthetic Prometheus.

Does not publish rules, modify source scenarios, or certify real hardware.
"""
import argparse,copy,json,sys,time
from pathlib import Path
MODULE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(MODULE/'runtime/src'))
from npumonitor_rules.bundle import compile_bundle
from npumonitor_rules.production_profile import definition
from npumonitor_rules.source import Source

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:19093');args=p.parse_args()
    d=definition();c=json.loads((MODULE/'runtime/config.production.example.json').read_text());c['upstream']['url']=args.url;c['source_contract'].update(confirmed=True,capabilities=list(d['metric_ids']),metadata={'metric':'sre_sim_gpu_info','labels':{}},stack={'gpu_model':'NVIDIA H100 SXM 80GB','driver_version':'595.synthetic','dcgm_version':'synthetic-master-v1','exporter_version':'master-sim1','nvml_version':'synthetic-R595','form_factor':'SXM','mig_enabled':False})
    c['profile']['collector_job_regex']='dcgm-os-sre';c['limits']={'query_timeout_seconds':10,'max_response_bytes':32*1024*1024}
    bundle=compile_bundle(c,MODULE);source=Source(bundle);report=source.preflight();assert report['production_contract']['ready'],report['production_contract']['mandatory_input_gaps']
    expected={r['rule_id'] for r in bundle['rules'] if r['rule_id'].startswith('os_sre.master_')};assert len(expected)==4
    evaluated=[]
    for rule in bundle['rules']:
        if rule['rule_id'] in expected or rule['rule_id'] in ('os_sre.inforom_invalid','os_sre.memory_unrepairable','os_sre.thermal_margin_exhausted','os_sre.ecc_change_pending'):
            source.query(rule['expression'],time.time());evaluated.append(rule['rule_id'])
    invalid=copy.deepcopy(c);invalid['source_contract']['units']['nvidia.board_power']='mW'
    try:compile_bundle(invalid,MODULE)
    except ValueError:unit_rejected=True
    else:raise AssertionError('wrong units admitted')
    invalid=copy.deepcopy(c);invalid['source_contract']['confirmed']=False
    assert not Source(compile_bundle(invalid,MODULE)).preflight()['production_contract']['ready']
    result={'passed':True,'scope':'production code against synthetic Prometheus, read-only; not physical hardware validation','authority':d['authority'],'numeric_fields':len(d['metric_ids']),'rule_definitions':len(bundle['rules']),'source_contract_ready':True,'queried_production_expressions':evaluated,'unit_mismatch_rejected':unit_rejected,'unconfirmed_source_rejected':True,'mandatory_coverage_gaps':report['production_contract']['mandatory_coverage_gaps'],'rule_sync_performed':False,'hardware_validation':'not_run','release_approval':False}
    out=MODULE/'runtime/evidence/production-contract-alignment.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
