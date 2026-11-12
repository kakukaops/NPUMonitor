# H100 覆盖现状与完整性审查方法

## 当前仓库实际覆盖了什么

### Takeaway

当前是“格式样例与模拟链路已建立”，不是“H100规则库已完成”。正式目录只有1个指标、1条规则，均为draft；已发布、默认自动启用和真实H100验证数量均为0。六条实验规则与单表达式18组/31断言不能转化为H100故障覆盖百分比。

### Cited Findings

- 本次直接解析YAML/JSON结果：正式指标1、正式规则1、released指标0、released规则0、auto_when_applicable规则0；H100 PCIe/SXM/NVL的real_cluster_validation全部not_run。[指标定义](../../../common/monitoring/catalog/metrics.yaml)、[规则定义](../../monitoring/catalog/rules.yaml)、[硬件配置](../../../common/monitoring/catalog/hardware.yaml)
- 唯一正式候选为volatile DBE近期新增：有负数、NaN/Inf、INT64 blank、最少样本与新鲜度guard，但发布被型号适配、采集映射、配套数据质量、夜莺结束语义和查询预算等门禁阻塞；default_policy=disabled。[规则卡](../../monitoring/rules/nvidia.ecc_dbe_new_errors.md)
- 新候选的测试是Prometheus 3.2.1下18组固定样本、31个求值断言，验证的是这一表达式，不执行夜莺状态机和通知；真实集群not_run。[样例测试](../../monitoring/tests/README.md)
- 旧实验目录六条为温度示范、XID79、DBE新增、采集失败、已发现设备温度序列消失、NaN温度；它们限制在gpu-simulator、gpu-sim-lab与simulated=true。[实验目录](../../rules/lab-catalog.json)
- 旧模拟链路有持续高温和八个补充场景证据；NaN规则最初失败，改成bool有限值后定向通过。该实验既不是H100采集验证，也不是新5分钟ECC表达式的通知验收。[验收报告](../../docs/07-首批模拟规则验收报告.md)
- `modules/devices/nvidia-gpu/rules/monitoring/coverage.md`现为一行ECC样例，尚未列出完整故障域、字段处置清单或不可覆盖目标；因此目前不具备计算全面性百分比的已审定分母。[覆盖矩阵](../../monitoring/coverage.md)

### Inferences

- “已有6条规则”“已有18个测试”只能说明工作量或局部验证，不能说明H100监控全面性；应优先建立有限、版本化、逐项有处置结论的清单。
- 正式目录把三种形态都标unknown是正确的诚实边界；不能为追求高覆盖率先把unknown当不适用排除。

### Gaps

- 尚无真实H100形态、驱动/DCGM/Exporter版本、采集配置、/metrics与Prometheus标签/时序样本；无法判断哪些官方字段在目标环境真正可用。
- 尚无全量字段与故障目标枚举清单，故不报告“已覆盖X%”，包括不能将下文建议24项目标直接伪装为NVIDIA规定的完整全集。

## 如何建立有证据的覆盖基线和缺口矩阵

### Takeaway

需要从“官方字段全集”和“故障/处置全集”两端交叉核对，再验证现场可见性。默认Exporter清单、DCGM全部字段、设备支持的字段和现场Prometheus实际序列是四个不同集合，任何一个都不能单独充当全部可监控故障的分母。

### Cited Findings

- NVIDIA说明Exporter按CSV/ConfigMap/YAML选择字段；配置类型按原样使用，不自动校验语义；配置了字段也不保证运行时发出。官方Exporter指标页列出的是随该版本提供的清单，并非所有可自定义DCGM字段。有效输出需看目标/metrics。[DCGM Exporter Metrics，rolling，页面2026-10-27更新](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)
- 同页说明MIG实体与GPU/GI/CI的字段支持受DCGM控制，GI/CI标签和采集选择影响时序粒度；额外Kubernetes/HPC标签不会创造硬件字段支持。[同一官方页 Runtime Considerations](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html#runtime-considerations)
- 官方健康监测从被动字段样本判断PCIe、内存、InfoROM、驱动、温度/功耗、NVLink、NVSwitch等域；Healthy仅表示已启用规则在保留样本中没有发现事件，并不证明全部子系统被监视或主动压力测试通过。[Health Monitoring，rolling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/health-monitoring.html)
- 较早固定3.1 API明确列举PCIe、NVLink、PMU、MCU、MEM、SM、InfoROM、THERMAL、POWER、DRIVER及NVSwitch fatal/nonfatal健康系统。枚举存在仍不等于某H100配置支持或全部实现。[DCGM 3.1 Structure Definitions，dcgmHealthSystems_enum](https://docs.nvidia.com/datacenter/dcgm/3.1/dcgm-api/dcgm-api-structs.html)
- 固定Exporter CSV中既有active也有注释候选，例ECC、thermal/power violation、fabric与新增health/event指标不能仅因出现在文件中就声称现有环境已采集。[NVIDIA CSV commit fafd151148052628061a80450b4ee037a5fa0c3c](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- Prometheus为抓取目标提供up，描述的是scrape成功/失败；这是目标可达性而非每张GPU或每个字段完整性。[Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/)
- PromQL选取最近有效样本并有staleness处理；某序列消失后不能简单用空结果当零值或健康。[Prometheus v3.2.1 Querying basics](https://github.com/prometheus/prometheus/blob/v3.2.1/docs/querying/basics.md)

### Inferences

以下24项是供本项目冻结/审阅的**第一版审查目标提案**，不是NVIDIA官方“24条H100规则包”。正式百分比必须等具体H100配置、来源版本与目标粒度确认后才能计算。每行进一步拆成设备/链路/字段/状态，编号稳定保留；不适用必须有依据，unknown不能删除。故障域依据来自上文健康系统，具体字段由对应领域研究笔记进一步核实。

| 目标ID | 审查目标与预期角色 | 需要映射的输入/依据 | 当前正式目录 | 当前模拟证据 | 主要缺口 |
| --- | --- | --- | --- | --- | --- |
| H100-C01 | 型号/形态/身份/实体模式；context+准入 | H100 PCIe/SXM/NVL清单、UUID、GI/CI模式、版本 | 有矩阵但准入未实现 | SIMULATED-GPU身份隔离 | 无真实H100配置与型号准入 |
| H100-C02 | 字段名/单位/类型/别名；context+质量 | 固定DCGM字段ID+Exporter CSV+#TYPE | 仅ECC一项partial | 小量合成字段 | 无全字段映射与实际类型核对 |
| H100-C03 | 采集目标失败；alert | up、抓取错误/目标清单 | 无正式卡 | scrape_error已测 | 没有生产目标绑定；从配置移除与失败需区分 |
| H100-C04 | 单卡/全卡消失；alert | 已知/预期设备集合与观测集合 | 无正式卡 | 单卡/全卡温度序列消失已测 | 未知首次设备数、设备替换、有限历史退出 |
| H100-C05 | 必需字段缺失/陈旧；alert+coverage | 按设备字段契约、timestamp、采样/刷新周期 | ECC只抑制判断 | 旧温度缺数、新ECC陈旧用例 | 没有通用数据质量告警，不能抑制后显示健康 |
| H100-C06 | NaN/Inf/sentinel/权限/不支持；alert+coverage | 值域、错误/空值映射、运行权限 | ECC guard部分已测 | 温度NaN有限值告警已测 | 其他字段和Exporter实际映射未知 |
| H100-C07 | 查询/评估/通知链路自身异常；alert | 查询错误、延迟、初始化/应用状态、发送失败 | 无正式卡 | 成功发送仅正向 | 网络故障、重试积压与重启缺口 |
| H100-C08 | 不可纠正ECC新增，DRAM/SRAM范围；alert | 分存储位置/类别/累计范围字段 | 仅汇总volatile DBE草案 | 旧DBE新增已测 | H100存储域细分与目标支持未知 |
| H100-C09 | 可纠正ECC趋势；候选alert或dashboard | corrected/SBE字段与官方风险判据 | 无 | 无 | 不可随意制定通用次数阈值 |
| H100-C10 | SRAM阈值/不可纠正状态；alert | 官方SRAM故障标志/判据与可见字段 | 无 | 无 | 不能用汇总ECC增量替代官方SRAM判据 |
| H100-C11 | 行重映射失败；alert | failure flag及真实映射 | 无 | 模拟器发字段但没有规则 | 无触发/恢复与硬件支持证据 |
| H100-C12 | 行重映射pending；alert或处置提示 | pending flag、要求重置/排空的上下文 | 无 | 无 | 不等于failure，需独立处置语义 |
| H100-C13 | 重映射资源/记录健康；alert+dashboard | row统计、bucket/availability、官方条件 | 无 | 无 | API可见性、型号/版本与RMA语义 |
| H100-C14 | XID严重事件与影响；alert | H100适用XID、最近码/事件流、contained/uncontained | 无 | 仅79状态演示 | 不覆盖其他XID，最近值非次数，无日志事件完整性 |
| H100-C15 | InfoROM/驱动/管理组件健康；alert | InfoROM、driver/hostengine健康及版本条件 | 无 | 无 | 健康子系统未映射，软件栈未知 |
| H100-C16 | GPU/HBM温度安全余量；alert | 温度、设备阈值、形态条件 | 无 | 固定85°C示范 | 无H100设备阈值依据，不能直接生产启用 |
| H100-C17 | 热降频/时钟限制原因；alert+context | thermal violation、clock event/reason | 无 | 无 | 位掩码/事件/累计时长的语义未映射 |
| H100-C18 | 功率限制及降频；候选alert+context | configured/enforced power limit、clock原因 | 无 | 无 | TDP不是阈值，正常功率管理不等于故障 |
| H100-C19 | 电源异常/不可读；alert | power health、违例/无效值 | 无 | 无 | 设备值与整机PSU/供电链范围分开 |
| H100-C20 | PCIe错误与链路退化；alert+context | replay、链路状态/宽度/速率、官方判据 | 无 | 无 | 传输量低不证明坏链路，实际字段支持未知 |
| H100-C21 | NVLink错误/链路/对端关系；alert+context | Hopper对应错误字段、链路状态与拓扑 | 无 | 无 | 前代字段不能直接继承，形态/拓扑未核实 |
| H100-C22 | NVSwitch/fabric健康；按拓扑alert | switch/fabric健康、fatal/nonfatal、Fabric Manager | 无 | 无 | 非所有H100部署都有NVSwitch；GPU序列不能证明交换机覆盖 |
| H100-C23 | 显存/计算/带宽容量效率；dashboard+opt-in | FB、GPU/SM/Tensor/DRAM/互联负载、作业上下文 | 无 | 模拟少量值，无规则验收 | 业务依赖、profile支持与复用限制，无通用故障阈值 |
| H100-C24 | 主动诊断及现场整机故障边界；诊断或外部依赖 | memory/stress/bandwidth诊断、系统/作业/PSU日志 | 不在只读指标自动检测范围 | 无 | 必须明示排除/依赖，不得称在线监控全硬件验收 |

每行的角色和拆分属于工程审查建议；不能仅用本表已写24行就说覆盖全部已知H100问题。parent领域研究会补充各行正式输入名与版本依据。

建议将两个登记册分开：

1. `field-inventory`：原始字段ID/别名/类型/单位/entity/version/是否导出/标签/权限/判定角色/引用目标。每个字段分类为alert、dashboard、context、not_applicable、missing_input或unverified；所有排除需理由。
2. `detection-targets`：故障/异常目标、官方判据、影响、可观察输入、规则ID、设备配置、测试证据、处置和边界。允许一个字段多个目标、多字段一个目标，也允许无现有输入的目标保留为缺口。

### Gaps

- 本地尚未真正枚举固定版本所有DCGM字段和所有H100官方故障判据；本次审查不能声称枚举已闭合。
- 当前H100实际形态、拓扑未知，NVSwitch/MIG等只能暂记unverified，不能仅因环境未知把它们标not_applicable。
- 只读已有Prometheus的约束意味着某些目标可能永远缺输入；应把missing_input和采集建议交付出来，而非暗中增加采集或删除目标。

## 怎样证明覆盖完整性并保持后续不退化

### Takeaway

能证明的是“指定版本、指定H100配置、已审定目标集合中的每项都有明确结论与分层证据”，不能证明“所有H100故障永远可检测”。完整性是可审计、可复现和有边界的闭合过程，不是规则数量多或测试全绿。

### Cited Findings

- DCGM被动健康检查不施加工作负载；完整硬件验证/RMA需要另外的离线诊断机制，在线监控正常并不能替代它。[Health Monitoring](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/health-monitoring.html)、[DCGM 3.1 Feature Overview](https://docs.nvidia.com/datacenter/dcgm/3.1/user-guide/feature-overview.html)
- Exporter配置、支持实体、权限、DCGM版本及实际运行输出共同决定能否得到字段；因此只检索模板或读取默认CSV无法闭合现场覆盖。[DCGM Exporter Metrics](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)
- 本项目现在没有H100采集/现场证据，H100 profile仍unknown，正式样例仍disabled。这是当前数据边界而不是本次算法所能绕开的障碍。[硬件矩阵](../../../common/monitoring/catalog/hardware.yaml)、[规则发布门禁](../../monitoring/catalog/rules.yaml)

### Inferences

建议执行以下流程，明确区分本次已完成的仓库审计与后续必须实施的动作：

**A. 冻结范围。** 记录H100形态、GPU数量、UUID、MIG状态、互联/交换机拓扑、驱动/DCGM/Exporter与采集文件版本、scrape/refresh周期。未知项继续显示，不能把Hopper架构名当具体现场认证。

**B. 冻结官方基线。** 为DCGM fields/health systems/errors、Exporter presets及额外指标、H100产品/内存故障管理/XID/排障/驱动已知问题、Prometheus执行语义建立来源清单；保存commit/release、章节、采集日期、摘要。滚动页面保存可追溯快照或内容hash并标记滚动风险。不存在统一官方H100 PromQL全集时，明确以多来源故障目标核对，而非假设下载了完整规则包。

**C. 双向穷举且逐项处置。** 从故障域查缺字段，从字段全集反查未使用输入；逐个字段/目标都要有分类、理由、来源与负责人。新版本源文件diff出现新/删/改字段、单位、类型、实体支持、错误定义，自动产生待审项。不得用“当前没采到”判定“不适用”。

**D. 交叉验证实际输入。** 对照Exporter原始/metrics（HELP/TYPE/labels）与Prometheus `/api/v1/metadata`、series/targets和查询样本，验证采集重标记、重复序列、scope、sentinel、类型配置。metadata并不能证明所有设备都持续提供字段，因此必须逐设备、逐依赖项检查。

**E. 逐目标形成证据链。** `官方依据→H100配置→有效字段→表达式→正常/故障/恢复/不可判断用例→夜莺→通知→处置`。缺少任一环只记录相应层级通过，不能合并成“已覆盖”。额外覆盖重置、stale、权限/不支持值、NaN/Inf、缺数据、查询失败、重复采集、标签变化、时间窗口边界、软件/规则切换及状态恢复。可用合成数据或历史回放验证逻辑，不能据此声称真实H100采集兼容。

**F. 使用多阶段指标，不给单一虚假总百分比。**

- 来源处置完整率 = 已明确分类且有理由的源字段/判据项 ÷ 冻结基线全部项（只度量清单有没有漏处理，不是故障检测率）。
- 适用性确认率 = 已有证据判适用或不适用的配置-目标项 ÷ 已审定配置-目标全集；unknown保留在分母。
- 实际可观察率 = 逐设备有效/新鲜输入齐全的适用目标项 ÷ 已确认适用目标项；同时公布未知项数和无输入项数，防止通过先排除unknown夸大覆盖。
- 规则实现率 = 已编写并审阅规则的alert目标 ÷ 已审定需alert目标；dashboard/context不硬凑成规则。
- 分别报告表达式边界、夜莺集成、真实H100采集/现场验证的通过数、总数和未运行数。高优先级故障目标单独列，不让大量性能仪表盘稀释关键缺口。

目前基线全集未冻结，除仓库实际1/1/0和单条测试数外，不应报告上述覆盖百分比。unknown大于0时不得称该配置已完整准入。

**G. 发布门禁。** P0/P1目标均有卡片/来源/处置结论；真正可执行的目标有现场字段证据和逐设备覆盖结果；关键规则具备失败输入/恢复用例及夜莺通知证据；明确缺输入、拒绝准入项和外部依赖；所有高风险缺口要补齐或经明确范围决策留作不支持。不能把“暂时不支持”从文档删除。物理H100首版的完整性不包含尚未准入的MIG实例级支持，但必须在范围中清楚展示这一排除。

**H. 防退化。** 固定来源diff、YAML/Markdown引用与参数一致性检查、规则-测试关联检查、每次目录/版本变化的回归和覆盖差异报告；改变适用范围或数据类型时要求重新审定而非沿用旧passed。现场统计告警误报/漏报和事后故障复盘，新增故障目标，不把初次冻结当永远完备。

### Gaps

- 任何未在遥测中留下可辨识信号、发生于采样间隙、输入丢失或需主动诊断/日志/作业语义的故障，都不能靠规则数量保证检测。需在矩阵保留为外部依赖/不可检测/未验证。
- 无真实GPU机器时可以建立并验证文档、字段清单、合成规则和状态机，但不能证明真实H100的权限、字段发出行为、DRAM/SRAM范围、MIG粒度和采样时效。
- 需要用户或目标环境提供脱敏硬件/软件清单和样本；在获取前最诚实的交付是“覆盖审查基线与缺口台账”，不是“完整H100生产规则库”。
