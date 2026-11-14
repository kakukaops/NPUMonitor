# 平台-夜莺自监控抓取不可用

规则 `os_sre.platform_nightingale_metrics_missing`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance`。不依赖集群ID、业务任务、租户或作业状态。
输入：采集目标/监控组件指标或OS资产清单。

## 语义与边界

组件级聚合，不绑定任何业务任务或夜莺数据库规则ID。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
(max by (job,instance) (up{job=~"nightingale.*"} == 0)) or (sre:inventory:monitor_expected unless on (job,instance) up{job=~"nightingale.*"})
```

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | Prometheus up及集合运算可识别失败或预期目标缺失。 |
| 具体来源 | [prometheus.up](https://prometheus.io/docs/concepts/jobs_instances/)；[prometheus.operators](https://prometheus.io/docs/prometheus/latest/querying/operators/) |
| 项目判据 | 自监控up=0；有预期监控目标清单时检测target移除。 |
| 参数来源 | P10=job/instance + 硬件ID；预期清单默认空；P03=60；P04=30；P09=1 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 仅在夜莺自身发出的告警不足以证明进程完全退出时可送达；独立外部监控另需验收。 |

[查看完整逐条来源表](../provenance.md#os-sre-platform-nightingale-metrics-missing)；[结构化来源定义](../provenance.yaml)。
