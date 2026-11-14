# fabric不健康或容量受限

规则 `os_sre.fabric_health`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY`。

## 语义与边界

summary=0保留覆盖缺口，需确认实际需要fabric。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

- OS资产声明该设备需要fabric；不由训练作业判断

## PromQL

```promql
(((((((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 4) and ((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90))))) * 0 + 1) and (((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 4) and ((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) >= 2)) or (((((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 4) and ((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90))))) * 0) and (((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 4) and ((DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == 1))) and on (job,instance,UUID) (sre:inventory:fabric_expected == 1))
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 字段175定义0不支持、1健康、2不健康、3容量受限。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.nvswitch](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/nvswitch.html) |
| 项目判据 | 仅预期需要fabric时，2/3异常、1解除；0无健康结论。 |
| 参数来源 | P10=job/instance + 硬件ID；预期清单默认空；P03=60；P04=30；P09=2；P01=90；P08=按metrics.yaml逐字段约束 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 预期清单和通知优先级需按现场fabric用途审定。 |

[查看完整逐条来源表](../provenance.md#os-sre-fabric-health)；[结构化来源定义](../provenance.yaml)。
