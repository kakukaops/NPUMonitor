# 在现有夜莺 v9.3.0 上实现规则与自定义机器学习

## 哪种集成方式最适合当前系统

### Takeaway
建议继续使用当前开源夜莺作为告警与可视化平台，独立模型 Worker 负责训练与推理，把结果输出成 Prometheus 指标；在夜莺中用普通 Prometheus 告警规则消费模型结果。它不要求夜莺具备上传模型的功能，也不要求修改夜莺源码，是基于已验证原生查询能力的架构推论。

### Cited Findings
- 官方告警原理说明：夜莺按规则频率调用 Prometheus `/api/v1/query`；查询返回的记录经过持续时长判断后形成事件，事件先入库，再进入通知规则。PromQL 本身包含阈值条件。— [官方告警原理](https://flashcat.cloud/docs/content/flashcat-monitor/nightingale-v9/usecase/alerting/)
- PromQL 支持 `and`、`or`、`unless`，并可用 `on(...)` 指定标签匹配；因此机器学习结果与原始指标可在普通规则中组合。注意 `and` 依据序列存在性而不是样本是否非零，必须先比较筛选，如 `ml_ready == 1`。— [Prometheus operators](https://prometheus.io/docs/prometheus/latest/querying/operators/)
- 现有 demo 已实现：真实 Prometheus 抓取 `/metrics` 模拟输入；Worker 从 Prometheus `query_range` 读取样本、推理，再输出 `ml_demo_anomaly_score`、`ml_demo_anomaly_threshold`、`ml_demo_alert_active`、`ml_demo_last_success_timestamp_seconds`，由同一个 Prometheus 抓取。现有页面是独立 Web demo，并未在夜莺中创建 ML 告警规则。— [本地代码](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/demo/app.py)；[说明](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/demo/README.md)；[采集配置](/home/mqq/github/zj/NPUMonitor/deploy/nvidia-gpu/lab/prometheus/prometheus.yml)
- 本地验收记录显示四类注入与恢复通过，派生输出有 3 个服务序列，5 项单测通过；尚未浏览器视觉验收，也没有夜莺 ML 告警生命周期验收。— [验收记录](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/evidence/anomaly/acceptance.json)
- 本地已有 v9.3.0 管理适配代码展示配置 Prometheus 数据源、普通规则、通知规则及活跃/历史事件查询；这证明项目已具备把 ML 指标接入相同配置路径的实施基础，但本次调研不执行写入。— [本地 n9e 管理适配器](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/rules/lab/n9e.py)

### Inferences
- 推荐目标链路：Prometheus 原始指标 → 自定义 ML Worker → Prometheus 模型分数/基线/阈值/健康指标 → 夜莺普通 PromQL 规则 → 夜莺活跃/历史告警、屏蔽、订阅和通知。原始指标的固定规则仍独立运行。
- 最少需新增夜莺 ML 规则、模型健康规则及仪表盘；无需重写事件通知平台。模型选择、训练、模型注册/版本、灰度、回滚仍由外部服务负责。
- 三种规则模式：①硬规则独立告警，ML 不阻断；②ML 自身异常形成低级别候选告警；③对指定场景使用“软阈值 AND 新鲜的 ML 异常”降低噪音。不要把全站 Critical 告警统一改为必须模型确认。
- 当前 demo 可以直接在夜莺 Prometheus 数据源中查询：

```promql
(ml_demo_alert_active{job="ml-anomaly-demo"} == 1)
and on(job,instance,service)
(time() - ml_demo_last_success_timestamp_seconds{job="ml-anomaly-demo"} < 10)
```

这里 10 秒和现有 demo 两秒抓取/检测频率相关；生产需按实际采样、推理与数据延迟调整。模型已有 3/5 状态机，夜莺持续时长再加长会叠加检测延迟，应明确由哪一层控制。
- 若使用分数而非模型状态，可使用 `(ml_score > ml_threshold) and ...freshness...`，但先保证两侧 labelset 一致且每个实体唯一。多实例指标与服务级分数连接前先确定聚合与匹配键。
- 把预测基线、上下界也输出成指标后，可在夜莺仪表盘叠加实际曲线；不能因此说夜莺原生具备自定义模型训练 UI。现有 demo 目前没有导出基线上下界 gauge，只通过 `/api/state` 返回给独立页面，此项需实现。

### Gaps
- 当前 demo 的推理输入仅为 `ml_demo_*`，训练为独立健康模拟数据，不能直接称为真实业务模型平台。接真实指标需配置查询、Counter/Histogram 处理、实体对齐、周期特征与历史回放。
- 夜莺中真实模型告警触发、恢复、重复通知、进程中断时生命周期，仍需专门验收；现有 demo 的事件表不是夜莺告警表。

## 是否也能直接推送模型事件或使用自定义数据源

### Takeaway
v9.3.0 确有受 APIForService 配置控制的内部事件接口，但不应把它当成无需契约适配的通用 ML 插件接口。当前推荐指标路线；直接事件推送适合已有成熟外部事件状态机的场景。

### Cited Findings
- v9.3.0 官方路由：`HTTP.APIForService.Enable` 为 false 时不注册；前缀 `/v1/n9e`；可配置 BasicAuth；注册 POST `/event`、`/event-persist`、`/make-event`。因此当前准确路径不是某些二手资料所写 `/v1/n9e/push-event`。— [v9.3.0 router.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/router/router.go)；[同一文件 raw](https://raw.githubusercontent.com/ccfos/nightingale/v9.3.0/alert/router/router.go)
- v9.3.0 官方配置默认 `[HTTP.APIForService] Enable = false`，并有对应 BasicAuth 配置；当前项目配置同样关闭此入口。— [官方配置](https://github.com/ccfos/nightingale/blob/v9.3.0/etc/config.toml)；[本地配置](/home/mqq/github/zj/NPUMonitor/deploy/nvidia-gpu/lab/nightingale/config.toml)
- v9.3.0 handler 已通过官方 tag 下载的本地源码核实：`/event` 接受完整 `AlertCurEvent`，要求 RuleId 非零，经屏蔽和模板处理后入队；`/event-persist` 执行事件持久化；`/make-event` 接受含 alert/vectors/rule_id/datasource_id/inhibit 的数组，依赖 ExternalProcessors 中已存在的规则 worker，分别调用 Handle 或 RecoverSingle。它们消费检测结果，不训练或运行模型。— [v9.3.0 router_event.go](https://github.com/ccfos/nightingale/blob/v9.3.0/alert/router/router_event.go)；[已下载的同一源码](/tmp/nightingale-9.3.0/alert/router/router_event.go)
- 官方文档明确，通知规则里的回调、event update、event drop、AI summary 在告警事件已生成并持久化后执行。这是后处理扩展，不是对所有原始时序数据进行模型检测的入口。— [官方告警流程](https://flashcat.cloud/docs/content/flashcat-monitor/nightingale-v9/usecase/alerting/)

### Inferences
- 使用内部事件接口意味着外部模型服务还需负责构造正确事件内容、稳定事件身份、异常/恢复时序、幂等重试及与夜莺通知规则关联；在未完整验证契约前，不推荐替换当前指标路径。
- 可以自行实现 Prometheus 查询协议适配器，把外部算法返回包装为夜莺理解的 `/api/v1/query` 结果；这属于自建协议适配，不是“夜莺可直接调用任意自定义 REST 模型”。相比先把模型结果存回 Prometheus，它还需解决历史曲线、协议兼容、延迟和错误语义等问题，当前收益有限。
- 不应把通知 Webhook、AI 事件摘要、Ibex 自愈脚本、管理 API 等扩展点称为“支持上传 sklearn/PyTorch 自定义模型”。

### Gaps
- 已核实事件 handler 的主要契约，但没有在现有系统启用接口或执行事件推送试验；最终报告应列为“存在接口、需工程适配”，不等同于已经完成自定义模型接入。

## 商业插件与自行接入如何选择以及生产约束

### Takeaway
官方有独立“夜莺智能检测插件”，公开说明可与开源夜莺集成，因此不能简单表述为必须升级完整专业版才有 ML。若用户的重点是自定义模型及长期自主维护，指标结果接入仍是可控路线；商业插件是否允许 BYO 模型没有在该产品页面被证实。

### Cited Findings
- 官方独立产品页描述时序智能检测、趋势拟合、输入指标配置、训练效果反馈，且明确可以与开源夜莺集成；页内有商业订购入口。不能把此产品的存在写成开源仓库附带完整模型平台。— [官方智能检测插件](https://flashcat.cloud/product/flashcat-aiops-alert/)
- Prometheus 官方建议导出最后处理时间戳，用 `time() - timestamp_metric` 检测停滞；每个 labelset 都有额外时序存储和资源开销，应控制标签基数。— [Instrumentation](https://prometheus.io/docs/practices/instrumentation/)
- 夜莺官方说明规则持续期间某次查询无结果，会从候选缓存移除；事件生成与后续通知分层处理。— [官方告警原理](https://flashcat.cloud/docs/content/flashcat-monitor/nightingale-v9/usecase/alerting/)

### Inferences
- 外部 ML 至少输出：异常分数、阈值、当前模型状态、数据质量、最后成功推理的源样本时间，以及有限且稳定的模型信息。主要标签选 cluster/service/entity/detector；不要把分数、自由文本原因、事件时间或每次训练 UUID 当普通高基数标签。复杂解释存事件注释或外部详情页。
- 同时配置模型服务 down、推理时间过期、原始输入无数据/采集失败三个独立平台告警。新鲜度过滤可防止旧异常分数继续触发，但“无数据”不等于“业务恢复”，还需验证夜莺无数据与恢复配置，避免界面误导为健康恢复。
- 模型输出版本切换要避免改变事件身份导致重复告警；历史分数、历史阈值、基线应保留版本出处。正式数据集需要按时间切分、真实故障反馈、离线回放、影子运行、灰度和回滚。
- 购买插件的重点确认项：兼容夜莺 9.3.0 的具体插件版本、算法清单、是否有正式自定义算法 SDK/HTTP 协议、能否加载自有权重、训练/推理资源与离线部署要求、升级契约。页面“算法优化支持”不能代替 BYO 模型承诺。

### Gaps
- 商业插件具体 SDK、模型格式、训练 API、第三方模型许可、兼容矩阵需官方进一步提供；当前公开页不足以保证。
- 插件页面的准确率宣传不应作为用户数据效果承诺，仍需同一历史回放集测试。
