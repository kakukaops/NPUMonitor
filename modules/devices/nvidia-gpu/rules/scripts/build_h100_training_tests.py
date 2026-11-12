#!/usr/bin/env python3
"""Independent fixed samples for all comprehensive observation/quality expressions."""
import argparse
import json
from pathlib import Path
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lab'))
from comprehensive_model import SCALAR_FAULTS,COUNTER_FAULTS


def build():
    catalog=json.loads((ROOT/'rules/comprehensive-catalog.json').read_text())
    fields=catalog['fields'];entities=catalog['entities']
    def series(name,entity,extra=None):
        labels={'cluster_id':'h100-training-demo','job':'h100-comprehensive','instance':'comprehensive-source:9430',
                'entity_id':entity}
        labels.update(entities.get(entity,{}));labels.update(extra or {})
        return name+'{'+','.join(k+'='+json.dumps(str(v)) for k,v in sorted(labels.items()))+'}'
    def baseline():
        rows=[{'series':'up{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430"}','values':'1+0x30'}]
        for name,spec in fields.items():
            for entity in spec['entity_ids']:
                rows.append({'series':series(name,entity),'values':str(spec['normal'])+'+0x30'})
                if name.startswith('DCGM_'):
                    rows.append({'series':series('DEMO_EXPECTED_INPUT',entity,{'metric_name':name}),'values':'1+0x30'})
        rows.append({'series':series('DEMO_EXPECTED_LINK','GPU-DEMO-0000/1'),'values':'0+0x30'})
        rows.append({'series':series('DCGM_FI_DEV_NVLINK_GET_STATE','GPU-DEMO-0000/1'),'values':'0+0x30'})
        return rows
    def replace(rows,name,entity,values):
        key=series(name,entity)
        for row in rows:
            if row['series']==key:
                row['values']=values
                return
        raise ValueError(key)
    def assertion(rule,active=False,empty=False):
        if rule['kind']=='stateful':
            expression='max by (entity_id,metric_name) ('+rule['observation_expression']+')'
            samples=[] if empty else [{'labels':'{entity_id='+json.dumps(entity)+',metric_name='+json.dumps(rule['metric_name'])+'}',
                                       'value':1 if active and entity==rule['entity_ids'][0] else 0}
                                      for entity in rule['entity_ids']]
        else:
            expression='group by (entity_id) ('+rule['observation_expression']+')'
            samples=[]
            if active:
                labels='{}' if rule['rule_id']=='training.collector_down' else '{entity_id="GPU-DEMO-0000"}'
                samples=[{'labels':labels,'value':1}]
        return {'expr':expression,'eval_time':'40s','exp_samples':samples}
    cases=[]
    stateful=[r for r in catalog['rules'] if r['kind']=='stateful']
    cases.append({'name':'normal_valid_clear_evidence','interval':'2s','input_series':baseline(),
                  'promql_expr_test':[assertion(r) for r in catalog['rules']]})
    for rule in stateful:
        rows=baseline();scenario=rule['scenario'];entity=rule['entity_ids'][0]
        if scenario in SCALAR_FAULTS:
            name,value=SCALAR_FAULTS[scenario];replace(rows,name,entity,str(value)+'+0x30')
        elif scenario in COUNTER_FAULTS:
            name=COUNTER_FAULTS[scenario]
            scale=1000000000 if fields[name]['unit']=='nanoseconds' else 1
            replace(rows,name,entity,f'0+{scale}x30')
        else:raise ValueError('missing fixture '+scenario)
        cases.append({'name':scenario,'interval':'2s','input_series':rows,'promql_expr_test':[assertion(rule,True)]})
    rows=baseline();rows[0]['values']='0+0x30'
    cases.append({'name':'scrape_failure_never_supplies_clear','interval':'2s','input_series':rows,
                  'promql_expr_test':[assertion(r,empty=True) for r in stateful]})
    rows=[r for r in baseline() if not r['series'].startswith('DCGM_')]
    cases.append({'name':'missing_measurements_never_supply_clear','interval':'2s','input_series':rows,
                  'promql_expr_test':[assertion(r,empty=True) for r in stateful]})
    for rule in catalog['rules']:
        if rule['kind']!='direct':continue
        rows=baseline();key=rule['rule_id'].split('.',1)[1]
        field='DCGM_FI_DEV_SRAM_EXCEEDED';entity='GPU-DEMO-0000'
        if key=='field_missing':rows=[r for r in rows if r['series']!=series(field,entity)]
        elif key=='entity_missing':rows=[r for r in rows if not (r['series'].startswith('DCGM_') and 'entity_id="GPU-DEMO-0000"' in r['series'])]
        elif key=='input_stale':replace(rows,field,entity,'0 '+'_ '*30)
        elif key=='input_invalid':replace(rows,field,entity,'NaN+0x30')
        elif key=='input_duplicate':rows.append({'series':series(field,entity,{'replica':'other'}),'values':'1+0x30'})
        elif key=='collector_down':rows[0]['values']='0+0x30'
        cases.append({'name':key,'interval':'2s','input_series':rows,'promql_expr_test':[assertion(rule,True)]})
    codes=[r for r in stateful if '.xid_' in r['rule_id'] or '.sxid_' in r['rule_id']]
    rows=baseline()
    for entity in ['GPU-DEMO-0000','GPU-DEMO-0001','SWITCH-DEMO-0000']:
        replace(rows,'DEMO_RECOVERY_VERIFIED',entity,'0+0x30')
    cases.append({'name':'zero_code_without_recovery_record_holds','interval':'2s','input_series':rows,
                  'promql_expr_test':[assertion(r,empty=True) for r in codes]})
    return {'rule_files':[],'evaluation_interval':'2s','tests':cases}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    fixture=build();text=yaml.safe_dump(fixture,allow_unicode=True,sort_keys=False,width=120)
    path=ROOT/'monitoring/tests/h100-training.promtool.yaml'
    if args.check:
        if path.read_text()!=text:raise SystemExit('综合规则测试样本需更新')
    else:path.write_text(text)
    print(f'PASS: {len(fixture["tests"])}个综合规则用例 / '+str(sum(len(t['promql_expr_test']) for t in fixture['tests']))+'项断言')


if __name__=='__main__':main()
