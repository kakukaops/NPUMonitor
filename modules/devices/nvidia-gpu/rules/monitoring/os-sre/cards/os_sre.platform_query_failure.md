# 平台-查询或评估失败

规则 `os_sre.platform_query_failure`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance`。不依赖集群ID、业务任务、租户或作业状态。
输入：采集目标/监控组件指标或OS资产清单。

## 语义与边界

组件级聚合，不绑定任何业务任务或夜莺数据库规则ID。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
((sum by (job,instance) (increase(n9e_alert_query_data_error_total{job=~"nightingale.*"}[300s])) > 0) and on (job,instance) (max by (job,instance) ((up{job=~"nightingale.*"} == 1) and ((time()-timestamp(up{job=~"nightingale.*"})) >= 0) and ((time()-timestamp(up{job=~"nightingale.*"})) <= 90))))
```

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 夜莺v9.3.0定义CounterQueryDataErrorTotal，标签为datasource。 |
| 具体来源 | [nightingale.alert.stats](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)；[prometheus.functions](https://github.com/prometheus/prometheus/blob/v3.2.1/docs/querying/functions.md)；[prometheus.up](https://prometheus.io/docs/concepts/jobs_instances/) |
| 项目判据 | 按job/instance聚合配置窗口内查询错误增量>0，并校验自监控抓取。 |
| 参数来源 | P02=300；P03=60；P04=30；P09=1；P01=90 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 组件级查询失败不能直接定位具体GPU；窗口/通知持续时间为工程选择。 |

[查看完整逐条来源表](../provenance.md#os-sre-platform-query-failure)；[结构化来源定义](../provenance.yaml)。
