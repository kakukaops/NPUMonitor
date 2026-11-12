# H100 SRAM超阈值标志

metric_id：`nvidia.sram_exceeded`  
version：0.1.0；schema_version：0.2.0；lifecycle：draft  
日期：2026-11-09；维护者：GPU监控规则库维护者  
结构化定义：[metrics.yaml](../catalog/metrics.yaml)；范围：[H100训练基线](../hardware/H100训练基线.md)

## 1. 定义与检测边界

SRAM超阈值状态，参考源码声明1=true；它不是错误次数。不能用volatile DBE累计值代算。

## 2. 原始字段与映射

| 项目 | 本批定义 | 证据层级 |
| --- | --- | --- |
| 原始名称/字段ID | DCGM_FI_DEV_SRAM_EXCEEDED / 346 | 引用下方来源；真实映射未验证 |
| 类型/单位 | gauge / boolean | 布尔字段gauge映射是本批候选，目标TYPE仍需核对 |
| 单位换算 | 无换算 | 不将标志当累计次数 |
| 累计/重置 | not_applicable；状态字段的清除行为仍需实测 | 不能把重启/清除当硬件修复 |

字段ID346，固定header为SRAM_EXCEEDED；参考CSV未列出，不能虚构已默认采集或推断设备不支持。

## 3. 标签、唯一键与粒度

唯一键：`cluster_id`, `UUID`。cluster_id由部署/采集标签提供，UUID用于物理卡身份，job/instance用于定位源；这些现场标签是否存在尚未核对。配置输入中的标签代表期望值，不是现场已提供的证明。MIG实例不在本批准入范围。

重复序列需要单列数据质量结果；不得通过sum/max随意合并。本批状态字段按cluster+UUID+metric_name检查唯一性。未登记的新UUID不会自动纳入硬件判断，需要准入/库存更新流程。

## 4. H100配置兼容矩阵

| H100配置 | 设计软件基线 | 该字段/配置实际可用 | 采集/现场验证 |
| --- | --- | --- | --- |
| H100 PCIe | Linux 595.112.07；DCGM至少4.3.x，精确DCGM/Exporter待固定 | unknown | not_run |
| H100 SXM | 同上 | unknown | not_run |
| H100 NVL | 同上 | unknown | not_run |

对于up和预期配置，本表表示绑定H100环境的验证状态，不代表它们是GPU硬件专属字段。未启用虚拟化已确认；MIG实际模式独立记录。该矩阵没有将任何H100形态标为已实测。

## 5. 有效值、无效值与缺数

按本批候选0/1布尔映射，其他值（包括2、负值、NaN、Inf、sentinel）不作硬件判断并触发质量条件；目标H100实际映射未验证。

质量规则的“不触发”和硬件规则的“条件退出”不能单独证明健康。源失败时先报告采集问题；字段缺失/陈旧/非法状态均为无法判断。source查询本身失败则需要平台评估错误可见性，不能指望同一条无法执行的PromQL发出通知。

## 6. 周期、权限与采集限制

本批评审参数为30秒评估、90秒最大样本年龄，基于假设30秒scrape，不是NVIDIA硬件参数。实际刷新/scrape周期、权限和字段可用性仍未知。生产绑定必须核实已有数据标签，不能要求部署者自行写规则或擅自改Prometheus配置。

## 7. 样本与验证

以下全部为合成样本，不是H100采集结果：

```text
# TYPE DCGM_FI_DEV_SRAM_EXCEEDED gauge
DCGM_FI_DEV_SRAM_EXCEEDED{cluster_id="fixture-cluster",job="dcgm",instance="fixture-node:9400",UUID="GPU-FIXTURE-0000"} 0
```

本批49个表达式用例/392断言的结果见[本批验证](../../../rules/monitoring/tests/h100_batch1.md)。它们验证逻辑而非现场TYPE/权限/硬件兼容；新规则夜莺及真实H100验证仍not_run。

关联规则：[nvidia.required_field_missing](../../../rules/monitoring/rules/nvidia.required_field_missing.md)、[nvidia.required_field_stale](../../../rules/monitoring/rules/nvidia.required_field_stale.md)、[nvidia.required_input_invalid](../../../rules/monitoring/rules/nvidia.required_input_invalid.md)、[nvidia.duplicate_input_series](../../../rules/monitoring/rules/nvidia.duplicate_input_series.md)、[nvidia.sram_threshold_exceeded](../../../rules/monitoring/rules/nvidia.sram_threshold_exceeded.md)。

## 8. 来源、缺口与变更

来源：[nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)、[nvidia.memory.sram](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/sram-uncorrectable-errors.html)。

固定版本定义、实际Exporter输出以及本项目的映射假设必须分开记录。发布前补齐真实H100形态、目标版本、原始/metrics、维护/设备变更流程和状态清除语义。当前draft，不自动启用。

| 日期 | 版本 | 变更 | 影响 |
| --- | --- | --- | --- |
| 2026-11-09 | 0.1.0 | 首批完整卡片与边界用例 | 仅草案和合成验证，不改变运行环境 |
