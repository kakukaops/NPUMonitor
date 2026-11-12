# GPU 规则来源与独立系统需求

调研日期：2026-11-05。以下“需求建议”来自用户会话及工程推论，不声称是第三方产品现成能力。尚未连接用户真实集群或执行原型。

## 1. 哪些 GPU 规则依据与数据限制必须纳入设计

### Takeaway
已有采集完成不等于所有告警所需字段均已存在。新系统必须只读查询现有 Prometheus，自动发现实际可用字段、单位及实体粒度，缺少输入时报告覆盖不足，不能要求用户为开始使用修改采集或导入规则。

### Cited Findings
- DCGM Exporter 的采集字段由 CSV/ConfigMap/YAML 选择；配置了字段不保证运行时输出，支持性取决于 DCGM、硬件、驱动、权限与部署。Exporter 不自动校验配置的 Prometheus 类型是否符合 DCGM 定义。MIG 实例带 GPU_I_PROFILE/GPU_I_ID，compute instance 可带 GPU_CI_ID；Kubernetes 标签映射不会创造硬件不支持的字段。最新文档的字段存在改名、规范名称与旧 exporter 指标名映射，因此应固定版本测试。 — [NVIDIA Exporter 指标](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)
- DCGM 的整数和浮点字段有 blank、not found、not supported、not permissioned 特殊数值；INT64_BLANK 为 0x7ffffffffffffff0，FP64_BLANK 为 140737488355328.0，官方宏按大于等于 blank 识别，不能把所有合法解析的数字当有效样本。 — [NVIDIA 枚举宏](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-enums.html)
- 官方字段说明：XID 字段值表示具体错误码，而非次数；GPU temperature slowdown 和 temperature margin 分别表示设备降频温度与距最近降频阈值的温差；旧 GPU_UTIL 是百分比，而 canonical UTIL_RATIO 名称存在单位差异；旧 thermal/power violation 是 ns；旧显存字段是 MiB。 — [NVIDIA 字段定义](https://docs.nvidia.com/datacenter/dcgm/latest/reference/field-identifiers.html)
- DCGM 被动健康检查分析保留遥测，不运行测试负载，不能证明 GPU 能正常执行工作负载。 — [NVIDIA 健康监测](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/health-monitoring.html)
- DCGM 已有按子系统判断故障的逻辑，包括不可纠正内存错误、待退休页、行重映射失败、thermal violation、NVLink 等；同类 XID 的解释可能依赖架构，例如 XID 93 的 InfoROM 判断仅针对 Volta。这可作为规则依据，但不代表所有所需输入已在用户 Prometheus 中。 — [NVIDIA 功能概览](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html)
- DCGM Exporter 代码库 Apache-2.0。引用文档事实与复制代码/规则应分别核验许可证与版本。 — [Exporter 仓库](https://github.com/NVIDIA/dcgm-exporter)

### Inferences
- 建议第一版规则候选类别：不可纠正 ECC 增量、行重映射失败/待处理、按错误码与型号解释的 XID、设备提供的温度阈值/温差、热降频、必要指标或已发现设备停止上报、采集目标/查询失败。是否入正式内置集取决于实际字段与明确判断依据；不为了数量强行凑规则。
- 内存占用高/利用率高/低不是通用硬件故障，默认作为容量或效率建议关闭，不自动以 critical 开启。工作负载分配归因需要当前范围外的上下文时，应留为后续，不扩张当前 GPU 指标边界。
- XID gauge 不能使用 increase 当错误次数；持续保存非零码可能代表旧事件，必须定义“新事件”依据与抑制策略。仅有采样后的最后值可能丢失中间多个事件，应明确能力边界。
- 指标规范化映射必须按实际名字、语义、单位和版本维护，不能见类似名称自动乘系数。sentinel 过滤后需要另报数据无效，不能当成正常；Prometheus float64 精度不足以区分相邻 INT64 sentinel 的具体原因，不承诺细分所有错误原因。
- GPU 设备键至少为 cluster_id + stable UUID + 规则实体粒度，MIG GI/CI 与物理卡分开；型号未知或稳定 ID 缺失报告不能判定。动态 pod 标签不能进入硬件告警稳定身份，否则换 pod 产生新告警。

### Gaps
- 用户的 GPU 型号、Exporter/DCGM 版本、MIG、实际字段和标签样本、采样周期与目标规模均未提供；只能提出能力发现与验证门禁，不能承诺某条 GPU 规则必然可启用。
- 来源文档有现行与旧版并存；正式实现需锁定 tag/commit、字段清单及真实样本，不用 latest 文档直接替代环境测试。

## 2. 是否已有 GPU 专用系统可直接满足需求

### Takeaway
发现了 GPU 专用方案，但本轮未证实有一个开源成品同时满足“只查询已有 Prometheus、自动内置 GPU 告警、在线规则完整 CRUD”。这不是断言全行业不存在；应优先复用通用告警平台并封装 GPU 能力，避免重建执行语义。

### Cited Findings
- NVIDIA NVSentinel 是 Apache-2.0 的 Kubernetes GPU 故障检测与修复系统，架构包括 DCGM/syslog/cloud health monitors、MongoDB、Kubernetes 节点管理与修复模块。 — [官方仓库](https://github.com/NVIDIA/NVSentinel)
- NVSentinel GPU monitor 的三种输入模式为 operator DCGM service、external hostengine 和 embedded hostengine，均面向 DCGM 连接而非已有 Prometheus 查询；external 模式仍需逐节点 hostengine 和版本标签，embedded 模式涉及 NVIDIA RuntimeClass 与特权容器。不能把它称为符合现有只读 Prometheus 集成要求的直接替代品。 — [GPU Monitor 配置](https://docs.nvidia.com/nvsentinel/configuration/gpu-health-monitor/)
- Grafana Marketplace 中的 integrationplumbers NVIDIA DCGM app 直接读已有 Prometheus datasource，含 setup check 和十三条 GPU 告警。页面明确归类 Commercial Marketplace，链接厂商使用许可而非开源许可证。自托管告警需下载文件到 Grafana provisioning 目录并重启，且安装后 UI 不可编辑。此路径直接违反用户拒绝规则包导入以及后续 CRUD 的关键要求，不能作为开源首选；其指标覆盖检查和缺少输入提示可借鉴，数值默认值不能当 NVIDIA 官方阈值。 — [官方插件页面](https://grafana.com/grafana/plugins/integrationplumbers-nvidiadcgm-app/)

### Inferences
- 产品体验可复用的做法是“选择数据源 → 自动能力检查 → 告警开始工作”，但应由安装/初始化流程内部建成可管理规则，不能把手动导入步骤留给使用者。
- NVSentinel 可作为 GPU 判断知识与边界的参考，或未来单独的故障修复集成候选；当前不应为了使用其规则而追加日志、节点代理和自动修复。

### Gaps
- NVSentinel 是否另有第三方 Prometheus monitor 插件及在线规则 CRUD，不在已查官方模式中得到证实；不声称支持。
- 商业 Grafana DCGM app 未发现开源代码授权，不应复制其规则表达式；只能参考公开功能概念和另行查证 NVIDIA 依据。

## 3. 需求如何覆盖即用体验与后续规则增删改查

### Takeaway
“不需要配置规则”是默认部署体验，“可以增删改查”是授权管理能力，两者不冲突。内置基线、用户覆盖与有效规则应分层，自动首次初始化与后续升级必须区分，不能每次启动无条件重建规则。

### Cited Findings
- 当前用户已明确：DCGM + Prometheus 已部署且采集完成；希望独立系统直接使用、不配 Prometheus 规则、不导入规则包；其他集群也要部署；后续需增删改查。这些是会话中的一手约束，不是待确认假设。
- 对比产品的“自动覆盖规则文件”与“UI 可编辑数据库规则”存在不同管理语义，Grafana DCGM 插件也明确 provisioned 规则不可 UI 编辑，说明不能把 provisioning 与 runtime CRUD 混为一谈。 — [插件告警管理说明](https://grafana.com/grafana/plugins/integrationplumbers-nvidiadcgm-app/)

### Inferences
以下为建议需求和验收，需由主文档整合并标为拟定设计：

**默认部署**
- 每套集群部署同一发行版，只填现有 Prometheus URL/认证引用、cluster_id、通知出口及持久化配置；不编辑已有 Prometheus 配置、规则文件、CRD，不向已有 Prometheus 写入或 remote_write，不安装新的 GPU 采集器。
- 系统发行物携带审定默认目录，初始化内部数据库和执行器对象为幂等动作；自动检测输入并启用适用规则，不依赖部署者点击“导入模板”。覆盖清单展示 active/not applicable/missing metadata/missing metric/stale/query error。
- MVP 默认每集群独立部署，持久化和通知隔离；集中管理多集群是可选拓扑，不能反向要求打通所有网络。若选择集中部署，必须支持每数据源独立认证、超时、并发配额和集群标识，失败不拖垮其他源。

**CRUD 规则模型**
- Rule: stable id、name、origin(builtin/custom)、builtin_revision、effective_revision、source/license、GPU applicability、metric requirements、PromQL/执行器原生表达式、interval/for/recovery、labels、severity、no-data/error policy、enabled、notification route、created/updated actor/time。
- 规则列表支持 id/name/status/severity/source/适用设备搜索过滤，详情显示有效版本、来源、预期输入、覆盖、最近评估和最近错误。新增/复制规则默认为草稿；预览查询的实体/数值、语法检查、资源校验、验证成功后显式发布。现有告警持续运行直至新版本激活成功。
- 基本 viewer/operator/admin 权限；修改走鉴权 API，审计不记录明文 secret；表达式不允许任意代码执行，限制窗口长度、查询超时、返回系列与并发，防止一条规则压垮已有 Prometheus。
- 修改采用 revision/ETag 乐观锁，过期更新返回冲突。发布后暴露 desired_revision、active_revision、last_apply_error，避免数据库成功但执行器未加载的假成功；执行器 API 不支持跨规则事务时，不能承诺全组原子性，只承诺每条可验证激活或明确补偿。
- 规则表达式/窗口/身份标签改变应结束旧版本实例并建立新版本 pending；保留事件历史，旧实例关闭原因 rule_changed，不能伪装 GPU 恢复。
- 删除用户规则为软删除并停评估；内置规则删除记录 tombstone 而非删来源目录。禁用和删除都清理 pending，活动告警记录行政关闭原因，禁止继续重复通知；如发送 closed/resolved 应标明 disabled/deleted 管理原因，不能称为 hardware_recovered。历史记录保留期限可配置。

**升级与覆盖**
- builtin_catalog（发行版提供，immutable）+ override（用户改动/启停/删除标记，DB durable）→ effective_rule。更简单的全量用户副本也可，但必须明确上游更新合并规则。
- 未改内置规则升级到新基线；用户自定义规则、用户改动、禁用标记和删除 tombstone 保留；内置新版本与用户改动冲突时生成待审差异，不自动覆盖。可“恢复默认”清除 override/tombstone，并显示恢复至哪个目录版本。
- 上游删除某内置规则时，未改对象退役；用户修改对象标为 upstream_removed 并需审核，不静默继续假称官方内置。安全问题应有单独显式撤销策略而非普通更新偷偷覆盖用户决定。
- 规则回滚是创建指向旧内容的新 revision，保留审计；系统程序回滚与规则目录回滚、DB schema rollback 分开，备份后升级并验证兼容。
- 并发启动初始化与进程重启不能恢复已删除内置规则或覆盖用户编辑；每次重启不应发送同一组新告警。告警状态持久化/重建行为要按所选执行器原生语义验证，不能先承诺不中断严格等价。

**关键验收用例**
1. 空白持久库 + 接入真实已有 Prometheus，系统不向其写配置；自动呈现可用 GPU 与内置有效规则，并能将受控 fixture 触发送到测试出口。
2. 只有默认采集字段时，缺少 ECC/健康字段的规则明确报告缺失，既不假正常，也不阻断其他已支持规则开始工作。
3. 新增、查询、修改、启停、删除、预览、恢复默认、单条版本回滚经 UI/API 均验证；非法表达式拒绝并保留原生效版本；未授权写入拒绝。
4. 删除/禁用正在 firing 的规则后停止后续评估与重复通知，历史显示行政关闭；重启、升级后 tombstone 和禁用状态不丢失。
5. 内置版本升级时保持用户覆盖与自定义规则，冲突可见；重复初始化不增加副本；并发编辑触发冲突；apply 失败可见并可回滚。
6. 缺数、sentinel、NaN、旧样本、查询超时、counter reset、GPU 更换、MIG 重建与动态工作负载标签变化按约定区分处理。
7. 数据源与通知断网、重启、规则版本切换分别演练；多源部署时单源故障不影响其余集群，通知事件含 cluster_id、device_key、rule_id/revision。

### Gaps
- 具体 RBAC 粒度、审计保留天数、默认管理流程是否需审核、集中与逐集群拓扑尚未由用户确定；以上使用简单默认和可扩展接口，不增加多租户审批系统。
- 不应继续沿用旧文档对“必须编译成 Go、必须自建 IR、SQLite 必选”的硬性表述；这些属于旧实现假设，应随选型移除。
