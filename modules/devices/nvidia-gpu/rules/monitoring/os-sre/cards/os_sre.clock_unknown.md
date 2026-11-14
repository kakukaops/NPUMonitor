# 时钟原因存在未核实位

规则 `os_sre.clock_unknown`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_CLOCKS_EVENT_REASONS`。

## 语义与边界

已知热降频位仍独立解码，未知位记录待核实。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
(((max by (job,instance,UUID) ((((DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 9007199254740992) and ((DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) >= bool 512)
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 固定版本原因位定义覆盖0x1至0x100。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h) |
| 项目判据 | 整数位图>=512视为超出本项目已知位集合的待核对信号。 |
| 参数来源 | P12=512；P03=60；P04=30；P09=3；P01=90；P08=按metrics.yaml逐字段约束；P10=job/instance + 硬件ID；预期清单默认空 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 这是版本/解码完整性提示，不是官方硬件故障定义。 |

[查看完整逐条来源表](../provenance.md#os-sre-clock-unknown)；[结构化来源定义](../provenance.yaml)。
