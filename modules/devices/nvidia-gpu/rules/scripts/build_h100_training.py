#!/usr/bin/env python3
"""Build H100 candidate rules, documented simulation parameters and demo bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = 'h100-training-demo'
JOB = 'h100-comprehensive'
TARGET = f'cluster_id="{CLUSTER}",job="{JOB}"'
GPUS = ['GPU-DEMO-0000', 'GPU-DEMO-0001']
SWITCH = 'SWITCH-DEMO-0000'
GPU_LINKS = [gpu + '/0' for gpu in GPUS]
SWITCH_LINKS = [SWITCH + '/0']
NODE = 'demo-monitor'
ENTITIES = {gpu: {'UUID': gpu, 'entity_type': 'gpu'} for gpu in GPUS}
for gpu in GPUS:
    ENTITIES[gpu + '/0'] = {'UUID': gpu, 'link_id': '0', 'entity_type': 'gpu_link'}
ENTITIES[SWITCH] = {'switch_id': SWITCH, 'entity_type': 'nvswitch'}
ENTITIES[SWITCH + '/0'] = {'switch_id': SWITCH, 'link_id': '0', 'entity_type': 'switch_link'}
ENTITIES[NODE] = {'ident': NODE, 'entity_type': 'monitor'}

# Raw field IDs and old Exporter aliases are explicit. Project fields carry no DCGM ID.
FIELDS = {}


def field(name, field_id, kind, unit, entities, normal, minimum=0, maximum=9223372036854775792):
    FIELDS[name] = {'dcgm_field_id': field_id, 'kind': kind, 'unit': unit,
                    'entity_ids': entities, 'normal': normal, 'minimum': minimum, 'maximum': maximum}


field('DCGM_FI_DEV_GPU_TEMP', 150, 'gauge', 'celsius', GPUS, 55, -140737488355328, 140737488355328)
field('DCGM_FI_DEV_GPU_MAX_OP_TEMP', 152, 'gauge', 'celsius', GPUS, 95, 1, 140737488355328)
field('DCGM_FI_DEV_MEMORY_TEMP', 140, 'gauge', 'celsius', GPUS, 60, -140737488355328, 140737488355328)
field('DCGM_FI_DEV_MEM_MAX_OP_TEMP', 151, 'gauge', 'celsius', GPUS, 110, 1, 140737488355328)
field('DCGM_FI_DEV_CLOCKS_EVENT_REASONS', 112, 'integer', 'bitmask', GPUS, 0, 0, 9007199254740992)
for name, fid in [('SRAM_EXCEEDED', 346), ('ROW_REMAP_FAILURE', 395), ('ROW_REMAP_PENDING', 396)]:
    field('DCGM_FI_DEV_' + name, fid, 'boolean', 'boolean', GPUS, 0, 0, 2)
for name, fid, unit in [
    ('ECC_DBE_VOL_TOTAL', 311, 'errors'), ('ECC_DBE_VOL_DEV', 319, 'errors'),
    ('ECC_DBE_VOL_SRM', 343, 'errors'), ('ECC_SBE_VOL_TOTAL', 310, 'errors'),
    ('ECC_SBE_VOL_DEV', 318, 'errors'), ('ECC_SBE_VOL_SRM', 342, 'errors'),
    ('ECC_DBE_AGG_TOTAL', 313, 'errors'), ('ECC_DBE_AGG_DEV', 329, 'errors'),
    ('ECC_DBE_AGG_SRM', 345, 'errors'), ('THERMAL_VIOLATION', 241, 'nanoseconds'),
    ('PCIE_REPLAY_COUNTER', 202, 'events'), ('NVLINK_CRC_ERROR_TOTAL', 497, 'errors'),
    ('NVLINK_RECOVERY_TOTAL', 498, 'events'), ('NVLINK_REPLAY_TOTAL', 499, 'events')]:
    field('DCGM_FI_DEV_' + name, fid, 'counter', unit, GPUS, 0)
field('DCGM_FI_DEV_XID_ERRORS', 230, 'integer', 'code', GPUS, 0)
field('DCGM_FI_DEV_PCIE_LINK_GEN', 237, 'integer', 'generation', GPUS, 5, 1, 7)
field('DCGM_FI_DEV_PCIE_LINK_WIDTH', 238, 'integer', 'lanes', GPUS, 16, 1, 33)
field('DCGM_FI_DEV_NVLINK_GET_STATE', 1508, 'integer', 'enum', GPU_LINKS, 1, 0, 3)
field('DCGM_FI_DEV_FABRIC_MANAGER_STATUS', 170, 'integer', 'enum', GPUS, 3, 0, 7)
field('DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY', 175, 'integer', 'enum', GPUS, 1, 0, 4)
field('DCGM_FI_DEV_NVSWITCH_FATAL_ERRORS', 856, 'integer', 'sxid_code', [SWITCH], 0)
field('DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS', 857, 'integer', 'sxid_code', [SWITCH], 0)
field('DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT', 858, 'gauge', 'celsius', [SWITCH], 50, -140737488355328, 140737488355328)
field('DCGM_FI_DEV_NVSWITCH_TEMPERATURE_LIMIT_SLOWDOWN', 859, 'gauge', 'celsius', [SWITCH], 95, 1, 140737488355328)
field('DCGM_FI_DEV_NVSWITCH_LINK_STATUS', 870, 'integer', 'enum', SWITCH_LINKS, 2, 0, 4)
field('DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERROR_TOTAL', 784, 'counter', 'events', SWITCH_LINKS, 0)
field('DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERROR_TOTAL', 785, 'counter', 'events', SWITCH_LINKS, 0)
field('DEMO_EXPECTED_LINK', None, 'boolean', 'boolean', GPU_LINKS + SWITCH_LINKS, 1, 0, 2)
field('DEMO_EXPECTED_PCIE_GEN', None, 'integer', 'generation', GPUS, 5, 1, 7)
field('DEMO_EXPECTED_PCIE_WIDTH', None, 'integer', 'lanes', GPUS, 16, 1, 33)
field('DEMO_JOB_RUNNING', None, 'boolean', 'boolean', GPUS, 1, 0, 2)
field('DEMO_RECOVERY_VERIFIED', None, 'boolean', 'boolean', GPUS + [SWITCH], 1, 0, 2)
field('DEMO_EXPECTED_FABRIC', None, 'boolean', 'boolean', GPUS, 1, 0, 2)
field('DEMO_MAINTENANCE', None, 'boolean', 'boolean', list(ENTITIES), 0, 0, 2)


def raw(name):
    return f'{name}{{{TARGET}}}'


def healthy():
    target = f'up{{{TARGET}}}'
    age = f'(time() - timestamp({target}))'
    return f'(({target} == 1) and ({age} >= 0) and ({age} <= 15))'


def valid(name):
    spec = FIELDS[name]
    value = raw(name)
    age = f'(time() - timestamp({value}))'
    expression = (f'({value} and ({age} >= 0) and ({age} <= 15)'
                  f' and ({value} >= {spec["minimum"]}) and ({value} < {spec["maximum"]})'
                  f' and (({value} - {value}) == 0)'
                  f' and on (entity_id) (count by (entity_id) ({value}) == 1)'
                  f' and on (job,instance) {healthy()})')
    if spec['kind'] != 'gauge':
        expression = f'({expression} and ({value} == floor({value})))'
    return expression


def bit(number):
    return f'(floor({valid("DCGM_FI_DEV_CLOCKS_EVENT_REASONS")} / {number}) % 2)'


def recent(name):
    value = raw(name)
    window = value + '[30s]'
    return (f'(increase({window}) and {valid(name)} and (count_over_time({window}) >= 2)'
            f' and (min_over_time({window}) >= 0) and (max_over_time({window}) < 9223372036854775792)'
            f' and (sum_over_time({window}) >= 0))')


def normalized(expression, metric_name):
    return f'label_replace(({expression}), "metric_name", "{metric_name}", "__name__", ".*")'


def split_hysteresis(value, trigger, clear):
    return f'((({value} * 0) + 1) and ({value} {trigger})) or (({value} * 0) and ({value} {clear}))'


def build():
    entries = []

    def rule(key, title, observation, inputs, entities, severity=2, hold=10, scenario=None,
             trigger='', clear='', reason='', source='nvidia.dcgm.fixed_fields', kind='stateful'):
        rule_id = 'training.' + key
        entries.append({'rule_id': rule_id, 'title': title, 'kind': kind, 'version': '0.1.0',
                        'lifecycle': 'candidate', 'production_default': 'disabled',
                        'input_fields': inputs, 'entity_ids': entities, 'severity': severity,
                        'desired_for_seconds': hold, 'eval_interval_seconds': 5,
                        'native_for_seconds': (hold + 5 if hold else 0) if kind == 'direct' else 0,
                        'observation_expression': (f'label_replace({normalized(observation, key)}, \"cluster_id\", \"{CLUSTER}\", \"__name__\", \".*\")' if kind == 'stateful' else observation),
                        'metric_name': key, 'trigger': trigger, 'clear': clear, 'reason': reason,
                        'scenario': scenario or key, 'source_ids': [source],
                        'nightingale_tests': 'evidence_in_separate_report', 'real_h100_tests': 'not_run'})

    for key, title, field_name in [
        ('sram', 'SRAM超阈值标志', 'DCGM_FI_DEV_SRAM_EXCEEDED'),
        ('remap_failed', '行重映射失败', 'DCGM_FI_DEV_ROW_REMAP_FAILURE'),
        ('remap_pending', '行重映射待维护', 'DCGM_FI_DEV_ROW_REMAP_PENDING')]:
        rule(key, title, valid(field_name), [field_name], GPUS, 2 if key == 'remap_pending' else 1, hold=10 if key == 'remap_pending' else 0,
             trigger='有效布尔标志=1', clear='有效布尔标志=0',
             reason='缺数和无效输入保持已确认异常，维护操作由运维复核。')

    for key, title, temperature, limit, entities in [
        ('gpu_thermal', 'GPU达到运行温度门槛', 'DCGM_FI_DEV_GPU_TEMP', 'DCGM_FI_DEV_GPU_MAX_OP_TEMP', GPUS),
        ('memory_thermal', 'HBM达到运行温度门槛', 'DCGM_FI_DEV_MEMORY_TEMP', 'DCGM_FI_DEV_MEM_MAX_OP_TEMP', GPUS),
        ('switch_thermal', 'NVSwitch达到降速温度门槛', 'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT',
         'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_LIMIT_SLOWDOWN', [SWITCH])]:
        margin = f'({valid(limit)} - on (entity_id) {valid(temperature)})'
        rule(key, title, split_hysteresis(margin, '<= 0', '> 5'), [temperature, limit], entities,
             trigger='设备门槛减当前温度<=0，持续10秒', clear='温度余量>5°C',
             reason='5°C解除回差和10秒持续时间为本次工程提案。门槛使用设备读数。')

    for key, title, mask, severity in [
        ('sw_thermal', '软件热降频持续', 32, 2), ('hw_thermal', '硬件热降频持续', 64, 1),
        ('power_cap', '训练功率限制持续', 4, 3), ('power_brake', '外部供电限制信号', 128, 2),
        ('hw_slowdown', '硬件slowdown状态', 8, 2), ('sync_boost', '同步boost限制状态', 16, 3)]:
        expression = bit(mask)
        if key == 'power_cap':
            expression = f'({expression} * on (entity_id) {valid("DEMO_JOB_RUNNING")})'
        rule(key, title, expression, ['DCGM_FI_DEV_CLOCKS_EVENT_REASONS'] +
             (['DEMO_JOB_RUNNING'] if key == 'power_cap' else []), GPUS, severity,
             trigger=f'原因位0x{mask:x}置位并持续10秒', clear='有效原因位清零',
             reason='分别识别热、功率、供电和组同步原因，关联作业与主机证据。')

    rule('clock_unknown','时钟原因存在未核实位',
         f'({valid("DCGM_FI_DEV_CLOCKS_EVENT_REASONS")} >= bool 512)',
         ['DCGM_FI_DEV_CLOCKS_EVENT_REASONS'],GPUS,3,
         trigger='已知位集合之外的位出现',clear='回归已知位集合',
         reason='已知热降频位仍独立解码，未知位记录待核实。')

    counters = [('ecc_new', '不可纠正ECC近期新增', 'DCGM_FI_DEV_ECC_DBE_VOL_TOTAL', 1),
                ('thermal_time', '近期热限制时长增加', 'DCGM_FI_DEV_THERMAL_VIOLATION', 2),
                ('pcie_replay', 'PCIe replay近期活动', 'DCGM_FI_DEV_PCIE_REPLAY_COUNTER', 2),
                ('nvlink_crc', 'Hopper NVLink CRC近期活动', 'DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL', 2),
                ('nvlink_recovery', 'Hopper NVLink recovery近期活动', 'DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL', 2),
                ('nvlink_replay', 'Hopper NVLink replay近期活动', 'DCGM_FI_DEV_NVLINK_REPLAY_TOTAL', 2),
                ('switch_replay', 'NVSwitch端口replay近期活动', 'DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERROR_TOTAL', 2),
                ('switch_recovery', 'NVSwitch端口recovery近期活动', 'DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERROR_TOTAL', 2)]
    for key, title, name, severity in counters:
        rule(key, title, f'({recent(name)} > bool 0)', [name], SWITCH_LINKS if key.startswith('switch_') else GPUS,
             severity, hold=5, trigger='30秒窗口有新增且持续5秒', clear='窗口内无新增且当前输入有效',
             reason='演示窗口30秒，生产候选窗口300秒。互联>0仅为活动策略提案，按现场基线审定。')

    xid = valid('DCGM_FI_DEV_XID_ERRORS')
    reviews = yaml.safe_load((ROOT/'monitoring/catalog/xid-review.yaml').read_text())['items']
    verified = valid('DEMO_RECOVERY_VERIFIED')
    for key, title, disposition, severity in [
        ('xid_node', 'XID节点事件待处置', 'node_incident_review', 1),
        ('xid_reset', 'XID GPU重置复核', 'gpu_reset_review', 1),
        ('xid_app', 'XID训练作业复核', 'training_job_review', 2)]:
        codes = [i['code'] for i in reviews if i['disposition'] == disposition]
        bad = '(' + ' or '.join(f'({xid} == {code})' for code in codes) + ')'
        observation = f'(({bad} * 0 + 1) or (({xid} == 0) and on(entity_id) ({verified} == 1)))'
        rule(key, title, observation, ['DCGM_FI_DEV_XID_ERRORS','DEMO_RECOVERY_VERIFIED'], GPUS, severity, hold=0,
             trigger='最近码属于该处置分组', clear='有效码值0并取得恢复确认记录',
             reason='其他码值和缺数保持事件。最近码无法提供完整事件流，记录原始日志后人工复核。', source='nvidia.xid.catalog')

    known_codes=[i['code'] for i in reviews]
    known='('+' or '.join(f'({xid} == {code})' for code in known_codes)+')'
    unknown=f'(({xid} > 0) unless ({known}))'
    rule('xid_unknown','XID目录外码值待复核',
         f'(({unknown} * 0 + 1) or (({xid} == 0) and on(entity_id) ({verified} == 1)))',
         ['DCGM_FI_DEV_XID_ERRORS','DEMO_RECOVERY_VERIFIED'],GPUS,2,hold=0,
         trigger='非零有效码超出已核对目录',clear='有效0并取得恢复确认记录',
         reason='记录驱动版本与有序日志后核对适用性。',source='nvidia.xid.catalog')
    scope_codes=[i['code'] for i in reviews if i['disposition']=='deployment_scope_review']
    scope='('+' or '.join(f'({xid} == {code})' for code in scope_codes)+')'
    rule('xid_scope','XID与部署范围需复核',
         f'(({scope} * 0 + 1) or (({xid} == 0) and on(entity_id) ({verified} == 1)))',
         ['DCGM_FI_DEV_XID_ERRORS','DEMO_RECOVERY_VERIFIED'],GPUS,2,hold=0,
         trigger='观测到虚拟化相关处置码',clear='有效0并取得恢复确认记录',
         reason='物理卡训练场景中先核对部署身份。',source='nvidia.xid.catalog')

    for key, title, name, severity in [
        ('sxid_fatal', 'NVSwitch fatal SXid待复核', 'DCGM_FI_DEV_NVSWITCH_FATAL_ERRORS', 1),
        ('sxid_nonfatal', 'NVSwitch nonfatal SXid待复核', 'DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS', 2)]:
        code = valid(name)
        observation = f'(({code} > bool 0) and ({code} > 0)) or (({code} == 0) and on(entity_id) ({verified} == 1))'
        rule(key, title, observation, [name,'DEMO_RECOVERY_VERIFIED'], [SWITCH], severity, hold=0,
             trigger='该SXid通道存在有效非零码', clear='有效码值0并取得恢复确认记录',
             reason='按fatal/nonfatal来源分流并保存具体码。逐码RMA决策需官方排障和现场证据。',source='nvidia.nvswitch')

    for key, title, name, ids, bad, clear in [
        ('gpu_link_down', '预期GPU NVLink端口未连接', 'DCGM_FI_DEV_NVLINK_GET_STATE', GPU_LINKS, '== 0', '> 0'),
        ('switch_link_down', '预期NVSwitch端口未活动', 'DCGM_FI_DEV_NVSWITCH_LINK_STATUS', SWITCH_LINKS, '!= 2', '== 2')]:
        state = valid(name)
        obs = split_hysteresis(state, bad, clear)
        rule(key, title, f'(({obs}) and on (entity_id) ({valid("DEMO_EXPECTED_LINK")} == 1))',
             [name,'DEMO_EXPECTED_LINK'], ids, trigger='预期端口有效但未达到链路状态条件',
             clear='GPU端口ACTIVE/SLEEP或NVSwitch端口ACTIVE', reason='仅配置清单中预期启用的端口参与，GPU与交换机枚举独立。',source='nvidia.topology')

    gen = f'({valid("DCGM_FI_DEV_PCIE_LINK_GEN")} < bool on (entity_id) {valid("DEMO_EXPECTED_PCIE_GEN")})'
    width = f'({valid("DCGM_FI_DEV_PCIE_LINK_WIDTH")} < bool on (entity_id) {valid("DEMO_EXPECTED_PCIE_WIDTH")})'
    degraded = f'((({gen} + on(entity_id) {width}) > bool 0) * on(entity_id) {valid("DEMO_JOB_RUNNING")})'
    rule('pcie_degraded','训练负载下PCIe链路退化',degraded,
         ['DCGM_FI_DEV_PCIE_LINK_GEN','DCGM_FI_DEV_PCIE_LINK_WIDTH','DEMO_EXPECTED_PCIE_GEN','DEMO_EXPECTED_PCIE_WIDTH','DEMO_JOB_RUNNING'],
         GPUS, trigger='作业运行且代际或宽度低于清单', clear='链路达到预期或作业停止',
         reason='预期gen5/x16为模拟清单值，现场按主机、插槽和GPU配置核定。',source='nvidia.topology')

    fm = valid('DCGM_FI_DEV_FABRIC_MANAGER_STATUS')
    expected = valid('DEMO_EXPECTED_FABRIC')
    fm_bad = f'(({fm} == bool 1) + ({fm} == bool 2) + ({fm} == bool 4)) > bool 0'
    rule('fabric_manager','预期Fabric Manager未就绪',f'(((({fm_bad}) == 1) or (({fm} == 3) * 0)) and on(entity_id) ({expected} == 1))',
         ['DCGM_FI_DEV_FABRIC_MANAGER_STATUS','DEMO_EXPECTED_FABRIC'],GPUS,
         trigger='预期需要FM，状态为未启动/启动中/失败，持续10秒',clear='有效状态3成功',
         reason='0/5/6另报能力或版本缺口。',source='nvidia.nvswitch')
    capability = f'(({fm} == bool 0) + ({fm} == bool 5) + ({fm} == bool 6)) > bool 0'
    rule('fabric_capability','预期fabric能力或版本缺口',f'(({capability}) and on(entity_id) ({expected} == 1))',
         ['DCGM_FI_DEV_FABRIC_MANAGER_STATUS','DEMO_EXPECTED_FABRIC'],GPUS,
         trigger='预期需要FM，状态0/5/6',clear='支持状态回归',reason='按采集和版本能力处理。',source='nvidia.nvswitch')
    fabric = valid('DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY')
    rule('fabric_health','fabric不健康或容量受限',f'(((({fabric} >= bool 2) and ({fabric} >= 2)) or (({fabric} == 1) * 0)) and on(entity_id) ({expected} == 1))',
         ['DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY','DEMO_EXPECTED_FABRIC'],GPUS,
         trigger='summary=2不健康或3容量受限',clear='summary=1健康',reason='summary=0保留覆盖缺口，需确认实际需要fabric。',source='nvidia.nvswitch')

    # Quality rules are evaluated directly against Prometheus so the lifecycle adapter is observable.
    names = '|'.join(name for name in FIELDS if name.startswith('DCGM_'))
    samples = f'label_replace({{__name__=~"{names}",{TARGET}}}, "metric_name", "$1", "__name__", "(.+)")'
    expected_input = f'DEMO_EXPECTED_INPUT{{{TARGET}}} == 1'
    present = f'count by (entity_id) ({samples})'
    missing_entity = f'((count by(entity_id) ({expected_input})) unless on(entity_id) ({present})) and on(job,instance) {healthy()}'
    # count loses job/instance, so source gating uses the single bound cluster.
    missing_entity = f'((count by(cluster_id,entity_id) ({expected_input})) unless on(entity_id) ({present})) and on(cluster_id) {healthy()}'
    missing_field = f'(({expected_input}) unless on(entity_id,metric_name) ({samples})) and on(entity_id) ({present}) and on(job,instance) {healthy()}'
    rule('entity_missing','预期设备观测消失',missing_entity,[],list(ENTITIES),hold=5,
         trigger='预期对象所有测量字段消失',clear='观测恢复',reason='已有硬件异常由持久规则继续保持。',kind='direct')
    rule('field_missing','必需测量字段缺失',missing_field,[],list(ENTITIES),hold=5,
         trigger='部分测量字段缺失',clear='字段恢复',reason='整对象消失时抑制逐字段告警。',kind='direct')
    stale_parts = []
    invalid_parts = []
    for name, spec in FIELDS.items():
        if not name.startswith('DCGM_'):
            continue
        value = raw(name)
        age = f'(time() - timestamp({value}))'
        stale_parts.append(normalized(f'(({age} > 15) or ({age} < 0))',name))
        invalid = f'(({value} != bool {value}) + ({value} >= bool {spec["maximum"]}) + ({value} < bool {spec["minimum"]}))'
        if spec['kind'] != 'gauge':
            invalid = f'({invalid} + ({value} != bool floor({value})))'
        invalid_parts.append(normalized(f'({invalid} > 0)',name))
    rule('input_stale','测量样本陈旧','('+' or '.join(stale_parts)+') and on(job,instance) '+healthy(),[],list(ENTITIES),hold=5,
         trigger='可见原始样本超过15秒',clear='新鲜样本恢复',reason='演示15秒，生产候选90秒。',kind='direct')
    rule('input_invalid','测量值无效','('+' or '.join(invalid_parts)+') and on(job,instance) '+healthy(),[],list(ENTITIES),hold=5,
         trigger='NaN/Inf/sentinel或非法枚举',clear='有效值恢复',reason='按字段类型验证。',kind='direct')
    duplicate = f'(count by(cluster_id,entity_id,metric_name) ({samples}) > 1) and on(cluster_id) {healthy()}'
    rule('input_duplicate','重复采集输入',duplicate,[],list(ENTITIES),hold=5,
         trigger='同对象同字段存在多个序列',clear='唯一输入恢复',reason='硬件规则拒绝重复输入。',kind='direct')
    rule('collector_down','模拟采集目标不可用',f'up{{{TARGET}}} == 0',[],[NODE],hold=5,
         trigger='up=0',clear='up=1',reason='采集链路故障。',kind='direct')

    state_rules = []
    for entry in entries:
        if entry['kind'] == 'stateful':
            state_rules.append({'rule_id': entry['rule_id'], 'metric_name': entry['metric_name'],
                                'entity_ids': entry['entity_ids'],
                                'confirm_seconds': entry['desired_for_seconds'],
                                'observation_expression': entry['observation_expression']})
    config = {'schema_version':1,'scope':'simulation-only','production_admitted':False,
              'cluster_id':CLUSTER,'uuids':list(ENTITIES),'identity_label':'entity_id','entity_labels':ENTITIES,
              'upstream_url':'http://prometheus:9090','maximum_confirmation_gap_seconds':6,'poll_seconds':2,'max_poll_age_seconds':15,'rules':state_rules}
    return {'schema_version':'0.1.0','scope':'H100_training_simulation_acceptance',
            'production_admitted':False,'fields':FIELDS,'entities':ENTITIES,'rules':entries}, config


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    catalog,config=build()
    outputs={'rules/comprehensive-catalog.json':catalog,'rules/comprehensive-lifecycle.json':config}
    views=[]
    for path in ['monitoring/catalog/ecc-xid-review-queries.yaml','monitoring/catalog/thermal-links-review-queries.yaml']:
        for view in yaml.safe_load((ROOT/path).read_text())['queries']:
            expression=view['expression']
            for old,new in [('fixture-cluster',CLUSTER),('job="dcgm"',f'job="{JOB}"'),
                            ('fixture-node:9400','comprehensive-source:9430'),('GPU-FIXTURE-000','GPU-DEMO-000')]:
                expression=expression.replace(old,new)
            views.append(dict(view,expression=expression))
    outputs['rules/comprehensive-views.json']={'scope':'simulation-only','views':views}
    for name,data in outputs.items():
        content=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
        path=ROOT/name
        if args.check:
            if path.read_text()!=content:raise SystemExit('生成文件需更新 '+name)
        else:path.write_text(content)
    print(f'PASS: {len(catalog["rules"])}条候选规则，{len(config["rules"])}条持久规则，{len(FIELDS)}项输入')


if __name__=='__main__':main()
