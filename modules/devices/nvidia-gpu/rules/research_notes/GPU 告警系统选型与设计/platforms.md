# Grafana OSS 与 Nightingale 告警平台调研

调研日期：2026-11-05。文档检索验证，未部署验证；latest/main 不是已锁定发布版本。仅采用项目官方文档和仓库。以下平台均不能据现有证据称为“安装后自动启用完整 DCGM Exporter GPU 告警”的现成成品。

## 是否能独立查询已有 Prometheus 并提供规则管理

### Takeaway
两者都能把规则执行从已有 Prometheus 中移出，用户不必修改 Prometheus rule_files。夜莺侧重独立告警；Grafana-managed alerting 已覆盖规则 UI/API 和历史版本，适合已使用 Grafana 的场景。

### Cited Findings
- 夜莺注册数据源保存地址、认证和超时；规则绑定一个或多个数据源，周期执行查询并产生事件。它在原数据源查询，不要求搬迁数据。— [对象模型](https://n9e.github.io/zh/docs/concepts/data-model)
- 夜莺支持 UI/API 管理规则及通知，按业务组授权，开源许可 Apache-2.0；其示例 Compose 同时带 MySQL、Redis、VictoriaMetrics、Categraf，这不是本项目必须照搬的最小拓扑。— [官方仓库](https://github.com/ccfos/nightingale/)
- 夜莺页面共用公开 HTTP API，JWT 或 X-User-Token 认证；无 OpenAPI/Swagger，权威接口定义为 center/router/router.go。规则入口包括 GET/POST /api/n9e/busi-group/:id/alert-rules 和 GET /api/n9e/alert-rule/:arid/pure。— [HTTP API](https://n9e.github.io/zh/docs/usecase/api/)
- Grafana-managed 规则在 Grafana 执行并存入 Grafana 数据库；data-source-managed 规则在数据源执行。Grafana 对普通 Prometheus 的后者只可查看，不能创建编辑。本项目必须使用前者。— [两类规则比较](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/create-data-source-managed-rule/)
- Grafana 提供规则 GET/POST/PUT/DELETE API；API 初始化的规则默认不能 UI 编辑，部分端点需 X-Disable-Provenance: true。最新文档正在将 provisioning API 转向 App Platform API，需固定版本验证，不应把 latest 示例当作长期契约。— [Provisioning API](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/)
- Grafana 默认许可 AGPL-3.0-only，部分子目录例外；与夜莺 Apache-2.0 存在许可证差异。— [官方许可清单](https://github.com/grafana/grafana/blob/main/LICENSING.md)

### Inferences
- 以夜莺作为“完整底座+GPU 产品层”可减少调度、告警事件、通知、权限与 UI 开发；不能把成熟底座等同于成熟 GPU 成品。
- 复用 Grafana 需选择 Grafana-managed alerts；只显示 Prometheus 原生告警不满足需求。
- 自动化封装可以调用平台 API 初始化规则，这属于系统内部实现；用户不得执行规则文件导入步骤。

### Gaps
- 尚未锁定并跑通具体夜莺/Grafana release 的规则 CRUD 及 API 兼容性。平台源码当前文档的能力必须以固定版本 PoC 校验。
- 规则范围、每卡标识和 MIG 标签兼容需要真实 DCGM Exporter 样本，不能仅凭支持 Prometheus 判定。

## 内置 GPU 规则是否真正开箱即用，增删改查如何与版本升级共存

### Takeaway
夜莺的“内置规则”是供导入的模板，直接使用仍有用户手工步骤；需产品自动初始化和适用性层才能满足需求。Grafana 原生版本历史更完整，但完整审计不在 OSS。

### Cited Findings
- 夜莺官方明确：模板中心的系统内置规则不能改删，只能导入业务组；导入默认停用；模板没有通知配置；需绑定数据源和通知后启用。系统启动加载 integrations/<集成名>/alerts/*.json 只创建模板库，不等于活动告警规则。— [模板机制](https://n9e.io/zh/docs/alerting/templates)
- 夜莺 NVIDIA 官方集成页列出 2 条告警规则（显存和温度），采集路径为 Categraf nvidia_smi 与 dcgm 插件，并列出 3 张仪表盘。页面并未证明这些规则直接兼容现有 NVIDIA DCGM Exporter 的指标和标签。— [NVIDIA 集成](https://n9e.io/zh/integrations/nvidia)
- 夜莺官方回滚说明明确：告警规则、仪表盘、通知配置没有版本历史；最后修改人和时间可见，并发编辑提示不能用来恢复上一版。— [回滚与恢复](https://n9e.github.io/zh/docs/operations/rollback)
- Grafana OSS/Enterprise 可以查看、比较、恢复规则历史版本，限制版本数量；可暂停/恢复规则，也支持恢复近期删除规则，恢复产生新 UID。— [规则查看管理](https://grafana.com/docs/grafana/latest/alerting/monitor-status/view-alert-rules/)
- Grafana 完整审计日志功能只在 Enterprise 和 Cloud 提供，不能写成 OSS 已提供。— [官方审计说明](https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/audit-grafana/)

### Inferences
- 推荐产品层持有 stable rule_key、builtin_version、revision、origin、content_hash、deleted tombstone、local_override 等元数据。新装经能力校验自动生成活动规则、绑定当前数据源与默认通知。缺指标输出不可判定，不自动启用不适用检测。
- 应明确基线与覆盖：用户编辑形成本地覆盖；升级只自动更新未修改基线，冲突需展示差异；用户删除内置规则留 tombstone 防止重启/升级复活；自定义规则不被升级覆盖。元数据不能只靠规则名称匹配。
- 夜莺路线需补足不可变 revision/audit 和回滚。若允许直接在原生夜莺界面写规则，外部产品层难以保证每次修改审计：应使用受控入口或在夜莺写事务层扩展事件及版本记录，避免两个可写事实源。
- Grafana 已有历史版本可复用，但 builtin baseline/override/tombstone 冲突策略仍需产品层；官方 OSS 版本历史不应等同完整操作审计。

### Gaps
- 没有发现上述两者提供完整、自动激活、适配硬件的 DCGM Exporter GPU 告警成品证据。不要声称已存在覆盖所有 GPU 故障的规则库。
- Nightingale 的集成数量在模板页与 schema 页出现83/88差异，不应作为选型依据。

## 可靠性、部署代价与选型验证门禁

### Takeaway
建议把夜莺作为独立告警底座的优先 PoC，Grafana-managed alerting 作功能完整度对照；若现有 Grafana 已满足接入和管理，也应优先复用。不能在没有 PoC 情况下保证重启前后逐点评估等价。

### Cited Findings
- 夜莺元数据含规则、用户、通知配置，可存 SQLite/MySQL/PostgreSQL；指标库与元数据库是两种不同职责。— [存储模型](https://n9e.github.io/zh/docs/concepts/storage)
- 夜莺 HA 多进程共享 MySQL、Redis，同 EngineName 按一致性哈希分配规则；实例间需 HTTP 互通，判定记录保留在各实例本地；内置时序库需关闭。— [安装 HA](https://n9e.io/zh/docs/install/high-availability)
- 夜莺进程挂掉后约30秒接管，启动默认等待30秒再判定；数据库不可用全站不可用，Redis 不可用会影响启动/运行；某数据源故障影响使用它的规则。— [HA 故障域](https://n9e.io/zh/docs/operations/high-availability)
- Grafana HA 默认所有节点重复执行全部规则，嵌入 Alertmanager 尽力去重，仍可能重复/乱序通知；最新文档还列出单节点评估模式，故障切换有短暂评估缺口，状态留在数据库。版本可用性需核实。— [Grafana HA](https://grafana.com/docs/grafana/latest/alerting/set-up/configure-high-availability/)
- Grafana 有 No Data/Error/Keep Last State 等配置，丢失序列有独立淘汰与恢复行为；不能把空返回简单等同健康，也不能假设“整条查询无数据”覆盖“某一张卡消失”。— [No Data/Error](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/)

### Inferences
- 本项目复用既有 Prometheus，应关闭/不部署新指标采集器与内置时序库；夜莺生产推荐明确 n9e + 元数据库 + Redis 的实际代价，不能承诺单个无依赖容器。
- 首选每集群独立实例可减少跨集群连通依赖；多数据源集中部署为可选，前提是网络、身份隔离、查询负载和故障影响可接受。
- 条件式决策：夜莺通过以下门禁后作为底座；若规则修改必须大范围 fork 或运行状态不能满足既定需求，则对照 Grafana 路线重新计成本，不直接跳到自研通用规则引擎。

### Gaps
- 未实测任何平台重启时 pending 的连续计时、通知重试持久化、状态恢复或规则修改后的状态继承。这些必须作为 PoC，不承诺完全等价。

建议 PoC 门禁（设计建议，非平台已验证能力）：
1. 固定 release/commit/license；从已有 Prometheus 只读查询，确认无 Prometheus 配置变更、无 remote_write、无新采集器。
2. 新部署只填连接/集群/通知信息，自动完成数据源与3–5条审定GPU规则的创建、适用性检查与通知绑定；用户零导入操作，重复启动无重复规则。
3. UI/API 完成新增、查询、修改、软删除、启停；修改可观察生效时间，无需重新构建镜像。
4. 增删改与平台原生 UI/API 不绕开 revision/audit；重启不复活删除规则；内置版本升级保留本地覆盖且冲突可见。
5. 固定回放覆盖每卡触发恢复、缺数/单卡消失、陈旧、counter reset、Prometheus断连、重启pending、通知断连与重试。
6. 验证实际依赖、CPU/内存、Prometheus QPS和评估周期；用故障演练确认已知恢复缺口而非写“无损”。
