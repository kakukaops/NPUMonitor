# H100平台-评估调度停滞

rule_id `platform_evaluation_stall`，版本0.1.0，状态candidate，生产默认disabled。

## 条件与数据源

固定5秒调度的探针在20秒窗口无新查询尝试。故障演练将探针周期改为3600秒，恢复时回到5秒。

目标持续时间5秒，夜莺每5秒评估，原生for=10秒，严重度1。
观测故障条件退出后解除。规则通过独立本地备用通知通道发送。

```promql
((increase(n9e_alert_query_data_total{job="nightingale-self",rule_id="18"}[20s]) == 0) and (count_over_time(n9e_alert_query_data_total{job="nightingale-self",rule_id="18"}[20s]) >= 2)) and on(job,instance) (up{job="nightingale-self"} == 1)
```

## 处置

核对原始错误、评估计数和通知尝试，修复组件或配置后验证实际成功记录。
看门狗在独立演示服务中记录组件不可达，Prometheus或夜莺停止时页面仍显示独立可用性记录。

## 验收

查询失败采用真实HTTP503，评估停滞采用探针调度间隔异常，通知失败采用实际Webhook503并核验备用通道。
本次为模拟环境参数。完整原始记录和规则ID绑定保存在验收报告。

## 来源

[固定夜莺自监控定义](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/astats/stats.go)
