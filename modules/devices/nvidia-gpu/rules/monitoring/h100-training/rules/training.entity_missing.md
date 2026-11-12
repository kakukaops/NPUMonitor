# 预期设备观测消失

rule_id `training.entity_missing`，版本0.1.0，状态candidate，生产默认disabled。

## 检测目标

已有硬件异常由持久规则继续保持。

## 输入与适用条件

预期输入清单与采集状态
按候选清单选择GPU、交换机或端口对象。实际硬件形态、字段支持及维护流程待现场核验。

## 触发、分级和解除

- 触发条件为预期对象所有测量字段消失。
- 解除条件为观测恢复。
- 夜莺严重度2为本次工程提案，1/2/3分别对应critical/warning/info。
- 目标持续时间5秒，由夜莺原生评估器执行。
- 夜莺每5秒评估，原生for=10秒。

## 输入质量与状态

质量规则直接读取Prometheus。整对象消失时抑制逐字段缺失，采集失败时优先报告采集目标。
原生持续时间包含首个评估周期，本次将目标持续时间加5秒映射为原生for。

## 完整观测表达式

```promql
((count by(cluster_id,entity_id) (DEMO_EXPECTED_INPUT{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1)) unless on(entity_id) (count by (entity_id) (label_replace({__name__=~"DCGM_FI_DEV_GPU_TEMP|DCGM_FI_DEV_GPU_MAX_OP_TEMP|DCGM_FI_DEV_MEMORY_TEMP|DCGM_FI_DEV_MEM_MAX_OP_TEMP|DCGM_FI_DEV_CLOCKS_EVENT_REASONS|DCGM_FI_DEV_SRAM_EXCEEDED|DCGM_FI_DEV_ROW_REMAP_FAILURE|DCGM_FI_DEV_ROW_REMAP_PENDING|DCGM_FI_DEV_ECC_DBE_VOL_TOTAL|DCGM_FI_DEV_ECC_DBE_VOL_DEV|DCGM_FI_DEV_ECC_DBE_VOL_SRM|DCGM_FI_DEV_ECC_SBE_VOL_TOTAL|DCGM_FI_DEV_ECC_SBE_VOL_DEV|DCGM_FI_DEV_ECC_SBE_VOL_SRM|DCGM_FI_DEV_ECC_DBE_AGG_TOTAL|DCGM_FI_DEV_ECC_DBE_AGG_DEV|DCGM_FI_DEV_ECC_DBE_AGG_SRM|DCGM_FI_DEV_THERMAL_VIOLATION|DCGM_FI_DEV_PCIE_REPLAY_COUNTER|DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL|DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL|DCGM_FI_DEV_NVLINK_REPLAY_TOTAL|DCGM_FI_DEV_XID_ERRORS|DCGM_FI_DEV_PCIE_LINK_GEN|DCGM_FI_DEV_PCIE_LINK_WIDTH|DCGM_FI_DEV_NVLINK_GET_STATE|DCGM_FI_DEV_FABRIC_MANAGER_STATUS|DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY|DCGM_FI_DEV_NVSWITCH_FATAL_ERRORS|DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS|DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT|DCGM_FI_DEV_NVSWITCH_TEMPERATURE_LIMIT_SLOWDOWN|DCGM_FI_DEV_NVSWITCH_LINK_STATUS|DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERROR_TOTAL|DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERROR_TOTAL",cluster_id="h100-training-demo",job="h100-comprehensive"}, "metric_name", "$1", "__name__", "(.+)")))) and on(cluster_id) ((up{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15))
```

有状态规则的观测值1表示触发证据，0表示解除证据，无向量表示当前未取得可用决策证据。

## 参数和窗口

演示输入年龄上限15秒，计数演示窗口30秒。生产候选输入年龄90秒、计数窗口300秒。
温度解除回差5°C及持续时间为工程提案。功率、时钟和互联活动结合任务、设备配置与拓扑复核。

## 处置步骤

1. 核对对象身份、原始值、输入质量和关联事件。
2. 保存日志与计数窗口，评估作业影响和维护条件。
3. 按本规则解除证据核验结果，记录处置动作。解除表示对应检测条件退出。

## 测试与发布状态

夜莺模拟验收 `passed`。固定样本见h100-training.promtool.yaml，完整结果见acceptance-results.yaml。
真实H100为not_run，生产规则默认禁用。模拟参数需经现场验收后形成生产配置。

## 来源

[固定字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h) · [覆盖矩阵](../../coverage.md) · [XID逐码台账](../../xid-review.md)
