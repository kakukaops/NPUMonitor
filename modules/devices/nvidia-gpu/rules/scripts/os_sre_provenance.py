"""Rule provenance metadata/rendering only: never modifies executable PromQL."""
import copy
import hashlib
import json
from pathlib import Path
import re
import yaml

BASE = Path(__file__).resolve().parents[1]/'monitoring/os-sre'


def load_definitions():
    return yaml.safe_load((BASE/'provenance.yaml').read_text())


def parameter_definitions(profile):
    return {
        'P01':{'name':'样本新鲜度','value':profile['freshness_seconds'],'unit':'s','kind':'engineering_proposal','origin':'profile.yaml/freshness_seconds','boundary':'官方timestamp提供时间语义，90秒不是官方通用值。'},
        'P02':{'name':'近期计数窗口','value':profile['counter_window_seconds'],'unit':'s','kind':'engineering_proposal','origin':'profile.yaml/counter_window_seconds','boundary':'increase函数由官方定义，窗口长度由项目选定。'},
        'P03':{'name':'持续确认','value':profile['confirmation_seconds'],'unit':'s','kind':'engineering_proposal','origin':'profile.yaml/confirmation_seconds + rule.for_seconds','boundary':'逐条实际值可能为0或PCIe下限120秒；当前仅验证表达式，不证明状态引擎落实此时长。'},
        'P04':{'name':'生成规则组评估周期','value':30,'unit':'s','kind':'engineering_proposal','origin':'build_os_sre.py/outputs','boundary':'生成YAML的interval；不代表现场scrape周期或夜莺已采用该值。'},
        'P05':{'name':'温度解除回差','value':5,'unit':'°C','kind':'engineering_proposal','origin':'build_os_sre.py/split(..., <=0, >5)','boundary':'温度门槛读设备，但5°C回差和差值判据是项目设计。'},
        'P06':{'name':'PCIe最小持续确认','value':120,'unit':'s','kind':'engineering_proposal','origin':'max(120, confirmation_seconds)','boundary':'非官方性能退化阈值；实际状态层尚待接入。'},
        'P07':{'name':'PCIe预期gen/width与活动速率','value':'逐卡配置；默认无值','unit':'generation/lanes/bytes_per_second','kind':'operator_inventory','origin':'profile.yaml/gpus','boundary':'gen5/x16及1MB/s只在结构示例/测试出现，不是生产默认值。'},
        'P08':{'name':'输入类型与有效范围','value':'按metrics.yaml逐字段约束','unit':'field_specific','kind':'mixed_official_semantics_project_guard','origin':'metrics.yaml + valid/recent','boundary':'官方blank值和字段含义不能证明全部项目min/max在现场可用；TYPE、sentinel和数值精度需核对。'},
        'P09':{'name':'告警严重度','value':'逐条1/2/3','unit':'level','kind':'engineering_proposal','origin':'catalog.json/rules[].severity','boundary':'项目通知分类，不是官方RMA等级；没有生产故障分级校准证据。'},
        'P10':{'name':'设备身份与预期清单','value':'job/instance + 硬件ID；预期清单默认空','unit':'identity/inventory','kind':'operator_inventory_project_contract','origin':'profile.yaml + identity/const','boundary':'不需要业务属性；switch/link标签仍要核对真实采集格式；预期配置不是自动发现的事实。'},
        'P11':{'name':'XID/SXid恢复证据','value':'错误码0且os_sre_recovery_verified=1','unit':'boolean','kind':'project_lifecycle_protocol','origin':'build_os_sre.py/XID/SXid observations','boundary':'运维确认是项目扩展输入；不能把最近码归零直接当作硬件修复。'},
        'P12':{'name':'已知时钟位集合边界','value':512,'unit':'bitmask_boundary','kind':'project_guard_from_pinned_definitions','origin':'固定字段宏0x1至0x100；当前>=512检测','boundary':'仅提示超出当前已知定义，不能直接判硬件故障。'},
    }


def matching_cases(expression,tests):
    if not expression:return []
    return [t['name'] for t in tests if any(expression in a['expr'] for a in t.get('promql_expr_test',[]))]


def attach_provenance(catalog,profile):
    definition=load_definitions();origins=definition['rules'];sources=definition['sources']
    assert set(origins)=={r['rule_id'] for r in catalog['rules']},'来源映射必须逐条覆盖且无孤立条目'
    tests=yaml.safe_load((BASE/'tests.promtool.yaml').read_text())['tests'] if (BASE/'tests.promtool.yaml').exists() else []
    parameters=parameter_definitions(profile)
    for rule in catalog['rules']:
        p=copy.deepcopy(origins[rule['rule_id']]);refs=list(p['semantic_source_ids'])
        refs+=['project.os_sre.policy','project.os_sre.inventory','project.os_sre.tests']
        if rule['expression']:refs+=['prometheus.functions','prometheus.operators']
        if rule['kind']=='stateful':refs+=['project.lifecycle.policy']
        refs=list(dict.fromkeys(refs));assert set(refs)<=set(sources),rule['rule_id']
        rule['previous_source_ids']=rule['source_ids'];rule['source_ids']=refs
        ids=list(p['parameter_ids'])+['P03','P04','P09']
        if rule['expression'] and 'timestamp(' in rule['expression']:ids+=['P01']
        if rule['kind']=='stateful':ids+=['P08','P10']
        ids=list(dict.fromkeys(ids));assert set(ids)<=set(parameters)
        p['parameters']=[]
        for ident in ids:
            value=parameters[ident]['value']
            if ident=='P03':value=rule['for_seconds']
            if ident=='P09':value=rule['severity']
            p['parameters'].append({'parameter_id':ident,'value':value,'kind':parameters[ident]['kind']})
        p['input_evidence']=p.get('input_evidence',rule['input_fields'])
        for locator in p.get('additional_locators',[]):
            assert locator['source_id'] in sources
        p['field_locators']={name:copy.deepcopy(definition['fields'][name]) for name in rule['input_fields'] if name in definition['fields']}
        if rule['rule_id'].endswith('pcie_degraded'):
            # Both current-link fields and Profiling transfer fields are explicit.
            assert len(p['field_locators'])==4
        if rule['kind']=='direct' and not rule['input_fields']:
            p['field_locator_scope']='动态检查已登记字段或平台指标；不能由空input_fields推断无输入依赖'
        p['test_case_ids']=matching_cases(rule['expression'],tests)
        p['expression_sha256']=hashlib.sha256(rule['expression'].encode()).hexdigest() if rule['expression'] else None
        p['evidence_scope']='合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例'
        assert p['production_case_evidence']==[], '本项目当前没有生产案例，不能在来源整理中伪造'
        p['production_case_evidence']=[]
        p['real_hardware_validation']='not_run'
        rule['provenance']=p
    catalog['provenance_version']=1
    catalog['provenance_reviewed_at']=definition['reviewed_at']
    catalog['parameter_origins']=parameters
    catalog['provenance_sources']=copy.deepcopy(sources)
    for view in catalog['views']:
        names=set(re.findall(r'\bDCGM_[A-Z0-9_]+\b',view['expression']))
        view['provenance']={'basis_kind':'project_readonly_view','source_ids':['nvidia.dcgm.fixed_fields','prometheus.functions','prometheus.operators','project.os_sre.policy'],
            'field_locators':{n:copy.deepcopy(definition['fields'][n]) for n in sorted(names)},
            'test_case_ids':matching_cases(view['expression'],tests),'production_case_evidence':[],
            'limitations':'字段含义和只读变换，不是独立故障判据、RMA或训练性能SLA。'}


def cell(value):
    return str(value).replace('|','&#124;').replace('\n','<br>')


def render_provenance(catalog):
    rows=['# OS SRE规则来源、项目判据与参数依据','',
          '覆盖当前46项规则和25个只读视图。来源审阅日期：'+catalog['provenance_reviewed_at']+'。本表由[结构化依据](provenance.yaml)与当前规则自动生成，避免与PromQL、参数和规则卡各自维护。','',
          '**这些是基于官方字段语义编写的项目规则，不是官方PromQL规则包，也没有逐条生产案例背书。** 官方支持内容与项目选择分栏列出；旧模拟验收不自动成为新版或真实硬件验收。','',
          '## 阅读方式','',
          '| 标记 | 含义 | 不代表 |','|---|---|---|',
          '| 官方语义 | 字段、类型、单位、状态枚举或查询函数定义 | 官方认可本项目完整表达式、窗口、分级及恢复协议 |',
          '| 项目判据 | 本项目组合条件与身份/质量策略 | 已被行业生产环境普遍采用 |',
          '| 工程参数 | 当前profile值或代码中的候选参数 | NVIDIA统一门槛或现场已校准值 |',
          '| 合成用例 | tests.promtool.yaml中的可定位向量断言 | 生产检测率、真实故障、持续确认或新版夜莺端到端验证 |',
          '| 生产证据 | 当前逐条均为空；真实硬件为not_run | 用旧版模拟证据填充缺口 |','',
          '## 审阅发现','',
          '| 项目 | 本次结论 | 当前处理 |','|---|---|---|',
          '| 通知错误指标 | 夜莺v9.3.0源码实际定义并注册AlertNotifyErrorTotal；候选全名为n9e_alert_alert_notify_error_total，channel为通知通道标签。运行中暂时没有该序列不能证明源码没有指标。 | 保持blocked：继续核对调用点、真实采集和失败注入；队列长度不能代替投递结果。不在来源整理中擅自启用规则。 |',
          '| NVLink枚举 | 字段1508使用NVML字段返回值；不能与其他dcgmNvLinkLinkState_t枚举混用。 | 当前0/正数判据显式标为需现场版本核对，不把合成值当作真实设备证明。 |',
          '| XID分组 | 官方有逐码行动建议，但当前分组来自本地2026-11-06快照与项目处置归类。 | 展开分组内错误码；不宣称本项目呼叫级别和恢复协议是官方方案。 |','',
          '## 官方与项目来源登记','',
          '| 来源ID | 文档/代码与版本 | 具体定位及可支持结论 | 不能支持的结论 | 复核状态/固定源码摘要 |','|---|---|---|---|---|']
    for ident,s in catalog['provenance_sources'].items():
        link=s.get('url') or s['path'];label=f'[{s["title"]}]({link})'
        rows.append('| '+' | '.join(map(cell,[ident,label+'；'+s['version'],s['locator']+'；'+s['supports'],s['does_not_support'],s['review_status']+('；SHA256 '+s['retrieved_sha256'][:16]+'…' if s.get('retrieved_sha256') else '')]))+' |')
    rows+=['','固定源码下载摘要和失败尝试见[来源复核记录](evidence/source-review.json)。滚动文档只代表所审阅页面，不保证现场版本兼容；旧来源台账和本地XID快照继续保留。','',
           '## 参数依据表','','| 编号 | 参数 | 当前配置或实现值 | 归属与定位 | 适用边界 |','|---|---|---|---|---|']
    for ident,p in catalog['parameter_origins'].items():
        rows.append('| '+' | '.join(map(cell,[ident,p['name'],str(p['value'])+' '+p['unit'],p['kind']+'；'+p['origin'],p['boundary']]))+' |')
    categories=list(dict.fromkeys(r['provenance']['category'] for r in catalog['rules']))
    for category in categories:
        rows+=['','## '+category,'','| 规则 | 官方语义与具体定位 | 本项目实际判据 | 参数来源 | 限制与验证 |','|---|---|---|---|---|']
        for rule in catalog['rules']:
            p=rule['provenance']
            if p['category']!=category:continue
            ident=rule['rule_id'];source_links=[]
            for sid in p['semantic_source_ids']:
                s=catalog['provenance_sources'][sid];source_links.append(f'[{sid}]({s.get("url") or s["path"]})')
            locators=[]
            for name,meta in p['field_locators'].items():
                url=catalog['provenance_sources']['nvidia.dcgm.fixed_fields']['url']+'#L'+str(meta['canonical_line'])
                locators.append(f'[{name} / ID{meta["field_id"]}]({url})')
            for locator in p.get('additional_locators',[]):
                src=catalog['provenance_sources'][locator['source_id']]
                url=src['url']+'#L'+str(locator['start_line'])+'-L'+str(locator['end_line'])
                locators.append(f'[{locator["symbol"]} L{locator["start_line"]}—{locator["end_line"]}]({url})')
            source_text=p['official_support']+'<br>'+'；'.join(source_links)
            if locators:source_text+='<br>'+'；'.join(locators)
            params='；'.join(x['parameter_id']+'='+str(x['value']) for x in p['parameters'])
            evidence='合成表达式关联'+str(len(p['test_case_ids']))+'个用例' if p['test_case_ids'] else '无执行表达式或暂无关联用例'
            evidence+='；真实硬件未验，生产案例无。'
            label=f'<a id="{ident.replace(".","-").replace("_","-")}"></a>[{rule["title"]}](cards/{ident}.md)<br>`{ident}`'
            rows.append('| '+' | '.join(map(cell,[label,source_text,'输入：'+'、'.join(p['input_evidence'])+'<br>'+p['project_criterion'],params,p['limitations']+'<br>'+evidence]))+' |')
    rows+=['','## XID当前项目分组明细','','官方原文动作与本项目分组不是同一概念。以下码来自本地快照，不在本次来源整理中静默更新规则。','','| 规则 | 本地处置分组 | 当前纳入码值 |','|---|---|---|']
    for rule in catalog['rules']:
        p=rule['provenance']
        if 'xid_codes' in p:
            codes=', '.join(map(str,p['xid_codes'])) if p['xid_codes'] else '不在本地已登记目录中的非零有效码；不是固定码列表'
            rows.append('| '+' | '.join(map(cell,[rule['rule_id'],p['xid_group'],codes]))+' |')
    rows+=['','## 25个只读诊断视图','','| 视图 | 字段定位与来源 | 项目处理与边界 | 关联表达式用例 |','|---|---|---|---|']
    for view in catalog['views']:
        p=view['provenance'];loc=[]
        for name,m in p['field_locators'].items():
            loc.append(f'[{name} / ID{m["field_id"]}]('+catalog['provenance_sources']['nvidia.dcgm.fixed_fields']['url']+'#L'+str(m['canonical_line'])+')')
        rows.append('| '+' | '.join(map(cell,[view['query_id'],'；'.join(loc),p['limitations'],'、'.join(p['test_case_ids']) or '未关联']))+' |')
    rows+=['','## 用例与验证索引','','下表只说明某条表达式在哪些合成测试中被求值；其中可能仅有正常或缺数断言，不能据用例数量声称故障分支全覆盖。持续确认、状态持久化和新版夜莺绑定不在这些断言内。','',
           '| 规则 | 可定位测试名 | 生产案例 | 真实硬件/新版夜莺绑定 |','|---|---|---|---|']
    for rule in catalog['rules']:
        p=rule['provenance'];rows.append('| '+' | '.join(map(cell,[rule['rule_id'],'、'.join(p['test_case_ids']) or ('无（当前阻塞）' if not rule['expression'] else '未关联当前配置用例'),'无','not_run']))+' |')
    rows+=['','验证结果和限定范围见[既有验收](evidence/summary.json)；来源细化自身的完整性检查见[来源表验收](evidence/provenance-check.json)。本次不改变任何执行表达式或在线规则。','']
    return '\n'.join(rows)


def source_table_for_card(rule,sources):
    p=rule['provenance']
    ids=p['semantic_source_ids']
    refs='；'.join(f'[{sid}]({sources[sid].get("url") or "../"+sources[sid]["path"]})' for sid in ids)
    # Official source rows have URLs; project basis is separately linked via the matrix.
    return ['','## 来源与参数依据','','| 项目 | 内容 |','|---|---|',
            '| 官方语义 | '+cell(p['official_support'])+' |',
            '| 具体来源 | '+refs+' |',
            '| 项目判据 | '+cell(p['project_criterion'])+' |',
            '| 参数来源 | '+cell('；'.join(i['parameter_id']+'='+str(i['value']) for i in p['parameters']))+' |',
            '| 证据边界 | '+cell(p['evidence_scope'])+'；生产案例无；真实硬件未验 |',
            '| 待核实项 | '+cell(p['limitations'])+' |','',
            '[查看完整逐条来源表](../provenance.md#'+rule['rule_id'].replace('.','-').replace('_','-')+')；[结构化来源定义](../provenance.yaml)。']
