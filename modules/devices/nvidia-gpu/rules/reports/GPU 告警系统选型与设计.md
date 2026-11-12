# 复用开源平台构建独立 GPU 告警系统

调研日期：2026-11-05；方法为官方文档与源码核实，尚未部署原型或连接真实集群。

**建议复用完整开源告警平台，并增加 GPU 内置规则、自动初始化和规则生命周期管理。** 用户已经完成 DCGM + Prometheus 采集，系统只需查询现有数据，部署时不修改 Prometheus 告警规则，也不要求导入规则包。夜莺适合作为优先原型，Grafana-managed Alerting 作为主要对照；最终选择应由固定版本原型决定。本轮没有核实到同时满足“只读现有 Prometheus、GPU 判断自动启用、完整在线 CRUD 与升级保护”的现成开源 GPU 成品，不能把通用平台或模板库直接称为满足全部需求。现成底座能省去调度、告警状态、通知和基础界面的重复开发，但 GPU 规则适用性与用户修改保护仍需产品化。自研编译器、IR 和执行引擎不再是项目起点。

## 用户需要的是自动生效的系统，而不是模板入口

首次部署的完整体验应是配置 Prometheus 地址、cluster_id、通知与持久化参数后，系统自动发现 GPU 和实际指标，创建可编辑规则、绑定通知并执行适用检测。系统内部调用 API 初始化规则与用户手动导入是不同交付方式。后续授权用户可以在线增删改查，且普通修改无需重建镜像。缺少某类指标时，应展示覆盖不足并继续执行其他可用规则；不能用“全部无告警”代替 GPU 健康结论。

夜莺官方模板机制明确，内置对象进入模板库，需导入业务组才能成为规则，导入后默认停用且没有通知配置。因此“夜莺有 NVIDIA 模板”并不意味着用户安装后已经获得 GPU 告警；其 NVIDIA 集成页面列出的规则也不能直接假设兼容用户现有 DCGM Exporter 字段。产品须在首次启动内部完成实际规则创建，而不是提供一页模板让部署者操作。([夜莺模板](https://n9e.io/zh/docs/alerting/templates)、[NVIDIA 集成](https://n9e.io/zh/integrations/nvidia))

## 完整平台比独立执行器更接近目标

夜莺的数据源与规则模型允许周期查询原数据源，不要求迁移指标，提供 UI/API 管理、通知和按业务组权限；开源许可为 Apache-2.0。它的规则没有完整历史版本，官方回滚说明明确只能看到最后修改信息，不能据此恢复旧版。以夜莺为底座需要补不可变 revision、审计和本地覆盖保护，而且不能允许原生 UI 绕过这些写入约束。其生产依赖也应如实列出；示例带有采集器和指标库，不意味着本项目需要照搬，原有采集与 Prometheus 应继续复用。([对象模型](https://n9e.github.io/zh/docs/concepts/data-model)、[官方仓库](https://github.com/ccfos/nightingale/)、[API](https://n9e.github.io/zh/docs/usecase/api/)、[回滚说明](https://n9e.github.io/zh/docs/operations/rollback)、[存储模型](https://n9e.github.io/zh/docs/concepts/storage))

Grafana 必须选择 **Grafana-managed**，由 Grafana 查询现有 Prometheus 并执行规则；data-source-managed 规则由数据源执行，普通 Prometheus 的这类规则只能在 Grafana 查看，不符合本需求。Grafana 有规则 CRUD API、历史查看比较与恢复，减少生命周期开发。API 初始化默认 provenance 可能限制 UI 编辑，需要按固定版本采用支持可编辑对象的端点和配置并实际验证。完整审计日志为 Enterprise/Cloud 功能，不能算作 OSS 现成能力；默认 AGPL-3.0-only 许可也需结合分发及修改方式核查。([规则类型](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/create-data-source-managed-rule/)、[API](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/)、[历史与管理](https://grafana.com/docs/grafana/latest/alerting/monitor-status/view-alert-rules/)、[审计](https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/audit-grafana/)、[许可](https://github.com/grafana/grafana/blob/main/LICENSING.md))

| 候选 | 已核实的适用能力 | 与目标的主要差距 | 建议 |
| --- | --- | --- | --- |
| 夜莺 | 原数据源查询、UI/API、通知、权限，Apache-2.0 | 内置模板仍需导入；完整版本审计及 GPU 自动化需补 | 优先原型 |
| Grafana OSS managed | 外部源查询、规则 CRUD 与历史、通知 | 初始化可编辑性需验证；补 OSS 审计与内置升级保护，AGPL | 主要对照，已有 Grafana 时优先考虑复用 |
| vmalert | 查询 Prometheus HTTP API、执行并发往 Alertmanager | 原生为配置/热加载、缺管理写 API；需管理面及恢复存储 | 有明确成本优势才包装 |
| Thanos Ruler | 远端查询、规则执行与通知 | rule-file 管理及额外拓扑，不能直接解决 CRUD | 已有 Thanos 时再评估 |
| HertzBeat | UI/API 阈值 CRUD、预览，Apache-2.0 | 任意只读外部 Prometheus、多源及语义尚未证实 | 次级候选 |
| NVSentinel | GPU 故障检测与修复，Apache-2.0 | 输入是 DCGM 等健康源，非本需求的 Prometheus 查询入口 | 当前不引入 |

vmalert 支持现有 Prometheus 查询 API，但规则保存和变更仍以文件/URL及 reload 为主，官方 Grafana 集成也明确这种规则只能查看。其重启恢复依赖 remote write/read，不能假定用户已有 Prometheus 可写；包装路线需要内部状态存储或其他明确恢复方案。Thanos Ruler 同样用 rule-file 与 reload，并非天然具有 CRUD 产品管理面。Alertmanager 只负责接收、分组、去重、路由和通知，不查询 GPU 指标。([vmalert](https://docs.victoriametrics.com/victoriametrics/vmalert/)、[只读集成限制](https://docs.victoriametrics.com/guides/vmalert-datasource-managed-alerts-grafana/)、[恢复](https://docs.victoriametrics.com/vmalert.html)、[Thanos Ruler](https://thanos.io/tip/components/rule.md/)、[Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/))

HertzBeat 的实际源码提供告警定义增删改查与预览接口，但现有 PromQL 查询执行器绑定 warehouse 配置。“支持 Prometheus”还包含接收 Prometheus 已生成告警的模式，后者仍依赖用户规则，不能作为满足需求的证据。需要进一步原型证明任意外部 Prometheus 只读查询、多数据源隔离、窗口函数及持续条件语义，暂不优先。([CRUD 源码](https://raw.githubusercontent.com/apache/hertzbeat/master/hertzbeat-alerter/src/main/java/org/apache/hertzbeat/alert/controller/AlertDefineController.java)、[查询执行器](https://raw.githubusercontent.com/apache/hertzbeat/master/hertzbeat-warehouse/src/main/java/org/apache/hertzbeat/warehouse/db/VictoriaMetricsQueryExecutor.java)、[阈值语义](https://hertzbeat.apache.org/docs/help/alert_threshold/))

## GPU 专用方案提供参考，但输入与管理方式仍不匹配

NVIDIA NVSentinel 是 Kubernetes GPU 故障检测与修复系统，但 GPU monitor 文档中的 operator、external、embedded 模式均连接 DCGM hostengine，不是查询现有 Prometheus 的模式。为使用它而增加节点代理、日志或自动修复，会改变当前范围。它可以作为 GPU 故障知识与未来集成的参考，不能称为本次即插即用替代品。([NVSentinel 仓库](https://github.com/NVIDIA/NVSentinel)、[输入模式](https://docs.nvidia.com/nvsentinel/configuration/gpu-health-monitor/))

Grafana Marketplace 的 integrationplumbers NVIDIA DCGM app 接入 Prometheus 并提供 GPU 告警及覆盖检查，说明这一产品体验有现实参照。但页面归类为 Commercial Marketplace，自托管规则仍需 provisioning 文件与重启，安装规则不能在 UI 编辑；没有核实开源授权。因此不作为本项目开源可复用底座，也不复制其规则阈值当作 NVIDIA 官方建议。([插件官方页面](https://grafana.com/grafana/plugins/integrationplumbers-nvidiadcgm-app/))

GPU 规则的难点不在简单比较，而在指标有效性和适用范围。NVIDIA 字段定义区分 XID 错误码、设备温度余量与不同单位；XID 不应使用 increase 当作错误次数。Exporter 实际字段依赖配置、硬件、驱动和权限，MIG 有独立粒度。DCGM 还有 blank/not supported 等 sentinel，解析为数值不代表有效；INT64 经 Prometheus float64 后也不能保证区分相邻特殊值的原因。系统必须过滤并展示无效数据，不能让它们误触温度等硬件阈值。([Exporter 指标](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)、[字段含义](https://docs.nvidia.com/datacenter/dcgm/latest/reference/field-identifiers.html)、[特殊值](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-enums.html))

首批正式规则应从有 NVIDIA 依据且现有输入支持的 ECC、行重映射、型号相关 XID、热降频/温差与采集覆盖检测中审定。当前只是候选类别，没有形成正式规则库或通用阈值。高利用率、低利用率或高显存占用不能自动等同硬件故障；被动遥测健康检查本身也不证明 GPU 一定能正常执行工作负载。([DCGM 功能概览](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html)、[健康监测边界](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/health-monitoring.html))

## 规则可编辑要求把初始化与升级分开设计

内置目录应是不可变发行基线，用户修改、禁用和删除是独立持久决定。自动首次初始化与每次启动覆盖规则必须分开：删除内置规则留下 tombstone，重启不复活；本地改动保留，目录升级出现冲突时展示旧基线、本地和新基线差异。未改规则可自动升级，自定义规则保持不动，回滚创建新 revision。禁用、删除或改变语义的旧告警按行政原因关闭，不能发成“GPU 已恢复”。这些属于本项目拟定设计，并非声称候选平台原生全部具备。

版本审计需要唯一写入口。优先扩展平台原生规则写事务；如果通过外部管理数据库管理，则受管 GPU 规则只能经产品 UI/API 写入，底座为执行投影。保存期望版本、应用操作、回读确认及 active_revision，避免数据库写成功就标记执行成功。不同存储与 HTTP API 不构成单一事务，只承诺每条可验证激活及明确失败补偿，不无依据承诺整组原子性。

持久数据库也不自动保证告警计时和通知队列恢复。夜莺 HA 有接管及启动等待，Grafana HA 有重复评估和尽力去重边界；Grafana 的 No Data/Error 处理也不能直接覆盖某一张 GPU 从结果中消失。必须用固定版本实测 pending/firing 重启、单卡消失、Prometheus 断网、通知重试和规则切换，明确运行契约。([夜莺故障域](https://n9e.github.io/zh/docs/operations/high-availability)、[Grafana HA](https://grafana.com/docs/grafana/latest/alerting/set-up/configure-high-availability/)、[缺数及错误](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/))

## 用真实接入与第二集群复装决定最终底座

下一步先取得实际指标、设备身份和通知协议，再将夜莺与 Grafana 固定到明确 release，验证只读接入、空库零导入初始化、在线 CRUD、全写路径审计、升级保护、每卡数据质量以及重启/通知恢复。平台 README 或 latest 文档只能提供候选证据，不能代替这些验收。优先复用完整平台是当前判断，最终平台选择与维护分支范围须由原型结果决定。

项目完成的有效证据是在第二套已有采集的 GPU 集群上，使用同一发行版，只配置连接、集群身份和通知等参数就能运行，并清楚展示哪些故障有覆盖。完整修订已落入[需求](../docs/01-需求文档.md)、[架构](../docs/02-技术架构文档.md)与[实施计划](../docs/03-开发计划文档.md)；这些是后续实现与验收基线，不表示系统已经实现。
