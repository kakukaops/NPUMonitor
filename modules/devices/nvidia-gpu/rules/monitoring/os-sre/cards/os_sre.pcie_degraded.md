# 持续PCIe传输时链路低于资产预期

规则 `os_sre.pcie_degraded`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance,UUID`。不依赖集群ID、业务任务、租户或作业状态。
输入：`DCGM_FI_DEV_PCIE_LINK_GEN`、`DCGM_FI_DEV_PCIE_LINK_WIDTH`、`DCGM_FI_PROF_PCIE_TX_BYTES`、`DCGM_FI_PROF_PCIE_RX_BYTES`。

## 语义与边界

只在可测PCIe传输期间判断；空闲/传输字段缺失不给故障或恢复结论。不把GPU利用率当PCIe负载，不对已有速率再次rate。
持续确认：120秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

- 每卡OS资产预期gen/width及实测活动字节速率门槛
- Profiling PCIe TX/RX字段已确认是bytes/s的gauge

## PromQL

```promql
(((((((max by (job,instance,UUID) ((((DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 1) and (DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 7) and ((DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_PCIE_LINK_GEN{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) < bool on (job,instance,UUID) sre:inventory:pcie_gen) + on (job,instance,UUID) (((max by (job,instance,UUID) ((((DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 1) and (DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 33) and ((DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90) and (DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} == floor(DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}))) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_DEV_PCIE_LINK_WIDTH{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) < bool on (job,instance,UUID) sre:inventory:pcie_width)) > bool 0)) and on (job,instance,UUID) (((((max by (job,instance,UUID) ((((DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 140737488355328) and ((DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90)) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_PROF_PCIE_TX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90)))) + on (job,instance,UUID) ((max by (job,instance,UUID) ((((DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} >= 0) and (DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""} < 140737488355328) and ((DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}-DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 0) and ((time()-timestamp(DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) >= 0) and ((time()-timestamp(DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""})) <= 90)) and on (job,instance,UUID) (count by (job,instance,UUID) (DCGM_FI_PROF_PCIE_RX_BYTES{job=~"dcgm.*",UUID!="",GPU_I_ID="",GPU_I_PROFILE=""}) == 1)))) and on (job,instance) (max by (job,instance) ((up{job=~"dcgm.*"} == 1) and ((time()-timestamp(up{job=~"dcgm.*"})) >= 0) and ((time()-timestamp(up{job=~"dcgm.*"})) <= 90))))) > on (job,instance,UUID) sre:inventory:pcie_active_bps)))
```

输出0/1为有效观测，空结果表示未知。必须由持久状态处理持续确认、缺数保持和恢复；不能把非空的0直接作为原生告警。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 字段237/238表示当前链路代际/宽度；Exporter把1009/1010声明为bytes/s gauge。 |
| 具体来源 | [nvidia.dcgm.fixed_fields](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[nvidia.exporter.counters](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[nvidia.profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)；[nvidia.topology](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/topology-and-links.html) |
| 项目判据 | 实测TX+RX超过每卡OS活动门槛且链路低于静态预期，才形成异常观测。 |
| 参数来源 | P06=120；P07=逐卡配置；默认无值；P10=job/instance + 硬件ID；预期清单默认空；P03=120；P04=30；P09=2；P01=90；P08=按metrics.yaml逐字段约束 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 不使用作业状态；不以GPU利用率代替PCIe活动，不对gauge再次rate。静态预期和门槛没有官方统一默认值。 |

[查看完整逐条来源表](../provenance.md#os-sre-pcie-degraded)；[结构化来源定义](../provenance.yaml)。
