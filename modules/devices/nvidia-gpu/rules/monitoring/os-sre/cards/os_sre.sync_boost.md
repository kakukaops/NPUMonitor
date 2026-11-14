# 同步boost限制状态

规则 `os_sre.sync_boost`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_CLOCKS_EVENT_REASONS`。

## 语义与边界

仅表示设备原因位；不使用作业上下文，不推断吞吐或性能故障。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
(floor(((max by (job,instance,UUID) ((((DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 9007199254740992) and ((DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) / 16) % 2)
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | DCGM_CLOCKS_EVENT_REASON_*中0x10的同步boost限制含义。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.smi](https://docs.nvidia.com/deploy/nvidia-smi/index.html) |
| 项目判据 | 解码0x10原因位；置位/清零形成1/0观测。 |
| 参数来源 | P03=60；P04=30；P09=3；P01=90；P08=按metrics.yaml逐字段约束；P10=job/instance + 硬件ID；预期清单默认空 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 不从原因位直接推断吞吐下降或硬件损坏；power_cap保持信息级。 |

[查看完整逐条来源表](../provenance.md#os-sre-sync-boost)；[结构化来源定义](../provenance.yaml)。
