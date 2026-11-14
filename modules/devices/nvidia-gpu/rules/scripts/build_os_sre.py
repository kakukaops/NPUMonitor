#!/usr/bin/env python3
"""Compile device/collector-only SRE expressions; legacy simulation stays archived."""
import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import re
import yaml
from os_sre_provenance import attach_provenance,render_provenance,source_table_for_card

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'monitoring/os-sre'
BANNED = {'cluster_id','clusterid','entity_id','task_id','job_id','tenant','tenant_id',
          'namespace','pod','workload','workload_id','training_job','DEMO_JOB_RUNNING'}
GPU = ('job','instance','UUID')
SWITCH = ('job','instance','switch_id')
GPU_LINK = GPU+('link_id',)
SWITCH_LINK = SWITCH+('link_id',)
TARGET = ('job','instance')


def reference():
    return json.loads((OUT/'definition-base.json').read_text())


def keys(names):return ','.join(names)
def quote(value):return json.dumps(str(value),ensure_ascii=False)
def max_by(expr,identity):return f'max by ({keys(identity)}) ({expr})'
def gate(expr,other,identity):return f'(({expr}) and on ({keys(identity)}) ({other}))'
def attach(expr,name,value):return f'label_replace(({expr}), {quote(name)}, {quote(value)}, "__name__", ".*")'


def compile_profile(profile,with_provenance=True,additional_required_fields=()):
    allowed={'schema_version','profile','collector_job_regex','nightingale_job_regex','lifecycle_job_regex',
             'freshness_seconds','counter_window_seconds','confirmation_seconds','gpus','switches','links','monitor_targets'}
    if set(profile)-allowed:raise ValueError('配置含未支持字段，不接受业务标签')
    if profile.get('schema_version')!=1 or profile.get('profile')!='os-sre':raise ValueError('规则profile无效')
    for name in ('collector_job_regex','nightingale_job_regex','lifecycle_job_regex'):
        value=profile[name]
        if not isinstance(value,str) or not value or len(value)>256:raise ValueError('采集job正则无效')
        re.compile(value)
    for name,low,high in [('freshness_seconds',1,3600),('counter_window_seconds',30,3600),('confirmation_seconds',0,3600)]:
        if type(profile[name]) is not int or not low<=profile[name]<=high:raise ValueError('时间参数无效')
    original=reference();fields={n:copy.deepcopy(v) for n,v in original['fields'].items() if n.startswith('DCGM_')}
    for name in ('DCGM_FI_PROF_PCIE_TX_BYTES','DCGM_FI_PROF_PCIE_RX_BYTES'):
        fields[name]={'kind':'gauge','minimum':0,'maximum':140737488355328,'unit':'bytes_per_second'}
    fields['os_sre_recovery_verified']={'kind':'boolean','minimum':0,'maximum':2,'unit':'boolean'}
    age=profile['freshness_seconds'];window=profile['counter_window_seconds'];inventory=[];seen=set()
    def const(name,item,identity,value=1,extra=None):
        labels={k:item[k] for k in identity};labels.update(extra or {})
        signature=(name,tuple(sorted(labels.items())))
        if signature in seen:raise ValueError('重复资产/端口/输入配置')
        seen.add(signature)
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('资产参数需要有限正数')
        expression=f'vector({value})'
        for k,v in labels.items():expression=attach(expression,k,v)
        inventory.append({'record':name,'expr':expression})
    def validate(item,identity,extras,job_regex):
        if not isinstance(item,dict) or set(item)-set(identity)-set(extras):raise ValueError('资产清单包含业务或未知属性')
        if any(not isinstance(item.get(k),str) or not item[k] for k in identity):raise ValueError('资产缺少稳定的采集/硬件身份')
        if not re.fullmatch(job_regex,item['job']):raise ValueError('资产job不在该采集器范围')
    for item in profile.get('gpus',[]):
        validate(item,GPU,('required_fields','pcie_gen','pcie_width','pcie_active_bytes_per_second','fabric_expected'),profile['collector_job_regex'])
        const('sre:inventory:gpu_expected',item,GPU)
        required=item.get('required_fields',[])
        if not isinstance(required,list) or any(n not in set(fields)|set(additional_required_fields) or not n.startswith('DCGM_') or 'NVSWITCH' in n or n=='DCGM_FI_DEV_NVLINK_GET_STATE' for n in required):raise ValueError('必需字段必须是已登记的DCGM字段')
        for name in required:const('sre:inventory:input_expected',item,GPU,extra={'metric_name':name})
        for key,suffix in [('pcie_gen','pcie_gen'),('pcie_width','pcie_width'),('pcie_active_bytes_per_second','pcie_active_bps')]:
            if key in item:const('sre:inventory:'+suffix,item,GPU,item[key])
        if 'fabric_expected' in item:
            if type(item['fabric_expected']) is not bool:raise ValueError('fabric_expected需要布尔值')
            if item['fabric_expected']:const('sre:inventory:fabric_expected',item,GPU)
    for item in profile.get('switches',[]):
        validate(item,SWITCH,(),profile['collector_job_regex']);const('sre:inventory:switch_expected',item,SWITCH)
    for item in profile.get('links',[]):
        identity=GPU_LINK if 'UUID' in item else SWITCH_LINK
        validate(item,identity,(),profile['collector_job_regex'])
        const('sre:inventory:'+('gpu_link_expected' if identity==GPU_LINK else 'switch_link_expected'),item,identity)
    for item in profile.get('monitor_targets',[]):
        validate(item,TARGET,('evaluation_expected',),profile['nightingale_job_regex'])
        const('sre:inventory:monitor_expected',item,TARGET)
        if 'evaluation_expected' in item and type(item['evaluation_expected']) is not bool:raise ValueError('evaluation_expected需要布尔值')
        if item.get('evaluation_expected'):const('sre:inventory:evaluation_expected',item,TARGET)
    def identity(name):
        if 'NVSWITCH_LINK_' in name:return SWITCH_LINK
        if 'NVSWITCH_' in name:return SWITCH
        if name=='DCGM_FI_DEV_NVLINK_GET_STATE':return GPU_LINK
        return GPU
    def raw(name,identity_override=None):
        dims=identity_override or identity(name)
        labels=[f'job=~{quote(profile["collector_job_regex"])}']
        labels += [f'{k}!=""' for k in dims if k not in TARGET]
        if 'UUID' in dims:labels+=['GPU_I_ID=""','GPU_I_PROFILE=""']
        return name+'{'+','.join(labels)+'}'
    def up(job_regex=None):
        value='up{job=~'+quote(job_regex or profile['collector_job_regex'])+'}'
        return max_by(f'({value} == 1) and ((time()-timestamp({value})) >= 0) and ((time()-timestamp({value})) <= {age})',TARGET)
    def valid(name,identity_override=None):
        dims=identity_override or identity(name);value=raw(name,dims);f=fields[name]
        expr=f'({value} >= {f["minimum"]}) and ({value} < {f["maximum"]}) and (({value}-{value}) == 0)'
        expr+=f' and ((time()-timestamp({value})) >= 0) and ((time()-timestamp({value})) <= {age})'
        if f['kind']!='gauge':expr+=f' and ({value} == floor({value}))'
        expr=gate(expr,f'count by ({keys(dims)}) ({value}) == 1',dims)
        return gate(max_by(expr,dims),up(),TARGET)
    def recent(name):
        value=raw(name);dims=identity(name);rng=value+f'[{window}s]'
        good=f'(increase({rng})) and (min_over_time({rng}) >= 0) and (max_over_time({rng}) < {fields[name]["maximum"]}) and (sum_over_time({rng}) >= 0) and (count_over_time({rng}) >= 2)'
        return gate(max_by(good,dims),valid(name),dims)
    def boolean(expr):return f'(({expr}) > bool 0)'
    def split(value,trigger,clear):return f'((({value}) * 0 + 1) and ({value} {trigger})) or ((({value}) * 0) and ({value} {clear}))'
    rules=[]
    def add(old,expr,inputs=None,identity_override=None,requirements=None,note=None,status='candidate'):
        dims=identity_override or identity(next((n for n in old['input_fields'] if n.startswith('DCGM_')),'DCGM_FI_DEV_GPU_TEMP'))
        item={'rule_id':old['rule_id'].replace('training.','os_sre.'),'previous_rule_id':old['rule_id'],
              'title':old['title'],'version':'0.2.0','kind':old['kind'],'default_policy':'disabled',
              'identity_labels':list(dims),'input_fields':inputs or [n for n in old['input_fields'] if n.startswith('DCGM_')],
              'expression':expr,'for_seconds':profile['confirmation_seconds'] if old['desired_for_seconds'] else 0,
              'severity':old['severity'],'requirements':requirements or [],'status':status,
              'note':note or old['reason'],'source_ids':old['source_ids'],'real_hardware_tests':'not_run'}
        if old['kind']=='stateful':item['execution']='persistent_boolean_observation; not a native alert expression'
        rules.append(item);return item
    by_key={r['rule_id'].split('.',1)[1]:r for r in original['rules']}
    for key in ('sram','remap_failed','remap_pending'):
        old=by_key[key];add(old,valid(old['input_fields'][0]))
    for key in ('gpu_thermal','memory_thermal','switch_thermal'):
        old=by_key[key];temp,limit=old['input_fields'];dims=identity(temp)
        margin=f'({valid(limit)} - on ({keys(dims)}) {valid(temp)})'
        add(old,split(margin,'<= 0','> 5'),note='使用设备门槛；5°C回差为工程参数。缺少任一有效输入不提供恢复证据。')
    for key,mask in [('sw_thermal',32),('hw_thermal',64),('power_cap',4),('power_brake',128),('hw_slowdown',8),('sync_boost',16)]:
        obs=f'(floor({valid("DCGM_FI_DEV_CLOCKS_EVENT_REASONS")} / {mask}) % 2)'
        item=add(by_key[key],obs,note='仅表示设备原因位；不使用作业上下文，不推断吞吐或性能故障。')
        if key=='power_cap':item['title']='设备功率限制状态（信息）';item['severity']=3
    add(by_key['clock_unknown'],f'({valid("DCGM_FI_DEV_CLOCKS_EVENT_REASONS")} >= bool 512)')
    for key in ('ecc_new','thermal_time','pcie_replay','nvlink_crc','nvlink_recovery','nvlink_replay','switch_replay','switch_recovery'):
        old=by_key[key];add(old,boolean(recent(old['input_fields'][0])),note='仅表示窗口内新增活动；窗口退出不是硬件修复。')
    xid_catalog=yaml.safe_load((ROOT/'monitoring/catalog/xid-review.yaml').read_text())['items']
    xid=valid('DCGM_FI_DEV_XID_ERRORS');known='('+' or '.join(f'({xid} == {r["code"]})' for r in xid_catalog)+')'
    for key,disposition in [('xid_node','node_incident_review'),('xid_reset','gpu_reset_review'),('xid_app','training_job_review'),('xid_scope','deployment_scope_review'),('xid_unknown',None)]:
        bad=f'(({xid} > 0) unless ({known}))' if disposition is None else '('+' or '.join(f'({xid} == {r["code"]})' for r in xid_catalog if r['disposition']==disposition)+')'
        obs=f'(({bad}) * 0 + 1) or ((({xid} == 0) * 0) and on ({keys(GPU)}) ({valid("os_sre_recovery_verified")} == 1))'
        item=add(by_key[key],obs,inputs=['DCGM_FI_DEV_XID_ERRORS','os_sre_recovery_verified'],requirements=['恢复确认由OS运维流程提供；缺少时只能触发并保持，不能自动解除'],note='按XID码分流，不需要作业ID、进程名或业务归属；其他码及缺数不解除已确认事件。')
        if key=='xid_app':item['title']='XID进程/软件排查线索（OS侧）'
    for key in ('sxid_fatal','sxid_nonfatal'):
        old=by_key[key];name=old['input_fields'][0];code=valid(name)
        # Recovery evidence is per hardware identity, with switch_id for NVSwitch.
        recovery=valid('os_sre_recovery_verified',SWITCH)
        obs=f'(({code} > 0) * 0 + 1) or ((({code} == 0) * 0) and on ({keys(SWITCH)}) ({recovery} == 1))'
        add(old,obs,inputs=[name,'os_sre_recovery_verified'],requirements=['NVSwitch真实switch_id及运维恢复确认'],note='最近错误码不是有序事件流；无恢复证据时事件保持。')
    for key,expected,bad,clear in [('gpu_link_down','gpu_link_expected','== 0','> 0'),('switch_link_down','switch_link_expected','!= 2','== 2')]:
        old=by_key[key];name=old['input_fields'][0];dims=identity(name)
        add(old,gate(split(valid(name),bad,clear),f'sre:inventory:{expected} == 1',dims),requirements=['OS维护的预期启用端口清单；无清单则不判断掉链'])
    gen=f'({valid("DCGM_FI_DEV_PCIE_LINK_GEN")} < bool on ({keys(GPU)}) sre:inventory:pcie_gen)'
    width=f'({valid("DCGM_FI_DEV_PCIE_LINK_WIDTH")} < bool on ({keys(GPU)}) sre:inventory:pcie_width)'
    traffic=f'({valid("DCGM_FI_PROF_PCIE_TX_BYTES")} + on ({keys(GPU)}) {valid("DCGM_FI_PROF_PCIE_RX_BYTES")})'
    busy=f'({traffic} > on ({keys(GPU)}) sre:inventory:pcie_active_bps)'
    degraded=gate(f'(({gen} + on ({keys(GPU)}) {width}) > bool 0)',busy,GPU)
    item=add(by_key['pcie_degraded'],degraded,inputs=['DCGM_FI_DEV_PCIE_LINK_GEN','DCGM_FI_DEV_PCIE_LINK_WIDTH','DCGM_FI_PROF_PCIE_TX_BYTES','DCGM_FI_PROF_PCIE_RX_BYTES'],requirements=['每卡OS资产预期gen/width及实测活动字节速率门槛','Profiling PCIe TX/RX字段已确认是bytes/s的gauge'],note='只在可测PCIe传输期间判断；空闲/传输字段缺失不给故障或恢复结论。不把GPU利用率当PCIe负载，不对已有速率再次rate。')
    item['title']='持续PCIe传输时链路低于资产预期';item['for_seconds']=max(120,profile['confirmation_seconds'])
    fm=valid('DCGM_FI_DEV_FABRIC_MANAGER_STATUS');fabric=valid('DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY')
    conditions={'fabric_manager':f'((({fm} == 1) or ({fm} == 2) or ({fm} == 4)) * 0 + 1) or (({fm} == 3) * 0)',
                'fabric_capability':f'((({fm} == bool 0)+({fm} == bool 5)+({fm} == bool 6)) > bool 0)',
                'fabric_health':split(fabric,'>= 2','== 1')}
    for key,expr in conditions.items():add(by_key[key],gate(expr,'sre:inventory:fabric_expected == 1',GPU),requirements=['OS资产声明该设备需要fabric；不由训练作业判断'])
    # Data quality uses the same physical/port keys and never silently chooses a duplicate.
    measurements=[];stale=[];invalid=[];duplicates=[];missing_ids=[]
    for name,f in fields.items():
        if not name.startswith('DCGM_'):continue
        v=raw(name);dims=identity(name)
        measurements.append(attach(max_by(v,dims),'metric_name',name))
        stale.append(attach(max_by(f'((time()-timestamp({v})) > {age}) or ((time()-timestamp({v})) < 0)',dims),'metric_name',name))
        bad=f'(({v} != bool {v}) + ({v} >= bool {f["maximum"]}) + ({v} < bool {f["minimum"]}))'
        if f['kind']!='gauge':bad+=f' + ({v} != bool floor({v}))'
        invalid.append(attach(max_by(f'(({bad}) > 0)',dims),'metric_name',name))
        duplicates.append(attach(f'count by ({keys(dims)}) ({v}) > 1','metric_name',name))
        # Any missing component is a gap, including absent per-port identity.
        for ident in dims:
            if ident in TARGET:continue
            missing=name+'{job=~'+quote(profile['collector_job_regex'])+','+ident+'=""'+(',GPU_I_ID="",GPU_I_PROFILE=""' if 'UUID' in dims else '')+'}'
            missing_ids.append(attach(f'count by ({keys(TARGET)}) ({missing}) > 0','metric_name',name))
    samples='('+' or '.join(measurements)+')'
    expected_gpu='sre:inventory:gpu_expected'
    expected_switch='sre:inventory:switch_expected'
    missing_gpu=f'({expected_gpu} unless on ({keys(GPU)}) (count by ({keys(GPU)}) ({samples})))'
    missing_switch=f'({expected_switch} unless on ({keys(SWITCH)}) (count by ({keys(SWITCH)}) ({samples})))'
    add(by_key['entity_missing'],gate(f'{missing_gpu} or {missing_switch}',up(),TARGET),identity_override=TARGET,requirements=['OS预期设备清单；历史观测不能证明永远应有该设备'])
    missing_field=f'((sre:inventory:input_expected unless on ({keys(GPU)},metric_name) {samples}) and on ({keys(GPU)}) (count by ({keys(GPU)}) ({samples})))'
    add(by_key['field_missing'],gate(missing_field,up(),TARGET),identity_override=GPU+('metric_name',),requirements=['OS逐卡必需字段清单；整卡消失时抑制逐字段告警'])
    for key,expr in [('input_stale',stale),('input_invalid',invalid),('input_duplicate',duplicates)]:
        add(by_key[key],gate(' or '.join(expr),up(),TARGET),identity_override=TARGET+('metric_name',))
    down=max_by('up{job=~'+quote(profile['collector_job_regex'])+'} == 0',TARGET)
    expected_targets=max_by(f'{expected_gpu} or {expected_switch}',TARGET)
    missing_target=f'({expected_targets} unless on ({keys(TARGET)}) up{{job=~{quote(profile["collector_job_regex"])}}})'
    add(by_key['collector_down'],f'({down}) or ({missing_target})',identity_override=TARGET,note='up=0表示采集失败；配置资产清单后还可检测target被移除，不代表GPU故障。')['title']='DCGM采集目标不可用'
    extra=copy.deepcopy(by_key['input_invalid']);extra['rule_id']='training.identity_missing';extra['title']='硬件身份标签缺失'
    add(extra,gate(' or '.join(missing_ids),up(),TARGET),identity_override=TARGET+('metric_name',),note='UUID/switch_id/link_id缺失时明确报采集契约缺口，不按序号伪造设备身份。')
    health=original['platform_rules']
    nj=quote(profile['nightingale_job_regex']);lj=quote(profile['lifecycle_job_regex'])
    q=f'sum by ({keys(TARGET)}) (increase(n9e_alert_query_data_error_total{{job=~{nj}}}[{window}s])) > 0'
    activity=f'sum by ({keys(TARGET)}) (increase(n9e_alert_rule_eval_total{{job=~{nj}}}[{window}s])) == 0'
    expected=gate('sre:inventory:evaluation_expected == 1',f'min by ({keys(TARGET)}) (count_over_time(n9e_alert_rule_eval_total{{job=~{nj}}}[{window}s])) >= 2',TARGET)
    health_expr={'platform_query_failure':gate(q,up(profile['nightingale_job_regex']),TARGET),
                 'platform_evaluation_stall':gate(gate(activity,expected,TARGET),up(profile['nightingale_job_regex']),TARGET),
                 'platform_notify_failure':None,
                 'platform_adapter_down':max_by(f'up{{job=~{lj}}} == 0',TARGET),
                 'platform_nightingale_metrics_missing':f'({max_by(f"up{{job=~{nj}}} == 0",TARGET)}) or (sre:inventory:monitor_expected unless on ({keys(TARGET)}) up{{job=~{nj}}})'}
    for old in health:
        expr=health_expr[old['key']]
        note='组件级聚合，不绑定任何业务任务或夜莺数据库规则ID。'
        status='candidate'
        if expr is None:status='blocked_missing_input';note='v9.3.0源码定义了通知错误counter，但现场采集、调用范围及真实失败增量尚未核对；保持输入接入阻塞，不把DEMO计数或队列长度冒充投递结果。'
        rules.append({'rule_id':'os_sre.'+old['key'],'previous_rule_id':old['key'],'title':old['name'].replace('H100平台-','平台-'),
                      'version':'0.2.0','kind':'direct','default_policy':'disabled','expression':expr,
                      'identity_labels':list(TARGET),'input_fields':[],'requirements':[], 'for_seconds':profile['confirmation_seconds'],
                      'severity':old['severity'],'status':status,'note':note,'source_ids':['project.scope'],'real_hardware_tests':'not_run'})
    views=[]
    previous=original['views']
    bit_views={'clock.sw_thermal':32,'clock.hw_thermal':64,'clock.sw_power_cap':4,
               'clock.hw_power_brake':128,'clock.hw_slowdown':8,'clock.sync_boost':16}
    for old in previous:
        ident=old['query_id'];name=old.get('input') or old['inputs'][0]
        if ident=='thermal.gpu_operating_margin':expression=f'({valid("DCGM_FI_DEV_GPU_MAX_OP_TEMP")} - on ({keys(GPU)}) {valid("DCGM_FI_DEV_GPU_TEMP")})'
        elif ident=='thermal.memory_operating_margin':expression=f'({valid("DCGM_FI_DEV_MEM_MAX_OP_TEMP")} - on ({keys(GPU)}) {valid("DCGM_FI_DEV_MEMORY_TEMP")})'
        elif ident in bit_views:expression=f'(floor({valid("DCGM_FI_DEV_CLOCKS_EVENT_REASONS")} / {bit_views[ident]}) % 2)'
        elif ident=='clock.unknown_bits':expression=f'({valid("DCGM_FI_DEV_CLOCKS_EVENT_REASONS")} >= bool 512)'
        elif ident=='thermal.slowdown_seconds':expression=f'({recent("DCGM_FI_DEV_THERMAL_VIOLATION")} / 1000000000)'
        elif ident.startswith('xid.'):
            group=ident.split('.',1)[1]
            expression='('+' or '.join(f'({xid} == {r["code"]})' for r in xid_catalog if r['disposition']==group)+')'
        elif ident.startswith(('ecc.sbe_trend','pcie.replay','nvlink.')):expression=recent(name)
        else:expression=valid(name)
        views.append({'query_id':ident,'expression':expression,'default_policy':'readonly_diagnostic',
                      'note':'仅诊断数据；不推断作业影响或硬件修复。'})
    for view in views:
        if any(re.search(r'\b'+re.escape(n)+r'\b',view['expression']) for n in BANNED):raise ValueError('诊断视图含业务属性')
    for item in rules:
        for name in BANNED:
            if item['expression'] and re.search(r'\b'+re.escape(name)+r'\b',item['expression']):raise ValueError('PromQL出现业务属性 '+name)
        if item['expression'] and 'DEMO_' in item['expression']:raise ValueError('PromQL仍依赖模拟字段')
    catalog = {'schema_version':1,'profile':'os-sre','version':'0.2.0','production_default':'disabled',
            'identity':'collector job/instance + physical UUID or switch_id/link_id; no business identity',
            'rules':rules,'views':views,'inventory_records':inventory,'metric_contracts':{name:{**{k:f[k] for k in ('kind','minimum','maximum','unit')},'identity_labels':list(identity(name)),'alternative_identity_labels':([list(GPU),list(SWITCH)] if name=='os_sre_recovery_verified' else [list(identity(name))]),'business_labels_required':False} for name,f in fields.items()},'real_hardware_tests':'not_run'}
    if with_provenance:attach_provenance(catalog,profile)
    return catalog


def outputs(catalog):
    rules=catalog['rules'];observations=[{'record':'sre:hardware:observation','expr':r['expression'],
        'labels':{'sre_rule_id':r['rule_id']}} for r in rules if r['kind']=='stateful']
    direct=[{'alert':r['rule_id'].replace('.','_'),'expr':r['expression'],'for':str(r['for_seconds'])+'s',
        'labels':{'severity':str(r['severity']),'monitoring_profile':'os-sre'},'annotations':{'summary':r['title']}}
        for r in rules if r['kind']=='direct' and r['expression']]
    groups=[]
    if catalog['inventory_records']:groups.append({'name':'os-sre-static-inventory','interval':'30s','rules':catalog['inventory_records']})
    groups.append({'name':'os-sre-stateful-observations','interval':'30s','rules':observations})
    # State observations must feed a persistent lifecycle adapter, never a native truthiness alert.
    content={'provenance.md':render_provenance(catalog),'catalog.json':json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',
             'views.yaml':yaml.safe_dump({'profile':'os-sre','views':catalog['views']},allow_unicode=True,sort_keys=False),
             'metrics.yaml':yaml.safe_dump({'profile':'os-sre','metrics':catalog['metric_contracts']},allow_unicode=True,sort_keys=False),
             'observations.prom.yaml':yaml.safe_dump({'groups':groups},allow_unicode=True,sort_keys=False),
             'native-alerts.prom.yaml':yaml.safe_dump({'groups':[{'name':'os-sre-quality-platform','interval':'30s','rules':direct}]},allow_unicode=True,sort_keys=False)}
    content['cards/README.md']='\n'.join(['# OS SRE规则卡','','| 规则 | 类型 | 状态 |','|---|---|---|']+[f'| [{r["title"]}]({r["rule_id"]}.md) | {r["kind"]} | {r["status"]} |' for r in rules])+'\n'
    for item in rules:
        lines=['# '+item['title'],'',f'规则 `{item["rule_id"]}`，版本0.2.0；默认disabled；状态 `{item["status"]}`。',
               '', '## 身份与输入','', '匹配标签：`'+','.join(item['identity_labels'])+'`。不依赖集群ID、业务任务、租户或作业状态。',
               '输入：'+('、'.join('`'+n+'`' for n in item['input_fields']) or '采集目标/监控组件指标或OS资产清单')+'。',
               '', '## 语义与边界','',item['note'],
               '持续确认：'+str(item['for_seconds'])+'秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。']
        if item['requirements']:lines+=['']+['- '+n for n in item['requirements']]
        if item['expression']:lines+=['','## PromQL','','```promql',item['expression'],'```']
        if item['kind']=='stateful':lines+=['','输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。']
        lines+=source_table_for_card(item,catalog['provenance_sources'])
        content['cards/'+item['rule_id']+'.md']='\n'.join(lines)+'\n'
    return content


def main():
    p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,default=OUT/'profile.yaml');p.add_argument('--output',type=Path,default=OUT);p.add_argument('--check',action='store_true');args=p.parse_args()
    result=compile_profile(yaml.safe_load(args.profile.read_text()))
    for name,text in outputs(result).items():
        path=args.output/name
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('OS SRE生成物需更新：'+str(path))
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print(f'PASS: {len(result["rules"])} OS SRE rules; no business labels; {len(result["inventory_records"])} optional inventory records')


if __name__=='__main__':main()
