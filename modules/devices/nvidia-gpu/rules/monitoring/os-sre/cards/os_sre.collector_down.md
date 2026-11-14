# DCGM采集目标不可用

规则 `os_sre.collector_down`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance`。不依赖集群ID、业务任务、租户或作业状态。
输入：采集目标/监控组件指标或OS资产清单。

## 语义与边界

up=0表示采集失败；配置资产清单后还可检测target被移除，不代表GPU故障。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
(max by (job,instance) (up{job=~"dcgm.*"} == 0)) or ((max by (job,instance) (sre:inventory:gpu_expected or sre:inventory:switch_expected) unless on (job,instance) up{job=~"dcgm.*"}))
```

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | up=0代表抓取失败；target从配置移除后序列可以消失。 |
| 具体来源 | [prometheus.up](https://prometheus.io/docs/concepts/jobs_instances/)；[prometheus.operators](https://prometheus.io/docs/prometheus/latest/querying/operators/) |
| 项目判据 | up=0触发；有OS预期清单时还检测target被移除。 |
| 参数来源 | P10=job/instance + 硬件ID；预期清单默认空；P03=60；P04=30；P09=2 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 这是本项目采集契约，不是NVIDIA官方故障规则；不从空结果推断健康。 |

[查看完整逐条来源表](../provenance.md#os-sre-collector-down)；[结构化来源定义](../provenance.yaml)。
