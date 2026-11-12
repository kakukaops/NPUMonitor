# 夜莺 v9.3.0 源码与自定义模型扩展

## 是否存在内置机器学习与任意推理调用钩子

### Takeaway
官方 v9.3.0 的已核查告警评估路径是数据源查询和表达式判断，不是可上传自训练模型的机器学习平台。源码中的 AnomalyPoint / GetAnomalyPoint 表示告警异常点，不能据此宣称内置机器学习。

### Cited Findings
- `AlertRuleWorker.Eval()` 按类型分发：Prometheus / Loki 使用 `GetPromAnomalyPoint`，Host 使用 `GetHostAnomalyPoint`，其他走 `GetAnomalyPoint`，然后交给 `Processor.Handle`。Prometheus 路径执行 `readerClient.Query(context.Background(), promql, time.Now())`，将返回向量转换为异常点。— [v9.3.0 eval.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/eval/eval.go)
- 通用 `GetAnomalyPoint` 通过 `dscache.DsCache.Get` 获取数据源插件，调用 `plug.QueryData(ctx, query)`，随后根据触发表达式、连接匹配、恢复条件生成异常点。这里的数据源插件调用不是默认向任意 URL 发送时序并执行自定义模型。— [v9.3.0 eval.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/eval/eval.go)
- 本次已核查 `alert/eval`、`alert/aconf`、`dscache`、`dskit` 的相关源文件，没有找到公开的模型上传、Python/ONNX 模型运行、训练任务注册或通用 HTTP 模型推理接口。严格措辞是“未在已核查路径中找到”，不应把有限搜索等同全仓库不存在。— [v9.3.0 告警目录](https://github.com/ccfos/nightingale/tree/v9.3.0/alert)、[v9.3.0 数据源目录](https://github.com/ccfos/nightingale/tree/v9.3.0/dskit)
- 当前官方商业产品称“夜莺智能检测插件”，并明确写可与开源夜莺集成、复用告警处理能力。这是产品支持说明，并未披露其源码协议或确认任何自定义模型 SDK。— [官方智能告警产品](https://flashcat.cloud/product/flashcat-aiops-alert/)

### Inferences
- 用户若拥有自己训练的 IsolationForest / TCN 等模型，最少耦合方式是模型独立运行、输出 Prometheus 指标，再让夜莺以正常 PromQL 规则统一调度与告警。
- 深入修改数据源插件/评估代码在工程上可行，但属于二次开发，不应描述为夜莺已提供即插即用的自定义 ML 插件能力。

### Gaps
- 商业智能检测插件是否支持替换算法、上传权重、私有镜像注册、外部推理 URL、训练接口和授权范围，公开源码不能回答；需要厂商合同/技术文档确认。
- 本次未对最新 main 的全部功能做穷尽源码审计，也未改变用户正在运行的夜莺配置。

## 外部检测结果能否进入夜莺的原生告警流程

### Takeaway
有明确源码接口，但它接收异常/恢复结果或完整告警事件，并不负责训练或运行模型。若要求最少改动，仍优先输出指标；只有需要独立检测引擎直接驱动夜莺事件生命周期时才考虑该接口。

### Cited Findings
- `alert/router/router.go`：仅当 `HTTP.APIForService.Enable` 为 true 才注册 `/v1/n9e` 路由；BasicAuth 配置非空时启用 gin.BasicAuth。注册 `POST /event`、`POST /event-persist`、`POST /make-event`。不是 `/push-event`。— [v9.3.0 router.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/router/router.go)
- `makeEvent` 接收数组 `[]eventForm`，字段为 `alert`、`vectors`（`[]models.AnomalyPoint`）、`rule_id`、`datasource_id`、`inhibit`。按数据源/规则哈希环转发到负责实例；要求 `ExternalProcessors.GetExternalAlertRule(datasource_id, rule_id)` 存在。`alert=true` 调用 `Handle(points, "http", inhibit)`；`alert=false` 按 `process.Hash` 与 `vector.Timestamp` 调用 `RecoverSingle`。— [v9.3.0 router_event.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/router/router_event.go)
- `pushEventToQueue` 接收完整 `AlertCurEvent`，要求非零 RuleId，进行格式转换、屏蔽/模板处理后进入 `EventQueue`。`eventPersist` 只对传入事件转换后调用 `models.EventPersist` 并返回事件 ID；不应把仅持久化接口当成完整的检测/告警状态机入口。— [v9.3.0 router_event.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/router/router_event.go)
- `Scheduler.syncAlertRules()` 为 Prometheus / Inner / Host 规则创建内部评估 worker，其余规则建立 external processor；因此 `/make-event` 不应拿一个普通 Prometheus 规则 ID 即假设会成功，必须有匹配外部规则和数据源。— [v9.3.0 alert_rule.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/eval/alert_rule.go)、[v9.3.0 process.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/process/process.go)

### Inferences
- 这些接口适合自研 detector → 结果适配器 → 夜莺事件处理的路线；适配器需要负责规则/数据源身份、稳定标签、触发/恢复配对、重试幂等、检测停滞和权限。
- 对当前 demo，Prometheus 已采集 `ml_demo_anomaly_score`、`ml_demo_anomaly_threshold`、`ml_demo_alert_active` 和新鲜度，直接增加夜莺 PromQL 告警规则比走外部事件接口更稳妥。
- 普通阈值规则和模型输出规则可以并行；ML 不必成为所有硬阈值规则的前置条件。

### Gaps
- 没有在用户实例启用 APIForService、创建 external rule 或调用写入接口进行实测；以上是源码核查结论。
- 未证明上述外部事件接口就是商业智能检测插件使用的唯一接口，不应作此推断。

## 证据采集与版本限制

### Takeaway
推荐报告以当前已部署 v9.3.0 为落地基线，产品网页用于核查商业功能，明确区分源码事实、工程方案和未证实厂商能力。

### Cited Findings
- 本次通过官方 codeload tag tarball 获取源码，虽然完整压缩包下载超时，但 `alert`、`dscache` 和 `dskit` 目录已解出，可核查上述函数；官方来源 [v9.3.0 tag](https://github.com/ccfos/nightingale/tree/v9.3.0)。临时路径 `/tmp/nightingale-9.3.0`。
- web 工具读取 raw v9.3.0 eval.go 的缓存行数与实时 tag tarball 文件行数有差异，但上述关键分发和结果接入合同一致。报告建议引用 tag 文件路径与函数名，不写死可能不一致的网页行号。

### Inferences
- 切换部署版本后，需要重新对比接口及配置，不能将 main 分支的 AI/LLM 功能直接当成 v9.3.0 自定义时序异常检测能力。

### Gaps
- 未对运行镜像的 build commit 与 tag 源码逐字节核验；镜像标签不能替代 build provenance。
