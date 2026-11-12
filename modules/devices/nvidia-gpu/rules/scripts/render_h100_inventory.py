#!/usr/bin/env python3
"""Validate and render proposed H100 ledgers. Does not build or deploy alert rules.

Requires PyYAML in the documentation tool environment. Runtime services are untouched.
"""
import argparse
from collections import Counter
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from layout import relocate_markdown

ROOT = Path(__file__).resolve().parents[1] / 'monitoring'
CLASS = {'required_check':'必须核验', 'mandatory_alert':'必须覆盖的告警目标',
         'conditional_alert':'条件适用告警', 'dashboard':'看板/上下文',
         'optional_policy':'可选训练策略','out_of_scope':'范围外/外部诊断'}


def read(name):
    return yaml.safe_load((ROOT / 'catalog' / name).read_text())


def table(headers, rows):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', '<br>')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(cell(c) for c in row) + ' |' for row in rows])


def load_validate():
    targets=read('coverage-targets.yaml')['targets']
    metrics=read('metric-inventory.yaml')['metrics']
    rules=read('rule-inventory.yaml')['rules']
    xid=read('xid-review.yaml')
    sources={s['source_id'] for s in read('sources.yaml')['sources']}
    profiles=read('hardware.yaml')
    assert profiles['release_scope']['target_models']==['H100']
    assert profiles['release_scope']['workload']=='training'
    tmap={t['target_id']:t for t in targets}
    mmap={m['metric_id']:m for m in metrics}
    rmap={r['rule_id']:r for r in rules}
    assert len(tmap)==len(targets)==24
    assert set(tmap)=={f'H100-C{n:02d}' for n in range(1,25)}
    assert len(mmap)==len(metrics) and len(rmap)==len(rules)
    formal_m={m['metric_id'] for m in read('metrics.yaml')['metrics']}
    formal_r={r['rule_id'] for r in read('rules.yaml')['rules']}
    for row in targets+metrics+rules:
        assert set(row['source_ids'])<=sources, row.get('name_zh')
        assert row.get('real_h100_tests',row.get('real_h100_validation','not_run'))=='not_run'
    for t in targets:
        assert t['classification'] in CLASS
        assert set(t['metric_ids'])<=mmap.keys() and set(t['rule_ids'])<=rmap.keys()
        assert t['actual_applicability']=='unknown'
        assert t['review_status']=='proposed_pending_review'
        assert t['metric_ids'] and t['rule_ids'] and t['decision_reason']
    for r in rules:
        assert r['classification'] in CLASS
        assert set(r['metric_ids'])<=mmap.keys() and set(r['target_ids'])<=tmap.keys()
        assert r['expression'] is None and r['default_policy']=='disabled'
        assert r['input_binding']=='candidate_pool_required_optional_alternatives_pending_review'
        if r.get('formal_rule_id'): assert r['formal_rule_id'] in formal_r
        for mid in r['metric_ids']: assert r['rule_id'] in mmap[mid]['rule_ids']
    field_ids=[]
    for m in metrics:
        assert m['target_ids'] and m['rule_ids']
        assert set(m['target_ids'])<=tmap.keys() and set(m['rule_ids'])<=rmap.keys()
        if m.get('formal_metric_id'): assert m['formal_metric_id'] in formal_m
        if m['input_kind']=='dcgm_field': field_ids.append(m['dcgm_field_id'])
        for rid in m['rule_ids']: assert m['metric_id'] in rmap[rid]['metric_ids']
    assert len(field_ids)==len(set(field_ids)), 'aliases must not count as separate inputs'
    codes=[i['code'] for i in xid['items']]
    assert len(codes)==len(set(codes))==xid['source_snapshot']['h100_yes_count']==78
    assert all(i['official_action_review']=='snapshot_reviewed' and i['default_policy']=='disabled' and i['rule_id'] is None for i in xid['items'])
    evidence=read('inventory-evidence.yaml')
    assert evidence['canonical_dcgm_entries']==len(field_ids)
    assert evidence['auxiliary_inputs']==len(metrics)-len(field_ids)
    assert evidence['rule_proposals']==len(rules)
    return targets,metrics,rules,xid


def render(targets,metrics,rules,xid):
    counts=Counter(t['classification'] for t in targets)
    coverage=['# H100 第一版检测覆盖矩阵','',
      '台账版本：0.1.0；日期：2026-11-09；状态：待审阅的目标清单。','',
      '范围为H100训练、无虚拟化、物理GPU；设计参考驱动固定为595.112.07（2026-11-06选定），没有因日期变化自动切换。PCIe/SXM/NVL、MIG实际模式、DCGM/Exporter及现场字段仍未知。','',
      f'**此表表示需要建设的覆盖目标，不表示生产覆盖。** 当前正式目录为{len(read("metrics.yaml")["metrics"])}个指标/输入卡、{len(read("rules.yaml")["rules"])}条draft/disabled规则；真实H100验证为0。24项目标来自工程审查，不是NVIDIA官方完整规则包，也不据此给出故障覆盖百分比。','',
      '[当前综合候选库](h100-training/README.md)已扩展为42项输入、45条告警规则与25个诊断视图；下面保留原始覆盖审查的实施分级，逐目标新进展见[实施映射](h100-training/coverage-map.md)。真实H100验证仍为not_run。','',
      '分类中“必须覆盖”表示产品要求，不意味着已有输入或已启用；“条件适用”在现场拓扑未知时不能变为“不适用”。型号、字段映射使用“必须核验”，避免硬凑成告警。','',
      table(['分类','目标数'],[(CLASS[k],v) for k,v in counts.items()]),'',
      '指标编号及详细语义见[指标台账](metric-inventory.md)，规则判据及缺口见[规则台账](rule-inventory.md)。此表由[coverage-targets.yaml](catalog/coverage-targets.yaml)生成。','',
      table(['目标ID','检测目标','分类/优先级','规则提案','实现/验证','适用条件与主要缺口'],[
       (t['target_id'],t['name_zh'],CLASS[t['classification']]+'/'+t['priority'],
        ', '.join('`'+x+'`' for x in t['rule_ids']),
        '部分草案/有合成测试，无H100验证' if t['implementation_status']=='partial_draft' else ('诊断查询/有合成测试，无H100验证' if t['implementation_status']=='review_queries' else '未实现/无H100验证'),
        t['applicability_condition']+'；'+t['decision_reason']) for t in targets]),'',
      '## 验收与后续顺序','',
      '先审阅P0型号/输入/数据质量，再完成P1内存、XID、温度降频及按训练拓扑适用的互联；容量效率作为可选策略。正式建卡时把每条提案的候选输入池拆成必需、可选和替代字段，并核实目标软件版本。','',
      '每项必须关联官方依据、实际有效字段、正式规则卡、测试与处置。当前所有现场适用性/输入仍为unknown；不能以“已登记24项”宣称完成监控覆盖。78个H100适用XID已有处置草案，见[XID台账](xid-review.md)。','',
      '依据：[H100覆盖审查](<../reports/H100 指标 规则 覆盖审查.md>)、[训练基线](hardware/H100训练基线.md)、[来源注册表](catalog/sources.yaml)。','']
    mdoc=['# H100 第一版指标与输入台账','',
      '日期：2026-11-09；状态：候选输入清单，不是已支持H100的白名单。','',
      f'共{len(metrics)}项：{sum(m["input_kind"]=="dcgm_field" for m in metrics)}个唯一DCGM字段ID，另有{sum(m["input_kind"]!="dcgm_field" for m in metrics)}项采集状态/配置/平台或外部上下文。后者不冒充已有GPU指标。{len(read("metrics.yaml")["metrics"])}项已有draft指标/输入卡，其余尚未建卡。','',
      '来源为固定DCGM header和固定Exporter配置；别名按字段ID合并。新版字段存在不证明所选DCGM 4.3.x及以上任一版本都支持，reference CSV存在/启用也不证明现场已发出。具体提交与哈希见[构建证据](catalog/inventory-evidence.yaml)。','',
      '“类型/单位”是源码或配置驱动的候选语义，目标栈仍需核对；没有CSV条目的字段不猜测实际Prometheus名称。label/string字段可能是标签或元信息，不保证有独立数值时序。','',
      '所有项的真实采集状态均unknown，逐H100形态字段支持未验证。规则引用表示候选输入池，不代表所有字段必须同时采集。新旧时长字段、总计数和位置明细不重复相加。','',
      table(['指标ID','名称 / 字段ID','固定header名称','参考CSV映射 / 类型 / 状态','语义类型 / 单位','用途与边界','对应目标'],[
       (m['metric_id'],m['name_zh']+' / '+str(m.get('dcgm_field_id','非DCGM')),
        m.get('canonical_field_in_reference_header',m['input_kind']),
        '; '.join(x['configured_field']+' / '+x['configured_type']+' / '+('启用' if x['enabled_in_reference_csv'] else '注释') for x in m.get('reference_csv_entries',[])) or ('up（Prometheus自生）' if m.get('actual_prometheus_name')=='up' else '未在参考CSV列出/实际映射待核实'),
        m['semantic_kind_proposal']+' / '+m['unit_proposal'],m['caution'],', '.join(m['target_ids'])) for m in metrics]),'',
      '逐项source_ids、正式卡片关联和规则引用见[metric-inventory.yaml](catalog/metric-inventory.yaml)。候选H100字段与R595/DCGM/Exporter适配必须单独核对，禁止直接整表导入或修改现有采集。','']
    rdoc=['# H100 第一版规则提案台账','',
      f'日期：2026-11-09；共{len(rules)}项提案，包括告警、准入检查、看板、可选策略及外部范围说明。不是{len(rules)}条可执行告警。','',
      '提案台账全部disabled、expression为空；部分已关联独立的draft规则卡，验证状态按对应范围保留，不升级为已发布。ECC/XID 诊断查询见[统计域和逐码分级](ecc-xid-review.md)。台账使用h100.*提案ID，正式草案保持nvidia.* ID，formal_rule_id/formal_rule_ids显式关联，不重命名。','',
      '每项metric_ids是候选输入池，必须/可选/替代关系待正式建卡时核定；例如旧ns时长与新s时长择一映射，不能同时统计。所有阈值、窗口、for和严重度尚未最终审定，不用统一85°C、TDP或低利用率阈值替代依据。','',
      '完整结构化定义见[rule-inventory.yaml](catalog/rule-inventory.yaml)，每项有来源、目标、输入、判据提案、结束语义和阻塞项。','']
    for r in rules:
        rdoc += ['## '+r['rule_id']+'：'+r['name_zh'],'',
          '- 分类/优先级：'+CLASS[r['classification']]+'/'+r['priority']+'；目标：'+', '.join(r['target_ids']),
          '- 候选输入：'+', '.join('`'+m+'`' for m in r['metric_ids']),
          '- 适用条件：'+r['applicability_condition'],
          '- 判据提案：'+r['judgment_proposal'],
          '- 结束语义：'+r['end_semantics'],
          '- 当前缺口：'+r['gap'],
          '- 来源：'+', '.join('`'+s+'`' for s in r['source_ids']),
          '- 卡片/验证：'+r['card_status']+'；表达式 '+r['expression_tests']+'；新提案夜莺和真实H100均not_run','']
    xdoc=['# H100 XID 逐码审查台账','',
      '登记日期：2026-11-09；目录证据为2026-11-06滚动快照，并非重新抓取的当前全集。','',
      '2026-11-11 完成固定快照的 78 码分级草案。项目处置列用于人工分流。当前默认禁用通知，现场适用性仍待核验。','',
      f'源页面SHA256：`{xid["source_snapshot"]["sha256"]}`；[官方目录]({xid["source_snapshot"]["source_url"]})。机器可读台账见[xid-review.yaml](catalog/xid-review.yaml)。','',
      '当前最近XID字段是gauge，不能保证scrape间所有事件、顺序、subcode或恢复动作均保存。不能用increase计算码值发生次数。通用文档中的XID160在该快照对H100=NO，不放入本表；不代表未来版本永远不适用。','',
      table(['XID','官方即时动作','官方调查动作','XID 154 联动','项目处置','复核说明'],
            [(i['code'],i['immediate_action'] or '空白',i['investigatory_action'] or '空白',
              i['xid_154_linkage'] or '空白',i['disposition'],i['reason']) for i in xid['items']]),'']
    return {'coverage.md':'\n'.join(coverage),'metric-inventory.md':'\n'.join(mdoc),
            'rule-inventory.md':'\n'.join(rdoc),'xid-review.md':'\n'.join(xdoc)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true',help='Validate and reject stale generated documents')
    args=parser.parse_args()
    try:
        targets,metrics,rules,xid=load_validate()
        output=render(targets,metrics,rules,xid)
        for name,content in output.items():
            content = relocate_markdown(content, "monitoring/" + name)
            path=ROOT/name
            if args.check:
                if not path.exists() or path.read_text()!=content:
                    raise ValueError('生成文档与YAML不一致：'+name)
            else:
                path.write_text(content)
        print(f'PASS: {len(targets)}目标 / {len(metrics)}候选输入 / {len(rules)}提案 / {len(xid["items"])}XID；引用一致，未生成可执行规则')
        return 0
    except (OSError,AssertionError,ValueError,KeyError,TypeError) as error:
        print('FAIL: '+str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
