# 平台-主通知投递失败

规则 `os_sre.platform_notify_failure`，版本0.2.0；默认disabled；状态 `blocked_missing_input`。

## 身份与输入

匹配标签：`job,instance`。不依赖集群ID、业务任务、租户或作业状态。
输入：采集目标/监控组件指标或OS资产清单。

## 语义与边界

v9.3.0源码定义了通知错误counter，但现场采集、调用范围及真实失败增量尚未核对；保持输入接入阻塞，不把DEMO计数或队列长度冒充投递结果。
持续确认：60秒（工程配置）；真实硬件与夜莺新版本接入尚未验收。

## 来源与参数依据

| 项目 | 内容 |
|---|---|
| 官方语义 | 夜莺源码定义并注册AlertNotifyErrorTotal（channel标签）；不能从运行中暂未出现序列断言源码无指标。 |
| 具体来源 | [nightingale.alert.stats](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go) |
| 项目判据 | 当前仍无执行表达式；等待真实计数器调用点、现场采集和失败注入核对后接入。 |
| 参数来源 | P03=60；P04=30；P09=1 |
| 证据边界 | 合成向量求值；不包括新版持续确认/夜莺/真实设备/生产案例；生产案例无；真实硬件未验 |
| 待核实项 | 应更正此前只看到队列指标的表述。候选名称n9e_alert_alert_notify_error_total；队列长度不能替代投递结果。 |

[查看完整逐条来源表](../provenance.md#os-sre-platform-notify-failure)；[结构化来源定义](../provenance.yaml)。
