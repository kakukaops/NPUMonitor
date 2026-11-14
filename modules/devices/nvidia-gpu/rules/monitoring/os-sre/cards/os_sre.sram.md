# SRAM超阈值标志

规则 `os_sre.sram`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_SRAM_EXCEEDED`。

## 语义与边界

缺数和无效输入保持已确认异常，维护操作由运维复核。
持续确认：0秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
((max by (job,instance,UUID) ((((DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 2) and ((DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_SRAM_EXCEEDED{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90))))
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 字段346定义threshold-exceeded布尔标志；SRAM管理文档说明诊断/RMA边界。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.memory.sram](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/sram-uncorrectable-errors.html) |
| 项目判据 | 有效标志1触发、0提供解除观测；不以DBE总量直接决定换卡。 |
| 参数来源 | P03=0；P04=30；P09=1；P01=90；P08=按metrics.yaml逐字段约束；P10=job/instance + 硬件ID；预期清单默认空 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 标志的目标设备清除行为未验证；触发不等于直接满足RMA。 |

[查看完整逐条来源表](../provenance.md#os-sre-sram)；[结构化来源定义](../provenance.yaml)。
