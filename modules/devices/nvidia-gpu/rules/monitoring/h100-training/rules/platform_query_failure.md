# H100平台-查询或评估失败

rule_id `platform_query_failure`，版本0.1.0，状态candidate，生产默认disabled。

## 条件与数据源

实际夜莺评估结果为负值，保存rule_id及原始错误。备用通道发送。

目标持续时间5秒，夜莺每5秒评估，原生for=10秒，严重度1。
观测故障条件退出后解除。规则通过独立本地备用通知通道发送。

```promql
(n9e_alert_eval_query_series_count{job="nightingale-self",rule_id=~"18|19|20|21|22|23|24|25|26|27|28|29|30|31|32|33|34|35|36|37|38|39|40|41|42|43|44|45|46|47|48|49|50|51|52|53|54|55|56|57|58"} < 0) and on(job,instance) (up{job="nightingale-self"} == 1) and on() (DEMO_ADAPTER_UP{job="h100-comprehensive"} == 1)
```

## 处置

核对原始错误、评估计数和通知尝试，修复组件或配置后验证实际成功记录。
看门狗在独立演示服务中记录组件不可达，Prometheus或夜莺停止时页面仍显示独立可用性记录。

## 验收

查询失败采用真实HTTP503，评估停滞采用探针调度间隔异常，通知失败采用实际Webhook503并核验备用通道。
本次为模拟环境参数。完整原始记录和规则ID绑定保存在验收报告。

## 来源

[固定夜莺自监控定义](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)
