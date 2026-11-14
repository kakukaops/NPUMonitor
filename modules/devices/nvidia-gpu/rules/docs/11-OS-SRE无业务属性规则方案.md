# OS SRE无业务属性规则方案

下文主体保留2026-11-12初版方案及当时接入状态；其中“未接入/未导入”等不表示当前事实，当前接入范围以第14篇和第15篇记录为准。

**规范入口：**[第14篇GPU生产主清单](14-GPU监控指标与告警规则说明表.md)是本模块指标、规则语义、适用性及取舍的唯一规范基线。本文在主清单范围内解释需求、实现或操作；旧阶段结论不覆盖主清单。当前代码/台账/证据仅说明实际实现，不能因规范补齐而追认已上线；存在差异按主清单附录C登记。

2026-11-13方案更新：检测职责按[第16篇双通道方案](16-XID事件与指标状态双通道监控方案.md)执行：XID/SXID作为错误事件入口，指标状态规则独立检测，质量/平台规则保障覆盖。当前最近码观测不等于完整事件流；完整事件采集待补齐。**跨规则事件关联和通知收敛按用户要求暂缓，本期不开发或上线**；既有单规则状态及通知机制保持。第14篇已逐项标注角色和XID重叠关系。下文历史阶段状态不覆盖这一最新范围。

日期：2026-11-12。当前接入版本0.2.0，[入口及规则卡](../monitoring/os-sre/README.md)。本次修改规则契约和PromQL，不修改ML模块，也不直接替换运行中的模拟告警。

逐条依据见[规则来源与参数依据表](../monitoring/os-sre/provenance.md)，并区分官方语义、项目判据、工程参数与验证证据。

## 1. 修改依据与范围

现场由OS SRE负责，只能稳定获取主机、设备、采集器和可选资产拓扑，不能依赖训练任务、租户、业务集群或调度上下文。旧版的cluster_id匹配、模拟entity_id、DEMO_JOB_RUNNING及写死的夜莺规则ID不作为新版查询条件。

新PromQL使用job/instance与物理设备标识；job指Prometheus采集配置，不指训练作业。所有匹配和聚合保留采集目标，避免移除cluster_id后发生跨主机串卡或many-to-many错误。原始额外标签先进行重复检测，再从输出去掉；不能用max掩盖重复输入。

完整映射见catalog.json的previous_rule_id：原45项均有明确去向，另增硬件身份缺失检测；通知投递失败因没有真实输入而显式阻塞。25个诊断视图同步改写。旧冻结文件不重写，保留其当时的模拟测试含义，当前规则入口已切换到OS SRE版本。

## 2. 行为变化

| 场景 | 新行为 |
|---|---|
| 所有硬件匹配 | 不要求cluster_id、任务/作业ID或entity_id；按采集目标及硬件身份匹配 |
| 功率限制 | 仅报告原因位状态，信息级；不推断业务性能损失 |
| PCIe链路低于预期 | 静态OS资产预期 + 实测PCIe活动；无活动信息不作判断，空闲不触发、不解除已确认异常 |
| XID分类 | 可提供OS侧进程/软件排查线索，无需获取业务归属；不会把XID统一归为硬件故障 |
| 缺卡、缺字段和端口掉链 | 仅在OS维护对应预期清单后判断；未配置就保留覆盖缺口 |
| 平台查询与评估 | 按组件采集目标聚合，不再写死18等数据库规则ID；评估停滞还需运维声明预期持续执行 |
| 通知投递失败 | 拒绝模拟字段；源码已找到通知错误counter；现场采集、调用范围与失败触发未验证，仍为blocked_missing_input |

温度门槛仍读设备上报值；5°C回差、90秒新鲜度、300秒计数窗口、60秒确认及PCIe至少120秒等均为工程候选参数，不宣称NVIDIA统一生产阈值。字段语义沿用既有固定来源台账；新增PCIe Profiling字段对照公共指标台账1009/1010，现场型号、版本和采集支持未验收。

## 3. 配置示例

只需修改collector_job_regex匹配现场Prometheus采集job即可使用不依赖清单的规则。下面所有资产和数值只是结构示例，不随默认配置生成生产对象：

```yaml
schema_version: 1
profile: os-sre
collector_job_regex: dcgm.*
nightingale_job_regex: nightingale.*
lifecycle_job_regex: gpu-lifecycle.*
freshness_seconds: 90
counter_window_seconds: 300
confirmation_seconds: 60
gpus:
  - job: dcgm
    instance: node-a:9400
    UUID: GPU-REPLACE-WITH-ACTUAL-UUID
    required_fields:
      - DCGM_FI_DEV_GPU_TEMP
    # 以下按实际设备/插槽及基线填写，不是统一生产参数。
    pcie_gen: 5
    pcie_width: 16
    pcie_active_bytes_per_second: 1000000
    fabric_expected: true
switches: []
links: []
monitor_targets: []
```

GPU端口清单字段为job、instance、UUID、link_id；交换机及端口使用switch_id替代UUID。monitor_targets使用job、instance，可选evaluation_expected=true。标签名和粒度需要先与真实采集器核实，不要求上层业务提供。

规则输出包含可选静态清单recording rules，不修改采集到的原始序列。清单与状态观测分组之间可能有一次评估延迟；新部署应先核对清单已生成再启用相应告警。原始指标重复、缺数、非法值或不支持不可补零。

## 4. 接入与发布边界

新catalog是当前规则编写和现场评审入口。11项直接查询表达式可按数据源和接口规范绑定夜莺；34项0/1硬件观测必须由兼容新身份的持久状态层消费，不能直接变成“有样本就报警”的规则。旧模拟适配器拒绝不匹配的绑定是预期行为，本次不绕过它的数据库保护或自动改写在线事件身份。

本次没有自动导入新版本、清理旧事件或重建生产状态。真实数据源/标签及新身份状态层未接入前，不宣称完成新版端到端生产发布。旧模拟服务仍运行其原有冻结测试绑定，页面旧cluster标记不代表新PromQL仍需要该属性。

新版验证记录见[OS SRE验收证据](../monitoring/os-sre/evidence/summary.json)。新规则独立测试，不把原H100模拟验收结果转换成新版本或真实GPU的验收。
