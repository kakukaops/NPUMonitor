# 预期GPU NVLink端口未连接

规则 `os_sre.gpu_link_down`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID,link_id`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_NVLINK_GET_STATE`。

## 语义与边界

仅配置清单中预期启用的端口参与，GPU与交换机枚举独立。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

- OS维护的预期启用端口清单；无清单则不判断掉链

## PromQL

```promql
(((((((max by (job,instance,UUID,link_id) ((((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} < 3) and ((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID,link_id) (count by (job,instance,UUID,link_id) (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90))))) * 0 + 1) and (((max by (job,instance,UUID,link_id) ((((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} < 3) and ((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID,link_id) (count by (job,instance,UUID,link_id) (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) == 0)) or (((((max by (job,instance,UUID,link_id) ((((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} < 3) and ((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID,link_id) (count by (job,instance,UUID,link_id) (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90))))) * 0) and (((max by (job,instance,UUID,link_id) ((((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} < 3) and ((DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID,link_id) (count by (job,instance,UUID,link_id) (DCGM_FI_DEV_NVLINK_GET_STATE{job=~"dcgm.*",UUID!="",link_id!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) > 0))) and on (job,instance,UUID,link_id) (sre:inventory:gpu_link_expected == 1))
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | DCGM字段1508采用LINK实体并引用NVML字段返回值；NVLink状态不决定端口是否应启用。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.nvml.fields](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlFieldValueEnums.html)；[nvidia.topology](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/topology-and-links.html) |
| 项目判据 | 仅预期启用端口参与；当前实现0为异常、正数为解除观测。 |
| 参数来源 | P10=job/instance + 硬件ID；预期清单默认空；P03=60；P04=30；P09=2；P01=90；P08=按metrics.yaml逐字段约束 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 不同NVML/DCGM版本枚举不能混用；0/正数判定尚须与现场版本逐值核对。 |

[查看完整逐条来源表](../provenance.md#os-sre-gpu-link-down)；[结构化来源定义](../provenance.yaml)。
