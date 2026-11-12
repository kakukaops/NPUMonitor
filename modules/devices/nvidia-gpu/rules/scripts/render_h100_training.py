#!/usr/bin/env python3
"""Render complete metric/rule cards from the comprehensive acceptance catalog."""
import argparse
import sys
import json
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from layout import relocate_markdown

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'monitoring/h100-training'


def render():
    catalog=json.loads((ROOT/'rules/comprehensive-catalog.json').read_text())
    health=json.loads((ROOT/'rules/comprehensive-health.json').read_text())
    inventory=yaml.safe_load((ROOT/'monitoring/catalog/metric-inventory.yaml').read_text())['metrics']
    by_id={m.get('dcgm_field_id'):m for m in inventory if m.get('dcgm_field_id') is not None}
    source='https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h'
    evidence_path=OUT/'acceptance-results.yaml'
    evidence=yaml.safe_load(evidence_path.read_text()) if evidence_path.exists() else {}
    verified=set(evidence.get('verified_rule_ids',[]))
    outputs={}
    index=['# H100训练规则候选库','','本目录完成输入契约、规则参数、处置和模拟验收的对应关系。生产默认策略为disabled，真实H100采集、版本、MIG及拓扑仍待现场验收。',
           '', '[综合演示](http://localhost:19430) · [夜莺](http://localhost:17000) · [规则和指标目录](catalog.yaml)',
           '', '## 规则','','| 规则 | 严重度 | 目标持续时间 | 夜莺模拟验收 |','| --- | --- | --- | --- |']
    structured={'schema_version':'0.2.0','baseline':'H100 training / R595.112.07 design reference',
                'production_default':'disabled','real_h100_tests':'not_run','metrics':[],'rules':[]}
    for name,spec in catalog['fields'].items():
        metric_id='training.input.'+name.lower()
        record=by_id.get(spec['dcgm_field_id'],{})
        title=record.get('name_zh',name)
        use=[r for r in catalog['rules'] if name in r['input_fields']]
        schema={'metric_id':metric_id,'name_zh':title,'upstream_name':name,**spec,
                'source_ids':record.get('source_ids',['project.scope']),
                'actual_h100_support':'unknown','real_h100_tests':'not_run',
                'documentation':'metrics/'+metric_id+'.md'}
        structured['metrics'].append(schema)
        kind='工程配置/上下文' if spec['dcgm_field_id'] is None else 'NVIDIA字段候选'
        text=[f'# {title}','',f'metric_id `{metric_id}`，版本0.1.0，状态candidate。',
              '', '## 语义与单位','',f'原始名 `{name}`，字段ID `{spec["dcgm_field_id"]}`，类别为{kind}。',
              f'类型 `{spec["kind"]}`，单位 `{spec["unit"]}`。',
              '', '## 身份与适用性','', '按cluster_id及entity_id定位对象。GPU使用UUID，交换机使用switch_id，端口额外保留link_id。',
              'H100 PCIe、SXM、NVL的现场字段支持均待核验。模拟数据的modelName为SIMULATED，实例清单见catalog.yaml。',
              '', '## 有效性与缺数','',f'有效范围为 [{spec["minimum"]}, {spec["maximum"]})。整数、计数及枚举还要求整数值。',
              '样本需来自健康采集目标，原始年龄0—15秒，输入唯一。生产候选新鲜度90秒，须结合实际采样周期审定。',
              '拒绝NaN、Inf和sentinel。缺失、重复、陈旧、非法值进入独立质量规则，已确认硬件异常继续保持。',
              '', '## 采集与数值示例','',f'模拟正常值 `{spec["normal"]}`。此值用于样本，设备门槛字段在实际部署读取设备。',
              '演示每2秒采样。各查询单位换算在对应规则说明中标明。',
              '', '## 关联规则','']
        text += [f'- [{r["title"]}](../rules/{r["rule_id"]}.md)' for r in use]
        if not use:text.append('该输入用于清单、维护、历史或诊断视图。')
        text += ['', '## 来源与验证','',f'[固定DCGM字段定义]({source}) · [原始输入台账](../../metric-inventory.md)',
                 '来源核对、合成测试、夜莺模拟验收与真实H100采集分别保留证据。当前真实硬件验证为not_run。','']
        outputs[schema['documentation']]='\n'.join(text)
    for entry in catalog['rules']:
        rule_id=entry['rule_id']
        stateful=entry['kind']=='stateful'
        item=dict(entry,documentation='rules/'+rule_id+'.md',nightingale_simulation='passed' if rule_id in verified else 'not_run')
        structured['rules'].append(item)
        index.append(f'| [{entry["title"]}](rules/{rule_id}.md) | {entry["severity"]} | {entry["desired_for_seconds"]}秒 | {item["nightingale_simulation"]} |')
        inputs='、'.join('`'+name+'`' for name in entry['input_fields']) or '预期输入清单与采集状态'
        owner='持久状态适配器' if stateful else '夜莺原生评估器'
        text=[f'# {entry["title"]}','',f'rule_id `{rule_id}`，版本0.1.0，状态candidate，生产默认disabled。',
              '', '## 检测目标','',entry['reason'],
              '', '## 输入与适用条件','',inputs,
              '按候选清单选择GPU、交换机或端口对象。实际硬件形态、字段支持及维护流程待现场核验。',
              '', '## 触发、分级和解除','',f'- 触发条件为{entry["trigger"]}。',
              f'- 解除条件为{entry["clear"]}。',
              f'- 夜莺严重度{entry["severity"]}为本次工程提案，1/2/3分别对应critical/warning/info。',
              f'- 目标持续时间{entry["desired_for_seconds"]}秒，由{owner}执行。',
              f'- 夜莺每5秒评估，原生for={entry["native_for_seconds"]}秒。',
              '', '## 输入质量与状态','']
        if stateful:
            text += ['先按实体校验新鲜、唯一及有效值。连续有效触发满足持续时间后置为活动，未知输入使确认重新计时。',
                     '已确认异常在缺数、无效或查询失败时保持活动。有效解除证据到达后退出，事件ID保持至解除。',
                     '状态与待确认时间保存到独立Docker卷。确认采样间隔超过6秒时重新计时。']
        else:
            text += ['质量规则直接读取Prometheus。整对象消失时抑制逐字段缺失，采集失败时优先报告采集目标。',
                     '原生持续时间包含首个评估周期，本次将目标持续时间加5秒映射为原生for。']
        text += ['', '## 完整观测表达式','', '```promql',entry['observation_expression'],'```','',
                 '有状态规则的观测值1表示触发证据，0表示解除证据，无向量表示当前未取得可用决策证据。',
                 '', '## 参数和窗口','', '演示输入年龄上限15秒，计数演示窗口30秒。生产候选输入年龄90秒、计数窗口300秒。',
                 '温度解除回差5°C及持续时间为工程提案。功率、时钟和互联活动结合任务、设备配置与拓扑复核。',
                 '', '## 处置步骤','', '1. 核对对象身份、原始值、输入质量和关联事件。',
                 '2. 保存日志与计数窗口，评估作业影响和维护条件。',
                 '3. 按本规则解除证据核验结果，记录处置动作。解除表示对应检测条件退出。',
                 '', '## 测试与发布状态','',f'夜莺模拟验收 `{item["nightingale_simulation"]}`。固定样本见h100-training.promtool.yaml，完整结果见acceptance-results.yaml。',
                 '真实H100为not_run，生产规则默认禁用。模拟参数需经现场验收后形成生产配置。',
                 '', '## 来源','',f'[固定字段定义]({source}) · [覆盖矩阵](../../coverage.md) · [XID逐码台账](../../xid-review.md)','']
        outputs[item['documentation']]='\n'.join(text)
    for entry in health:
        rule_id=entry['key']
        structured['rules'].append(dict(entry,rule_id=rule_id,kind='platform',production_default='disabled',
                                        nightingale_simulation='passed' if rule_id in verified else 'not_run'))
        index.append(f'| [{entry["name"]}](rules/{rule_id}.md) | {entry["severity"]} | {entry["desired_for_seconds"]}秒 | '+('passed' if rule_id in verified else 'not_run')+' |')
        outputs['rules/'+rule_id+'.md']='\n'.join([
            '# '+entry['name'],'',f'rule_id `{rule_id}`，版本0.1.0，状态candidate，生产默认disabled。','',
            '## 条件与数据源','',entry['note'],'',
            f'目标持续时间{entry["desired_for_seconds"]}秒，夜莺每5秒评估，原生for={entry["for_seconds"]}秒，严重度{entry["severity"]}。',
            '观测故障条件退出后解除。规则通过独立本地备用通知通道发送。','',
            '```promql',entry['expression'],'```','',
            '## 处置','', '核对原始错误、评估计数和通知尝试，修复组件或配置后验证实际成功记录。',
            '看门狗在独立演示服务中记录组件不可达，Prometheus或夜莺停止时页面仍显示独立可用性记录。','',
            '## 验收','', '查询失败采用真实HTTP503，评估停滞采用探针调度间隔异常，通知失败采用实际Webhook503并核验备用通道。',
            '本次为模拟环境参数。完整原始记录和规则ID绑定保存在验收报告。','',
            '## 来源','', '[固定夜莺自监控定义](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)',''])
    views=json.loads((ROOT/'rules/comprehensive-views.json').read_text())['views']
    index += ['', '## 诊断与上下文视图', '', '这25项只读查询用于历史、趋势、统计域和事件上下文，不重复创建同一故障告警。', '']
    structured['views']=[]
    for view in views:
        qid=view['query_id']
        path='views/'+qid+'.md'
        structured['views'].append(dict(view,documentation=path,production_default='disabled'))
        index.append(f'- [{qid}]({path})')
        outputs[path]='\n'.join(['# '+qid,'','版本0.1.0，候选只读视图，H100物理训练场景。',
            '', '## 查询与参数','', '身份绑定为演示集群和两张模拟GPU，生产部署需替换为核实后的目标。',
            '原始样本有效性、新鲜度及采集健康约束见表达式。趋势窗口为5分钟；只有至少两个有效样本才计算增长。',
            '', '```promql',view['expression'],'```','', '## 解释与处置','',
            '历史计数非零不自动等同近期故障；纠正ECC趋势和分域数据用于定位与复核。',
            '码值视图用于事件分流，需结合节点日志及恢复动作。禁止通过这些查询自动重启、隔离或执行诊断。',
            '无结果可能表示无匹配活动或输入不可判定，先核对设备清单、字段及采集质量。',
            '', '## 验证与来源','',
            'ECC/XID和温度互联查询已有固定样本测试；综合演示可查询 /api/views 查看实际Prometheus求值结果。',
            '真实H100字段支持待现场验收。',
            '', '[固定DCGM字段定义]('+source+') · [覆盖矩阵](../../coverage.md)',''])
    index += ['', '## 验证入口','', '```bash','bash scripts/lab.sh comprehensive suite --case hardware',
              'bash scripts/lab.sh comprehensive suite --case quality',
              'bash scripts/lab.sh comprehensive suite --case platform',
              'bash scripts/lab.sh comprehensive suite --case semantics','```','',
              '综合演示地址为 http://localhost:19430，夜莺业务组为H100训练综合演示。','']
    outputs['README.md']='\n'.join(index)
    outputs['catalog.yaml']=yaml.safe_dump(structured,allow_unicode=True,sort_keys=False,width=120)
    return outputs


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    outputs=render()
    for name,text in outputs.items():
        if name.endswith(".md"):
            text = relocate_markdown(text, "monitoring/h100-training/" + name)
        path=OUT/name
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('文档需更新 '+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print('PASS: '+str(len(outputs))+'份综合规则/指标文档与目录一致')


if __name__=='__main__':main()
