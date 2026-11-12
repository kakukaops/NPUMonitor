# H100平台-夜莺自监控抓取不可用

rule_id `platform_nightingale_metrics_missing`，版本0.1.0，状态candidate，生产默认disabled。

## 条件与数据源

外部演示看门狗另记录组件不可达，夜莺进程停止时通过独立页面观察。

目标持续时间5秒，夜莺每5秒评估，原生for=10秒，严重度1。
观测故障条件退出后解除。规则通过独立本地备用通知通道发送。

```promql
up{job="nightingale-self"} == 0
```

## 处置

核对原始错误、评估计数和通知尝试，修复组件或配置后验证实际成功记录。
看门狗在独立演示服务中记录组件不可达，Prometheus或夜莺停止时页面仍显示独立可用性记录。

## 验收

查询失败采用真实HTTP503，评估停滞采用探针调度间隔异常，通知失败采用实际Webhook503并核验备用通道。
本次为模拟环境参数。完整原始记录和规则ID绑定保存在验收报告。

## 来源

[固定夜莺自监控定义](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)
