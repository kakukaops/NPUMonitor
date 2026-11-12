# H100已登记设备观测消失

rule_id：`nvidia.expected_gpu_observation_missing`  
version：0.1.0；schema_version：0.2.0；lifecycle：draft；default_policy：disabled  
日期：2026-11-09；维护者：GPU监控规则库维护者  
结构化定义：[rules.yaml](../catalog/rules.yaml)

## 1. 检测目标与影响

采集正常时，已登记UUID在本批四个必需字段中全部不可见。

覆盖目标：H100-C04。输入：[nvidia.gpu_temp](../../../common/monitoring/metrics/nvidia.gpu_temp.md)、[nvidia.ecc_dbe_volatile_total](../../../common/monitoring/metrics/nvidia.ecc_dbe_volatile_total.md)、[nvidia.sram_exceeded](../../../common/monitoring/metrics/nvidia.sram_exceeded.md)、[nvidia.remap_failed](../../../common/monitoring/metrics/nvidia.remap_failed.md)、[prometheus.target_up](../../../common/monitoring/metrics/prometheus.target_up.md)、[inventory.expected_devices](../../../common/monitoring/metrics/inventory.expected_devices.md)。只读查询已有Prometheus，不向生产采集写规则或新增collector。

## 2. 依据与H100适用性

[prometheus.up](https://prometheus.io/docs/concepts/jobs_instances/)、[prometheus.functions](https://github.com/prometheus/prometheus/blob/v3.2.1/docs/querying/functions.md)、`project.scope`（见[来源表](../../../common/monitoring/catalog/sources.yaml)）。

阈值均为工程评审参数，实际scrape/权限和维护契约必须重新核对。

| H100配置 | 设计软件基线 | 该字段/配置实际可用 | 采集/现场验证 |
| --- | --- | --- | --- |
| H100 PCIe | Linux 595.112.07；DCGM至少4.3.x，精确DCGM/Exporter待固定 | unknown | not_run |
| H100 SXM | 同上 | unknown | not_run |
| H100 NVL | 同上 | unknown | not_run |

本批使用[合成绑定](../catalog/batch1-binding.yaml)：fixture-cluster、dcgm、fixture-node:9400以及两个GPU-FIXTURE UUID。它们不是真实H100库存；modelName、MIG、版本/字段支持和标签重标记仍需核验。规则无法仅靠这些占位值实现生产自动发现，实际绑定/维护流程仍是阻塞项。

## 3. 表达式与解释

采集正常时，用预期UUID清单减去本批四个必需字段中仍有任一观测的设备集合。整组观测全空只报设备观测，不证明物理掉卡；只有温度缺失而其他字段还在时不报设备消失。

固定设备/字段清单展开为label_replace常量向量，不依赖不存在的expected_*采集指标，也不使用Prometheus recording rule。优点是不改采集；代价是表达式随库存变大，配置更新、查询预算和维护生命周期需在发布前实现。此处常量只服务评审用例。

<details>
<summary>完整PromQL快照（与YAML一致）</summary>

```promql
((label_replace(label_replace(label_replace(label_replace(vector(1), "cluster_id", "fixture-cluster", "__name__", ".*"), "job", "dcgm", "__name__", ".*"), "instance", "fixture-node:9400", "__name__", ".*"), "UUID", "GPU-FIXTURE-0000", "__name__", ".*") or label_replace(label_replace(label_replace(label_replace(vector(1), "cluster_id", "fixture-cluster", "__name__", ".*"), "job", "dcgm", "__name__", ".*"), "instance", "fixture-node:9400", "__name__", ".*"), "UUID", "GPU-FIXTURE-0001", "__name__", ".*")) unless on(cluster_id,UUID,job,instance) (count by(cluster_id,UUID,job,instance) (label_replace({__name__=~"DCGM_FI_DEV_GPU_TEMP|DCGM_FI_DEV_ECC_DBE_VOL_TOTAL|DCGM_FI_DEV_SRAM_EXCEEDED|DCGM_FI_DEV_ROW_REMAP_FAILURE",cluster_id="fixture-cluster",job="dcgm"}, "metric_name", "$1", "__name__", "(.+)")))) and on(cluster_id,job,instance) ((up{cluster_id="fixture-cluster",job="dcgm"} == 1) and (((time() - timestamp(up{cluster_id="fixture-cluster",job="dcgm"})) >= 0) and ((time() - timestamp(up{cluster_id="fixture-cluster",job="dcgm"})) <= 90)))
```

</details>

## 4. 参数与严重度

| 参数 | 本批值 | 依据/影响 |
| --- | --- | --- |
| 评估周期 | 30秒 | 工程提案，需匹配实际scrape |
| for持续时间 | 60秒 | 工程提案；本次promtool只验证表达式，夜莺for尚未测试 |
| 新鲜度 | 90秒，允许恰好90秒，拒绝未来时间戳 | 基于30秒scrape的假设；timestamp在原始selector上提取 |
| 设备与字段 | 2个合成UUID、4个必需字段 | 不是H100生产规模/字段全集 |
| 级别 | warning / 夜莺2 | 工程风险分级，非NVIDIA统一告警标准 |

字段绑定、库存、别名或参数变化时，同步表达式、版本和用例；不能只改YAML参数数字而保留旧表达式。

## 5. 触发、结束与不可判断

触发含义：采集正常时，已登记UUID在本批四个必需字段中全部不可见。

结束含义：监控观测恢复，不证明物理GPU已修复。查询错误、行政关闭、输入缺失和无效值不等于硬件恢复。源失败时缺数规则受到抑制；完整观测消失时不重复发出每字段缺失。状态非法/陈旧/重复时硬件表达式退出并显示数据质量问题。

特别是硬件告警先触发、随后失去有效输入，夜莺可能把空结果当resolved。**本批未实现结束原因适配，也未验证夜莺状态机，不能把数据质量告警出现视为已解决此问题。** 保持disabled，待集成时验证“不误发硬件已修复”及恢复文案。

## 6. 通知与处置

必需通知字段：rule_id, version, cluster_id, event_time, end_reason, UUID；逐字段质量问题还需metric_name和采集源，硬件问题需观测值/数据质量。

触发摘要：H100已登记设备观测消失：请核对输入及影响。

结束摘要：监控观测恢复，不证明物理GPU已修复。

处置：核对预期UUID及字段配置；本批观测全空不等于证明物理掉卡或其他指标也全空。值班人员先核对库存与维护状态、原始指标及时间、同卡其他字段和采集错误，再关联驱动/XID/业务影响并按平台流程升级；未经授权不执行负载诊断、隔离、重置或重启。

## 7. 误报、漏报及依赖

本批仅覆盖已登记设备和四个字段；从未登记的新卡、超出配置字段、没有来源的数据以及实际更复杂的标签/拓扑不能推断已覆盖。预期库存过期或维护未标记会误报，错误的序列归属会漏报。不同H100形态和MIG实例不能直接复用这份绑定。

硬件规则依赖源可用、输入质量和唯一性；质量规则的抑制只减少同源噪声，不实现通知侧根因归并。原ECC草案依旧独立，尚未对其应用全套身份/重复与结束语义约束。

## 8. 用例与实际验证

[本批49用例/392断言](../tests/h100_batch1.md)同时对八条表达式断言，覆盖正常、单卡/全组缺数、失效采集、陈旧、NaN/Inf/sentinel、重复、多卡与跨集群。相反条件也测试，避免只验证命中。固定Prometheus 3.2.1离线求值已通过。

状态：expression_tests=passed；nightingale_tests=not_run；real_cluster_tests=not_run。样本不执行夜莺for/通知，也不证明H100现场字段采集。此前六条实验规则的通知测试不转移到本规则。

## 9. 发布门禁与变更

阻塞项：真实库存和标签绑定、H100形态/版本与字段映射、维护/库存升级、夜莺持续/结束语义、实际采样和查询预算。当前不导入运行环境、不自动启用；无虚拟化不等于已确认MIG关闭。

| 日期 | 版本 | 变更 | 影响 |
| --- | --- | --- | --- |
| 2026-11-09 | 0.1.0 | 完整卡片、合成绑定和边界表达式 | 离线通过，不声明夜莺/H100验收 |


实验适配说明：本卡for=60秒为目标持续时间；夜莺9.3.0首个命中已计一个评估周期，30秒评估时实验副本原生配置为90秒。目标值不变，详见[持续时间适配](../../docs/08-H100草案流式模拟验证.md#5-持续时间适配)。


合成绑定集成证据：本规则的独立夜莺实验副本已随[11个流式用例](../tests/h100_batch1-streaming-results.yaml)通过；该证据不转记为现场准入或真实H100测试通过。
