# 平台-评估调度停滞

规则 `os_sre.platform_evaluation_stall`，版本0.2.0；默认disabled；状态 `candidate`。

## 身份与输入

匹配标签：`job,instance`。不依赖集群ID、业务任务、租户或作业状态。
输入：采集目标/监控组件指标或OS资产清单。

## 语义与边界

组件级聚合，不绑定任何业务任务或夜莺数据库规则ID。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## PromQL

```promql
((((sum by (job,instance) (increase(n9e_alert_rule_eval_total{job=~"nightingale.*"}[300s])) == 0) and on (job,instance) (((sre:inventory:evaluation_expected == 1) and on (job,instance) (min by (job,instance) (count_over_time(n9e_alert_rule_eval_total{job=~"nightingale.*"}[300s])) >= 2))))) and on (job,instance) (max by (job,instance) ((up{job=~"nightingale.*"} == 1) and ((time()-timestamp(up{job=~"nightingale.*"})) >= 0) and ((time()-timestamp(up{job=~"nightingale.*"})) <= 90))))
```

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 夜莺v9.3.0定义CounterRuleEval且无业务标签。 |
| 具体来源 | [nightingale.alert.stats](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)；[prometheus.functions](https://github.com/prometheus/prometheus/blob/v3.2.1/docs/querying/functions.md)；[prometheus.up](https://prometheus.io/docs/concepts/jobs_instances/) |
| 项目判据 | 运维声明预期持续执行、窗口计数样本>=2而eval增量为0时提示停滞。 |
| 参数来源 | P02=300；P10=job/instance + 硬件ID；预期清单默认空；P03=60；P04=30；P09=1；P01=90 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 未配置预期执行不能据无增量判故障；不是官方统一watchdog规则。 |

[查看完整逐条来源表](../provenance.md#os-sre-platform-evaluation-stall)；[结构化来源定义](../provenance.yaml)。
