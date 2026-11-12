# H100平台-主通知投递失败

rule_id `platform_notify_failure`，版本0.1.0，状态candidate，生产默认disabled。

## 条件与数据源

实际Night POST失败记录的累计计数，备用独立本地接收通道发送，窗口退出表示近期无失败。

目标持续时间0秒，夜莺每5秒评估，原生for=0秒，严重度1。
观测故障条件退出后解除。规则通过独立本地备用通知通道发送。

```promql
increase(DEMO_NOTIFY_FAILURES_TOTAL{job="h100-comprehensive"}[30s]) > 0
```

## 处置

核对原始错误、评估计数和通知尝试，修复组件或配置后验证实际成功记录。
看门狗在独立演示服务中记录组件不可达，Prometheus或夜莺停止时页面仍显示独立可用性记录。

## 验收

查询失败采用真实HTTP503，评估停滞采用探针调度间隔异常，通知失败采用实际Webhook503并核验备用通道。
本次为模拟环境参数。完整原始记录和规则ID绑定保存在验收报告。

## 来源

[固定夜莺自监控定义](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)
