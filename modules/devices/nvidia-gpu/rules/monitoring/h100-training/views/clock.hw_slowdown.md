# clock.hw_slowdown

版本0.1.0，候选只读视图，H100物理训练场景。

## 查询与参数

身份绑定为演示集群和两张模拟GPU，生产部署需替换为核实后的目标。
原始样本有效性、新鲜度及采集健康约束见表达式。趋势窗口为5分钟；只有至少两个有效样本才计算增长。

```promql
((floor((((DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"} and ((time() - timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"})) >= 0) and ((time() - timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"})) <= 90)) and on (cluster_id,UUID) (count by (cluster_id,UUID) ((DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"} and ((time() - timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"})) >= 0) and ((time() - timestamp(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"})) <= 90))) == 1) and on (cluster_id,job,instance) ((up{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430"} and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430"})) >= 0) and ((time() - timestamp(up{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430"})) <= 90)) == 1) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"} >= 0) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"} < 9223372036854775792) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"} == floor(DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"}))) and (DCGM_FI_DEV_CLOCKS_EVENT_REASONS{cluster_id="h100-training-demo",job="h100-comprehensive",instance="comprehensive-source:9430",UUID=~"GPU-DEMO-000[01]"} < 9007199254740992)) / 8) % 2) == 1)
```

## 解释与处置

历史计数非零不自动等同近期故障；纠正ECC趋势和分域数据用于定位与复核。
码值视图用于事件分流，需结合节点日志及恢复动作。禁止通过这些查询自动重启、隔离或执行诊断。
无结果可能表示无匹配活动或输入不可判定，先核对设备清单、字段及采集质量。

## 验证与来源

ECC/XID和温度互联查询已有固定样本测试；综合演示可查询 /api/views 查看实际Prometheus求值结果。
真实H100字段支持待现场验收。

[固定DCGM字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h) · [覆盖矩阵](../../coverage.md)
