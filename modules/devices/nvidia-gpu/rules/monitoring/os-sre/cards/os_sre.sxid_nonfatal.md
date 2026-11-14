# NVSwitch nonfatal SXid待复核

规则 `os_sre.sxid_nonfatal`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,switch_id`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS`、`os_sre_recovery_verified`。

## 语义与边界

最近错误码不是有序事件流；无恢复证据时事件保持。
持续确认：0秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

- NVSwitch真实switch_id及运维恢复确认

## PromQL

```promql
((((max by (job,instance,switch_id) ((((DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""} >= 0) and (DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""} < 9223372036854775792) and ((DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}-DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""})) <= 90) and (DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""} == floor(DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}))) and on (job,instance,switch_id) (count by (job,instance,switch_id) (DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) > 0) * 0 + 1) or (((((max by (job,instance,switch_id) ((((DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""} >= 0) and (DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""} < 9223372036854775792) and ((DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}-DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""})) <= 90) and (DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""} == floor(DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}))) and on (job,instance,switch_id) (count by (job,instance,switch_id) (DCGM_FI_DEV_NVSWITCH_NON_FATAL_ERRORS{job=~"dcgm.*",switch_id!=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == 0) * 0) and on (job,instance,switch_id) (((max by (job,instance,switch_id) ((((os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""} >= 0) and (os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""} < 2) and ((os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""}-os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""}) == 0) and ((time()-timestamp(os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""})) >= 0) and ((time()-timestamp(os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""})) <= 90) and (os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""} == floor(os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""}))) and on (job,instance,switch_id) (count by (job,instance,switch_id) (os_sre_recovery_verified{job=~"dcgm.*",switch_id!=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == 1))
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | SXid nonfatal通道字段及switch实体语义。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.nvswitch](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/nvswitch.html) |
| 项目判据 | 通道非零产生1观测；0且对应switch运维恢复确认=1才给0。 |
| 参数来源 | P11=错误码0且os_sre_recovery_verified=1；P03=0；P04=30；P09=2；P01=90；P08=按metrics.yaml逐字段约束；P10=job/instance + 硬件ID；预期清单默认空 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 通道值不是错误次数；具体SXid码、RMA和字段清零语义另需排障。 |

[查看完整逐条来源表](../provenance.md#os-sre-sxid-nonfatal)；[结构化来源定义](../provenance.yaml)。
