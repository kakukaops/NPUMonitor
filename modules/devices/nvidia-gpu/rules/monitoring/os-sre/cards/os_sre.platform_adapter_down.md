# 平台-状态适配器不可用

规则 `os_sre.platform_adapter_down`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance`。不依赖集群ID、业务任务、租户或作业状态。
输入：采集目标/监控组件指标或OS资产清单。

## 语义与边界

组件级聚合，不绑定任何业务任务或夜莺数据库规则ID。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
max by (job,instance) (up{job=~"gpu-lifecycle.*"} == 0)
```

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | Prometheus up反映所配置目标的抓取成功与否。 |
| 具体来源 | [prometheus.up](https://prometheus.io/docs/concepts/jobs_instances/) |
| 项目判据 | 状态适配器专用采集job的up=0产生告警。 |
| 参数来源 | P03=60；P04=30；P09=1 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 须实际配置该采集目标；本条不证明旧模拟适配器兼容新硬件身份。 |

[查看完整逐条来源表](../provenance.md#os-sre-platform-adapter-down)；[结构化来源定义](../provenance.yaml)。
