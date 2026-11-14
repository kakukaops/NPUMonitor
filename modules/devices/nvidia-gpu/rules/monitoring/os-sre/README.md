# OS SRE GPU规则（当前接入版本）

**规范主清单：**[第14篇GPU监控指标与告警规则说明表](../../docs/14-GPU监控指标与告警规则说明表.md)是GPU规则领域的唯一规范入口。本文说明或代码生成结果不替代主清单；当前实现范围和生产差距分别核对。

版本0.2.0。规则和诊断查询不依赖cluster_id、业务任务/作业ID、租户、Pod或作业运行状态。`job`是Prometheus采集配置的job，`instance`是采集目标地址；两者不需要业务系统提供。

本版本包含46项规则记录（34项硬件状态观测、11项原生质量/平台告警表达式、1项通知结果输入缺口）和25个只读诊断查询。默认未导入或启用。真实硬件与新版夜莺绑定仍待现场验证。

逐条来源、官方支持范围、项目判据、参数及用例索引见[规则来源与参数依据表](provenance.md)。

生产目标及未完成任务见[生产就绪审计](../../docs/12-生产就绪审计与任务清单.md)。当前不能直接全量启用；34项硬件观测仍需新身份状态层和夜莺绑定。交付按固定指标契约和模拟数据完成软件验收，不等待真实GPU数据；部署时自动预检兼容性。

## 文件入口

| 文件 | 内容 |
|---|---|
| [profile.yaml](profile.yaml) | 采集job范围、时间参数、可选OS资产清单 |
| [catalog.json](catalog.json) | 当前完整规则、身份匹配、输入依赖和旧版本映射 |
| [metrics.yaml](metrics.yaml) | 本版本指标契约，不再要求业务标签 |
| [views.yaml](views.yaml) | 无业务标签的25个诊断查询 |
| [observations.prom.yaml](observations.prom.yaml) | 硬件0/1观测的recording rules，供持久状态处理 |
| [native-alerts.prom.yaml](native-alerts.prom.yaml) | 可按现场配置采用的质量/平台原生告警 |
| [规则卡目录](cards/README.md) | 每条规则的PromQL、条件和限制 |
| [测试输入](tests.promtool.yaml) | 无业务上下文及隔离/异常回归用例 |

Prometheus YAML没有disabled开关，手动加载后就会执行。目录中的 `default_policy=disabled` 是接入策略，不是对Prometheus的自动禁用指令。本次没有修改运行中的Prometheus或夜莺规则。

## 标签与身份

| 对象 | 必需匹配标签 | 提供方 |
|---|---|---|
| 采集目标 | `job,instance` | Prometheus采集配置 |
| 物理GPU | `job,instance,UUID` | 采集配置与DCGM Exporter实际设备标识 |
| GPU端口 | 上述标签加 `link_id` | 采集器或OS侧基础设施映射 |
| NVSwitch | `job,instance,switch_id` | 采集器或OS侧基础设施映射 |
| NVSwitch端口 | 上述标签加 `link_id` | 采集器或OS侧基础设施映射 |

不要求Hostname、cluster_id、entity_id、业务归属或训练任务。UUID、switch_id、link_id等标签仍需核对现场采集格式；没有这些输入就报告身份缺口，不用卡序号或GPU UUID伪造交换机身份。当前物理GPU范围排除带MIG实例标签的样本。

原始序列即使附带业务标签，输出也只保留上述硬件/采集标签，以及规则生成的metric_name等技术标签。去标签前先按设备键检查唯一性；重复输入报告质量异常，硬件判断拒绝歧义样本。不同instance不能相互提供温度门槛或硬件状态。

## 哪些只需要DCGM

SRAM标志、行重映射、温度与设备温度门槛、时钟限制原因位、ECC/互联错误近期新增等，使用DCGM测量及up，不要求资产清单或业务信息。字段未采集、陈旧、非法或重复时，不生成正常/恢复证据。

功率限制改为设备状态信息，不能据此断言训练性能下降。PCIe链路低于预期的判断要求：现场确认的TX/RX字节速率字段、OS配置的每卡预期代际/宽度和活动速率门槛。只有实际PCIe传输活动达到门槛并持续满足条件才给异常证据；空闲或缺失活动输入不提供异常或恢复证据。Profiling字节速率按本项目已核对的参考契约为gauge，不再执行rate；实际采集版本仍需核实。

## 可选OS资产与恢复证据

以下都是基础设施信息，不是业务属性：

- 预期设备/必需字段：用于设备或target被移除、字段缺失检测。没有清单时，不能知道“一张从未出现的卡本来应该存在”。
- 预期启用端口：只检测应启用的链路，不把未接线端口统一判故障。
- 预期PCIe配置与活动门槛、是否需要fabric：由主机/插槽/设备拓扑及现场基线确定，没有统一gen5/x16假设。
- XID/SXid恢复确认：`os_sre_recovery_verified`为可选的运维流程证据，必须与对应硬件的规范化job/instance/UUID或switch_id一致；不是现成DCGM字段。未接入时只能触发并保持，不能自动认定错误已修复。

默认资产清单为空，不提供虚假的生产设备。配置结构示例见[接入方案](../../docs/11-OS-SRE无业务属性规则方案.md)。按现场能力启用相关规则，字段缺口不能解释为正常。

## 执行语义与旧版本

34项硬件表达式输出的是0/1观测：0为有效解除证据，1为异常证据，空向量为未知；还需持久状态层实现持续确认、缺数保持和恢复关联。不能把非空的0直接作为原生告警。旧 `lab/recovery_adapter.py` 是cluster绑定的模拟适配器，不能直接用新profile替换其数据库配置；新硬件身份的持久状态/夜莺绑定需要单独适配并验收。

原生质量与平台表达式按Prometheus非空向量语义执行，up==0虽然值为0仍代表触发。通知失败项当前标记blocked：源码复核已确认夜莺v9.3.0定义通知错误计数器；此前仅根据运行中缺少序列的推断已更正。该计数器的现场采集、实际调用覆盖和失败增量仍待核对，通知队列长度不能替代投递结果。本版不继续使用DEMO_NOTIFY_FAILURES_TOTAL，也不以队列长度冒充投递成功率。

旧H100模拟表达式、catalog/rules.yaml等冻结草案及既有验收保留为历史来源，不作为当前现场模板；新规则已映射原45项规则并增加身份缺失检测，验证状态不继承旧版夜莺模拟通过记录。机器学习模块此次未改动。

## 生成和验证

在仓库根目录运行（沿用既有规则工具的Python/PyYAML环境）：

```bash
python modules/devices/nvidia-gpu/rules/scripts/build_os_sre.py
python modules/devices/nvidia-gpu/rules/scripts/build_os_sre.py --check
python modules/devices/nvidia-gpu/rules/scripts/test_os_sre.py
python modules/devices/nvidia-gpu/rules/scripts/test_os_sre.py --check
python modules/devices/nvidia-gpu/rules/scripts/check_os_sre_provenance.py
bash modules/devices/nvidia-gpu/rules/scripts/test_monitoring.sh
```

现场配置可保存在被Git忽略的.local下，再运行 `build_os_sre.py --profile .local/os-sre-profile.yaml --output .local/os-sre-rendered`；不覆盖默认版本或旧模拟绑定。
