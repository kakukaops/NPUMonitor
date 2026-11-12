# 训练负载下PCIe链路退化

rule_id `training.pcie_degraded`，版本0.1.0，状态candidate，生产默认disabled。

## 检测目标

预期gen5/x16为模拟清单值，现场按主机、插槽和GPU配置核定。

## 输入与适用条件

`DCGM_FI_DEV_PCIE_LINK_GEN`、`DCGM_FI_DEV_PCIE_LINK_WIDTH`、`DEMO_EXPECTED_PCIE_GEN`、`DEMO_EXPECTED_PCIE_WIDTH`、`DEMO_JOB_RUNNING`
按候选清单选择GPU、交换机或端口对象。实际硬件形态、字段支持及维护流程待现场核验。

## 触发、分级和解除

- 触发条件为作业运行且代际或宽度低于清单。
- 解除条件为链路达到预期或作业停止。
- 夜莺严重度2为本次工程提案，1/2/3分别对应critical/warning/info。
- 目标持续时间10秒，由持久状态适配器执行。
- 夜莺每5秒评估，原生for=0秒。

## 输入质量与状态

先按实体校验新鲜、唯一及有效值。连续有效触发满足持续时间后置为活动，未知输入使确认重新计时。
已确认异常在缺数、无效或查询失败时保持活动。有效解除证据到达后退出，事件ID保持至解除。
状态与待确认时间保存到独立Docker卷。确认采样间隔超过6秒时重新计时。

## 完整观测表达式

```promql
label_replace(label_replace((((((((DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} and ((time() - timestamp(DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15) and (DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} >= 1) and (DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} < 7) and ((DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} - DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 0) and on (entity_id) (count by (entity_id) (DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 1) and on (job,instance) ((up{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15))) and (DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} == floor(DCGM_FI_DEV_PCIE_LINK_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"}))) < bool on (entity_id) ((DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} and ((time() - timestamp(DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15) and (DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} >= 1) and (DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} < 7) and ((DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} - DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 0) and on (entity_id) (count by (entity_id) (DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 1) and on (job,instance) ((up{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15))) and (DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"} == floor(DEMO_EXPECTED_PCIE_GEN{cluster_id="h100-training-demo",job="h100-comprehensive"})))) + on(entity_id) (((DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} and ((time() - timestamp(DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15) and (DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} >= 1) and (DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} < 33) and ((DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} - DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 0) and on (entity_id) (count by (entity_id) (DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 1) and on (job,instance) ((up{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15))) and (DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} == floor(DCGM_FI_DEV_PCIE_LINK_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"}))) < bool on (entity_id) ((DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} and ((time() - timestamp(DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15) and (DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} >= 1) and (DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} < 33) and ((DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} - DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 0) and on (entity_id) (count by (entity_id) (DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 1) and on (job,instance) ((up{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15))) and (DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"} == floor(DEMO_EXPECTED_PCIE_WIDTH{cluster_id="h100-training-demo",job="h100-comprehensive"}))))) > bool 0) * on(entity_id) ((DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"} and ((time() - timestamp(DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15) and (DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"} >= 0) and (DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"} < 2) and ((DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"} - DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 0) and on (entity_id) (count by (entity_id) (DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"}) == 1) and on (job,instance) ((up{cluster_id="h100-training-demo",job="h100-comprehensive"} == 1) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive"})) <= 15))) and (DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"} == floor(DEMO_JOB_RUNNING{cluster_id="h100-training-demo",job="h100-comprehensive"}))))), "metric_name", "pcie_degraded", "__name__", ".*"), "cluster_id", "h100-training-demo", "__name__", ".*")
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
