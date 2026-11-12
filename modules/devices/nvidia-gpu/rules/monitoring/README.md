# GPU 指标与规则文档库

格式版本：0.2.0；日期：2026-11-09。  
状态：已有6份指标/输入卡、9条默认禁用草案；累计307个合成用例、675个求值断言通过，8条夜莺实验副本的11个流式用例已通过，真实H100验证尚未完成。

先阅读[首批卡片与离线验收](tests/h100_batch1.md)，再阅读[指标卡样例](../../common/monitoring/metrics/nvidia.ecc_dbe_volatile_total.md)和[规则卡样例](rules/nvidia.ecc_dbe_new_errors.md)，确认内容深度，再扩充[覆盖矩阵](coverage.md)。既有实验规则仍保存在根目录 rules/，其运行验收不自动转移到本目录的新表达式。

## 第一版台账入口（2026-11-09）

- [覆盖矩阵](coverage.md)：24项检测目标，区分必须核验、必须覆盖告警、条件适用、看板、可选策略和范围外。
- [指标与输入台账](../../common/monitoring/metric-inventory.md)：92项候选输入，包含82个唯一DCGM字段ID及10项采集状态、配置或平台/外部上下文；不是92个已验证H100指标。
- [规则提案台账](rule-inventory.md)：33项提案，包含准入检查/看板/外部边界；不是33条可执行告警。
- [XID逐码台账](xid-review.md)：保留源快照中78个H100适用代码，78码已有人工处置分级草案。

对应YAML为catalog/coverage-targets.yaml、metric-inventory.yaml、rule-inventory.yaml和xid-review.yaml。它们属于规划台账，不能交给现有夜莺导入器；正式定义仍单独保存在metrics.yaml和rules.yaml。台账的必需/可选/替代输入关系和参数需在正式建卡时审定。

文档由YAML生成，避免多份表格漂移：在已有PyYAML的文档工具环境运行 `python3 modules/devices/nvidia-gpu/rules/scripts/render_h100_inventory.py`；只检查可运行 `python3 modules/devices/nvidia-gpu/rules/scripts/render_h100_inventory.py --check`。这不启动Docker或修改运行配置，也不生成告警表达式。

## 第一版型号范围

**第一版只做NVIDIA H100训练场景，不启用虚拟化；H200及其他型号后续再扩展。** [H100范围和配置矩阵](../../common/monitoring/hardware/H100.md)是适用性核验入口，[hardware.yaml](../../common/monitoring/catalog/hardware.yaml)保存结构化型号配置。

Linux设计驱动固定为核对日最新Production Branch补丁595.112.07，详见[训练与驱动基线](../../common/monitoring/hardware/H100训练基线.md)；实际安装版本和采集栈仍需核验。

指标卡和规则卡必须明确H100型号、PCIe/SXM/NVL形态、物理卡/MIG粒度及软件栈条件；分开记录官方字段支持、采集验证与真实集群验证。H100产品存在的官方证据不能替代指标支持证据；unknown不能变为默认支持。

官方指标语义、硬件能力/故障标志、官方诊断/RMA条件、项目PromQL和工程参数分别注明来源。并非所有型号都必然有独立官方PromQL规则包，本项目不预设其存在。

## 1. 目录和职责

| 位置 | 内容 | 谁负责保持一致 |
| --- | --- | --- |
| templates/metric.md | 指标说明卡模板 | 规则库维护者 |
| templates/rule.md | 规则说明卡模板 | 规则库维护者 |
| metrics/ | 每个指标一份详细说明 | 指标核验者 |
| rules/ | 每条规则一份详细说明和处置步骤 | 规则维护者 |
| hardware/H100.md、catalog/hardware.yaml | 第一版H100形态、范围及准入状态 | 硬件适配维护者 |
| catalog/metrics.yaml | 指标名、类型、单位、标签、适用性等结构化定义 | 与指标卡同步 |
| catalog/rules.yaml | 表达式、参数、启用策略及依赖等结构化定义 | 与规则卡同步 |
| catalog/sources.yaml | 固定来源、核对日期和具体支持的结论 | 引用者 |
| tests/ | 输入样本、预期结果和验证记录 | 与表达式同步 |

YAML 是程序可读取的事实与执行字段；Markdown 负责解释依据、边界和操作步骤。Markdown 展示的表达式、参数及状态必须与 YAML 一致，不能维护两套不同默认值。正式目录保持默认禁用；独立实验副本的绑定、导入和流式验证见[指南](../docs/08-H100草案流式模拟验证.md)。

## 2. 标识、版本及缺失信息

- metric_id / rule_id / source_id 稳定不变，使用小写字母、数字、下划线和点；标题和原始指标名变化不更换ID。
- schema_version 是格式版本；version 是单个对象版本，两者不混用。语义或表达式修改更新对象版本，并写明影响。
- unknown 表示没有核实，not_applicable 表示有依据证明不适用。空列表不代表“所有型号支持”。
- 参数中的 null 表示尚未给定，绝不隐式换成0。每个待验证项须说明缺少什么证据及怎样补足。
- 来源记录固定提交或文档release、章节、核对日期及支持的具体结论。只能找到滚动页面时明确标为rolling，并列为发布前待补项。

## 3. 两套独立状态

对象维护状态 lifecycle：draft（草案）→ candidate（候选）→ released（已发布）→ deprecated（退役）。

规则默认策略 default_policy：disabled（未准入）/ opt_in（需现场启用）/ auto_when_applicable（条件满足自动启用）。released也不自动代表默认启用。草案和候选不得自动导入生产。

验证状态逐层记录：source_review、expression_tests、nightingale_tests、real_cluster_tests，各自使用 not_run / passed / failed / partial。通过来源核对不等于通过故障测试，实验版的通过记录不等于新版本表达式已通过。

运行覆盖状态另行记录：covered / not_applicable / missing_input / invalid_input / stale / query_error / unverified。规则未触发、表达式无结果和GPU健康不能互相等同。

## 4. 参数与数据约定

时间参数以整数秒保存，窗口以 window_seconds 保存；YAML中的expression是该参数组合下的完整PromQL快照，无未替换的占位符。参数修改必须同步表达式、测试和版本。当前不开发模板编译器。

计数值注明累计范围与重置条件；gauge注明枚举或位掩码语义；区分次数、速率、百分数与比率。设备身份至少是cluster_id+UUID，MIG规则必须额外确认实例粒度。不得随意丢弃原始标签后跨设备求和；重复采集的去重策略必须另有说明。

严重度保存业务语义 critical / warning / info，同时明确夜莺1/2/3的映射和选择依据。通知中的结束原因区分条件退出、数据不可判断及行政关闭；不把全部结束都命名为硬件恢复。

## 5. 审阅重点

首份样例请重点确认：字段深度是否足够；官方事实与工程建议是否分明；触发/结束和缺数是否说清楚；处置步骤是否可操作；待验证项是否能阻止错误的默认启用。目前先审阅台账的目标分类和输入范围，再分批完善正式指标卡/规则卡；台账条目不自动视为正式卡片。


## 夜莺合成绑定验收

[流式验证指南](../docs/08-H100草案流式模拟验证.md)提供场景、UI验证和复现命令，[结果文件](tests/h100_batch1-streaming-results.yaml)记录8条实验副本、11用例通过。正式catalog默认禁用及现场绑定not_run状态不变；实验通过不能继承为真实H100支持。质量目标60秒在夜莺9.3.0原生适配为90秒。夜莺界面原生恢复仍仅代表条件退出，本地判读通知不宣称硬件修复。


## 硬件告警保持与解除实验

另有2条独立持久实验规则，通过9个保持/解除场景及上游/适配器/夜莺故障重启验证。[设计与验证](../docs/09-硬件告警保持与解除策略.md)、[证据](tests/hardware-lifecycle-results.yaml)说明新增有状态组件、原生能力探测和生产门禁。它们不计入正式9条草案或真实H100支持；输出gpu_lifecycle_active是派生告警状态，不能当作GPU实时指标。

ECC 分域诊断和 XID 分级的范围、查询及测试见[统计域与逐码分级](ecc-xid-review.md)。

维护、温度、降频和 Hopper 互联已补充 15 条复核查询，通过 138 个离线用例和 8 个独立 Prometheus 流式场景。运行方法和采集缺口见[本批说明](thermal-links-review.md)。
