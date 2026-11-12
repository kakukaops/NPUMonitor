# 指标与规则离线验证

本目录验证规则表达式和边界，全部输入为合成样本；不生成真实硬件故障，不向现有Prometheus写数据，不导入夜莺规则。

新增批次见[H100首批卡片与离线验收](h100_batch1.md)。执行 `bash modules/devices/nvidia-gpu/rules/scripts/test_monitoring.sh` 可一次验证现有五批，共307用例和675项断言（ECC18/31、首批49/392、解除判据12/24、ECC/XID90/90、维护/热/互联138/138）。以下保留原有ECC测试的说明。

## 1. 固定用例格式

[ecc_dbe.promtool.yaml](ecc_dbe.promtool.yaml)使用Prometheus官方promtool用例格式：input_series记录带标签的输入序列、interval记录采样周期、eval_time记录求值点、exp_samples记录期望结果。

每个用例名称稳定，便于定位失败。表达式外层使用 `group by (cluster_id, UUID)`，把命中值归一成1以断言设备身份；内部表达式必须逐字等于catalog/rules.yaml。这样不把increase的外推小数误当作精确错误次数，也不只检查“返回非空”。

用例分层：

| 层级 | 本例证据 | 不能替代的内容 |
| --- | --- | --- |
| 来源核对 | 固定源码/文档说明，目标兼容仍未知 | 不能证明现场字段存在 |
| 表达式固定样本 | promtool 3.2.1，18用例/31断言通过 | 不执行夜莺for、状态机和通知 |
| 夜莺新表达式链路 | not_run | 旧实验规则通过不能继承 |
| 真实硬件/集群 | not_run | 合成输入不能证明型号和Exporter兼容 |

## 2. 用例清单

| 用例 | 输入要点 | 预期 |
| --- | --- | --- |
| normal_zero | 持续为0 | 不命中 |
| historical_nonzero_no_increment | 一直为7 | 不把历史非零当近期新增 |
| new_increment_and_window_exit | 0变1，随后不增长 | 新增时命中，窗口退出后不命中 |
| reset_only | 5降为0 | 不产生新增错误 |
| reset_then_new_error | 5归零后增至1 | 能识别重置后的新增 |
| nan_in_window | 窗口包含NaN后恢复数值 | 阻断硬件判断，不把NaN当计数 |
| positive_infinity_in_window | 窗口含正无穷 | 不命中 |
| negative_infinity_in_window | 窗口含负无穷 | 不命中 |
| negative_count_in_window | 窗口含负计数 | 不命中 |
| int64_blank_in_window | 注入INT64 blank | 不命中 |
| int64_not_supported_in_window | 注入INT64不支持值 | 不命中；不通过float反解错误码 |
| missing_current_stale_marker | 新增后出现stale | 无当前输入时不作新增判断 |
| old_sample_without_stale_marker | 最后样本年龄超90秒 | 即使lookback还能取到旧值也不命中 |
| one_sample_cannot_estimate | 单个非零样本 | 不伪造增量 |
| missing_uuid | 身份标签缺失 | 不进入硬件规则 |
| missing_cluster | 集群标签缺失 | 不进入硬件规则 |
| two_gpu_isolation | 仅第一张卡增长 | 仅命中第一张卡 |
| same_uuid_different_clusters | 同UUID，不同cluster | 不跨集群串联 |

无效、缺失或陈旧用例“不命中”不表示健康，配套数据质量和覆盖判断仍是未完成的发布门禁。

## 3. 复现

在项目根目录执行，使用已有Docker Compose服务定义启动一次性promtool进程：

```bash
docker compose -f deploy/nvidia-gpu/lab/compose.yaml run --rm --no-deps \
  --entrypoint /bin/promtool \
  -v "$PWD/monitoring:/work:ro" \
  prometheus test rules /work/tests/ecc_dbe.promtool.yaml
```

预期输出 `SUCCESS`，退出码0。不停止已有Prometheus，也不重新加载其配置。

## 4. 实际结果

2026-11-06，使用prom/prometheus:v3.2.1执行上述命令，退出码0，输出SUCCESS；18个用例共31个求值断言全部通过。catalog/rules.yaml中的expression_tests记为passed，夜莺和真实集群状态仍为not_run。

这是首份格式审阅样例的结果，不是正式发布批准。式子、参数、guard或身份逻辑变化时必须更新对象版本和用例，不能沿用旧通过结论。


## 夜莺流式验收

[8条实验副本/11个用例通过](h100_batch1-streaming-results.yaml)，包括实际持续时间、旁路抑制和硬件异常后缺数。详见[流式指南](../../docs/08-H100草案流式模拟验证.md)。离线求值、夜莺合成绑定、真实H100分别记证据，不能混用。


## 持久状态实验

新增[解除判据样本](hardware-lifecycle.promtool.yaml)与[离线结果](hardware-lifecycle-promtool-results.yaml)，以及[两条持久规则集成证据](hardware-lifecycle-results.yaml)。复现方法和故障恢复命令见[保持与解除策略](../../docs/09-硬件告警保持与解除策略.md)。25项单元/HTTP测试与79个离线用例为不同层次，不合并为同一覆盖率。

ECC/XID 新增查询及合成验证见[本批结果](ecc-xid-review-results.yaml)。

维护、温度、时钟原因及互联查询的[离线和流式证据](thermal-links-review-results.yaml)已记录。运行 `bash modules/devices/nvidia-gpu/rules/scripts/test_thermal_links_live.sh` 复现独立 Docker Prometheus 的 8 个场景，详见[本批说明](../thermal-links-review.md)。
