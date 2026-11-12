# 独立告警执行器及 HertzBeat 调研

调研日期：2026-11-05。均为文档或源码核实，未做实际部署验证。下列推荐是基于需求的工程推断；不是产品已通过验收的声明。

## 哪些执行器能直接查询已有 Prometheus，且支持规则管理？

### Takeaway
vmalert 最贴近独立查询执行器，但缺少完整规则写入管理面；Thanos Ruler 也依赖规则文件。它们可以作为内部组件，但不能裸部署就满足“内置 GPU 能力、在线规则 CRUD”的完整产品要求。

### Cited Findings
- vmalert 使用配置的数据源执行规则，支持 Prometheus HTTP 查询 API；告警发往 Alertmanager。规则来源包含本地文件和 HTTP URL。 — [vmalert 官方文档](https://docs.victoriametrics.com/victoriametrics/vmalert/)
- vmalert 支持信号、HTTP reload、定时检查配置；错误配置保留上一有效配置。规则 API 用于读取当前规则，不应当作写入 API。 — [配置及 Web API](https://docs.victoriametrics.com/vmalert/index.html)
- 官方 Grafana 集成指南明确比较：vmalert 的规则保存在 YAML 中，其 Grafana 数据源托管规则界面为 view-only；Grafana 托管规则才有完整创建编辑功能。 — [官方集成指南](https://docs.victoriametrics.com/guides/vmalert-datasource-managed-alerts-grafana/)
- Thanos Ruler 对外部 Query API 执行规则，配置使用 `--rule-file`；改文件后需 SIGHUP 或 POST reload。具有本地 TSDB 和无状态 remote-write 模式，以及 HA 配置。官方同时提醒远程查询可靠性风险，并不推荐用 Ruler 绕过规则配置管理问题。 — [Thanos Ruler 官方文档](https://thanos.io/tip/components/rule.md/)
- Prometheus 告警规则需在自身规则配置中定义，支持 `for` 与 `keep_firing_for`；其 HTTP rules API 返回已加载规则。 — [告警规则](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)；[HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- Prometheus 支持 remote_read，可在查询时透明访问远端时序数据，但配置方式属于 remote-read 存储接入，并非 vmalert 那种直接向远端提交完整 PromQL 的执行器接口。 — [配置](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)；[术语](https://prometheus.io/docs/introduction/glossary/)
- Alertmanager 负责接收告警、去重、分组、路由、静默和抑制；不承担指标查询与规则判断。 — [官方职责说明](https://prometheus.io/docs/alerting/latest/alertmanager/)
- VictoriaMetrics 开源源码与 Thanos 均为 Apache-2.0；VictoriaMetrics 企业功能需单独区分，不能以仓库开源推断全部发行功能免费。 — [VM LICENSE](https://github.com/VictoriaMetrics/VictoriaMetrics/blob/master/LICENSE)；[Thanos LICENSE](https://github.com/thanos-io/thanos/blob/main/LICENSE)；[VM 官方仓库](https://github.com/VictoriaMetrics/VictoriaMetrics)

### Inferences
- 不推荐另起一套 Prometheus 再采集 DCGM：重复采集和存储偏离用户已有基础设施。已有 Prometheus 只需开放受控的查询访问。
- 可以包装 vmalert，但必须补规则数据库、UI/API、版本和审计、内置规则初始化、配置生成与加载确认。这时内部生成 YAML 是实现细节，不能暴露为用户必需的规则包导入操作。
- 推荐通过进程/HTTP 边界复用执行器，不默认直接 import 它的 Go 内部包；调查未证明有长期稳定的嵌入 SDK。
- Thanos 已部署的环境可以再评估 Ruler；为几套独立 GPU 集群新引入 Thanos 全套体系缺乏必要性。

### Gaps
- 未对固定版本容器启动、API 兼容性、规则更新状态继承和高负载查询做实测。
- 未找到这些原生执行器具备用户所需“GPU 内置规则自动生效 + CRUD + 用户覆盖保护 + 审计”的完整一体能力的官方证据。

## 重启状态与可靠性有什么需要设计的边界？

### Takeaway
不能因现成引擎有状态恢复就承诺无缝重启。vmalert 的恢复依赖额外可写存储，不符合“只读访问已有 Prometheus”时必须由产品自行配套，而非要求用户改造原 Prometheus。

### Cited Findings
- vmalert 内存保存告警状态；重启保留需配置 remoteWrite 与 remoteRead。恢复只在启动对已配置规则执行，热加载不触发恢复，过旧或与当前规则不匹配的数据可能无法恢复。 — [状态恢复说明](https://docs.victoriametrics.com/vmalert.html)
- Prometheus remote-write receiver 需要显式启动参数开启，不应假定已有实例默认可写。 — [官方 API 文档源码](https://github.com/prometheus/prometheus/blob/main/docs/querying/api.md)
- Thanos Ruler 支持本地 TSDB、for 状态恢复相关选项；其分布式读取链路增加查询失败风险。 — [Ruler 文档](https://github.com/thanos-io/thanos/blob/main/docs/components/rule.md)
- Alertmanager 支持 HA 集群；客户端应该向所有副本发送而非在副本前做普通负载均衡。 — [Alertmanager HA 说明](https://prometheus.io/docs/alerting/latest/alertmanager/)

### Inferences
- vmalert 方案若坚持只读访问原 Prometheus，需单独内部状态时序存储，或明确接受并展示重启计时重置；后者必须由产品验收标准约束，不应静默发生。
- 规则保存、执行器加载、告警状态和通知发送是不同事务域。管理端应报告 desired_revision/applied_revision、加载失败和最后评估结果，加载失败不能把旧规则误标为新版本已生效。
- 删除/禁用规则应产生明确“人为停用”状态，不伪造设备恢复；修改表达式或计时条件需定义 pending 重置、旧活动告警关闭原因及通知行为。

### Gaps
- 未验证各引擎通知队列的进程崩溃持久性，不能承诺事件不丢或恰好一次。
- 没有实际硬件和指标样本，无法给出吞吐与恢复时间承诺。

## HertzBeat 是否比执行器包装更合适？

### Takeaway
HertzBeat 是具备 UI 与告警 CRUD 的完整开源系统候选，但“Prometheus 兼容”不能直接等同于支持用户现有 Prometheus 作为只读、任意多数据源。当前核实到的 PromQL executor 绑定其 warehouse 配置，需原型验证才能升级为推荐方案。

### Cited Findings
- HertzBeat 定时阈值支持 PromQL 风格表达式、执行周期、连续满足次数、严重度与启停；文档使用专门解析语法，连续次数不应自动等同于 Prometheus `for`。 — [告警阈值文档，页面版本 1.9.1](https://hertzbeat.apache.org/docs/help/alert_threshold/)
- 源码 `AlertDefineController` 提供 POST/PUT/GET/DELETE `/api/alert/define` 以及表达式预览 API，证明存在实际规则 CRUD。 — [官方源码](https://raw.githubusercontent.com/apache/hertzbeat/master/hertzbeat-alerter/src/main/java/org/apache/hertzbeat/alert/controller/AlertDefineController.java)
- `DataSourceServiceImpl` 从注入的 `QueryExecutor` 中按 datasource 选择执行器并使用自身表达式处理器，不是通用无条件透传所有 PromQL。 — [官方源码](https://raw.githubusercontent.com/apache/hertzbeat/master/hertzbeat-alerter/src/main/java/org/apache/hertzbeat/alert/service/impl/DataSourceServiceImpl.java)
- `VictoriaMetricsQueryExecutor` 通过 `warehouse.store.victoria-metrics.enabled` 条件创建，从该 warehouse 的 URL、用户名、密码构造 HTTP PromQL 配置。 — [官方源码](https://raw.githubusercontent.com/apache/hertzbeat/master/hertzbeat-warehouse/src/main/java/org/apache/hertzbeat/warehouse/db/VictoriaMetricsQueryExecutor.java)
- 默认配置具有 H2 元数据库和本地历史存储，也支持外部数据库配置；仓库中展示的 VictoriaMetrics 配置同时包含 insert 配置。 — [官方 application.yml](https://raw.githubusercontent.com/apache/hertzbeat/master/hertzbeat-startup/src/main/resources/application.yml)
- HertzBeat 的 Prometheus 告警集成还包含“接收 Prometheus 发来的告警”的模式，此模式仍依赖 Prometheus 规则，不能用于满足本需求。 — [告警集成](https://hertzbeat.apache.org/ko/docs/help/alert_integration/)
- Apache-2.0 许可；1.9.0 升级文档标明新增/修改告警定义和预览需管理员权限，不能假设匿名初始化 API。 — [LICENSE](https://raw.githubusercontent.com/apache/hertzbeat/master/LICENSE)；[1.9.0 升级说明](https://hertzbeat.apache.org/docs/1.9.0/start/1.9.0-update/)

### Inferences
- 若选 HertzBeat，应独立验证：禁用采集后是否能只查询原 Prometheus；是否会向只读地址写入；能否按规则选择多个数据源；GPU 常用 rate/increase/窗口函数是否忠实执行；重启计数恢复、缺数、通知可靠性与升级保留自定义规则。
- HertzBeat 可以列为次级整个平台候选；与 Grafana、Nightingale 相比应以实际 PoC 通过率决定，不能仅凭有告警页面就锁定。
- 原生 UI/API 可以降低管理面开发，但 GPU 内置规则、能力发现、初始化及用户覆盖保护仍需产品化补充。

### Gaps
- 尚未证实任意外部 Prometheus、多数据源隔离、完整 PromQL 与告警 pending 恢复均可开箱即用。
- 未找到固定稳定版本开箱内置经过核实的 GPU 规则、自动安装并保留用户覆盖的官方证据。
