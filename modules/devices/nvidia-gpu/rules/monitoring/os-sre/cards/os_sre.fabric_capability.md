# 预期fabric能力或版本缺口

规则 `os_sre.fabric_capability`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_FABRIC_MANAGER_STATUS`。

## 语义与边界

按采集和版本能力处理。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

- OS资产声明该设备需要fabric；不由训练作业判断

## PromQL

```promql
(((((((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 7) and ((DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == bool 0)+(((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 7) and ((DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == bool 5)+(((max by (job,instance,UUID) ((((DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 7) and ((DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_FABRIC_MANAGER_STATUS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == bool 6)) > bool 0)) and on (job,instance,UUID) (sre:inventory:fabric_expected == 1))
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | FM状态枚举0/5/6对应不支持、未识别或NVML过旧。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.dcgm.enums](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_structs.h) |
| 项目判据 | 预期需要fabric时，0/5/6报能力缺口；已识别状态给解除观测。 |
| 参数来源 | P10=job/instance + 硬件ID；预期清单默认空；P03=60；P04=30；P09=2；P01=90；P08=按metrics.yaml逐字段约束 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 这是能力/版本检查，不能与fabric硬件故障混为一谈。 |

[查看完整逐条来源表](../provenance.md#os-sre-fabric-capability)；[结构化来源定义](../provenance.yaml)。
