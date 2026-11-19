# A3 NPU监控指标与告警规则说明表

**修订：0.2（2026-11-17）；状态：研究初版，未生产准入。** 本文件是NPU指标分类、采集路径和候选规则的统一审阅入口，参考[GPU指标与规则主清单](../../../nvidia-gpu/rules/docs/14-GPU监控指标与告警规则说明表.md)的八类监控领域及六列主表编排。这里只继承组织方式，不继承NVIDIA字段、阈值、规则编号或验收结论。

本轮用户所称“DCGM”按华为**DCMI**理解；DCGM属于NVIDIA，不是本文件的华为采集路径。NPU Exporter自身也调用DCMI，所以“Exporter已有”和“DCMI可取得”不是互斥的底层能力集合。本表区分的是**现成导出路径**与**拟直接调用DCMI补充的信息**。

人工审阅以本文件为入口；[coverage.json](01-A3-NPU监控指标与告警规则说明表.coverage.json)从本文件生成，仅作分类/路径/引用校验。早期[26项YAML台账](../../common/catalog/metrics.yaml)和[12项规则候选](../candidates.yaml)是研究子集，不代表本表全量输入已实现或已同步成可执行规则；其unknown不得反向覆盖本轮已引用的官方定义。本文件也不是采集器、Prometheus规则文件或夜莺配置。

## 0. 版本、来源层级与全局契约

| 维度 | 初版约定 |
|---|---|
| 硬件 | Ascend A3物理芯片；Atlas900/9000/800T/800I/A200T Box8等整机支持不相同。整机尚未固定，条件能力必须逐机型准入。vNPU/软硬分区与租户隔离不自动继承。 |
| 软件 | 用户选定驱动26.1.x最新补丁、CANN 9.20暂按9.2.0理解；驱动精确补丁及配套固件待确认。Exporter文档所列26.2.0；证据源码多数来自master，未固定发行commit/digest，不将master实现直接声称为发行包验收结果。 |
| 已有的含义 | 源码或官方指标文档中存在字段/采集路径；不表示默认已开启、不表示该A3整机支持全部字段、更不表示现场已取得。 |
| 数值与单位 | 表内gauge仅指所阅路径或源语义；带_cnt名称不自动认counter。容量MB/MiB、速度MB/s与Mb/s、功率/电压换算未证实的保留待核实；不允许参与未验证阈值计算。 |
| 身份 | 候选物理键为job/instance/vdie_id，稳定性和唯一性待实机验证；card_id/device_id/logic_id/id不能混用。端口、lane、PCS等增加对应维度。容器标签不能定义物理芯片身份。 |
| 数据质量 | 缺失、陈旧、非法、sentinel、查询失败、不支持、未来/迟到样本及重复冲突分开处理；未知不补0，不用max/min掩盖冲突。能力不支持不是健康。 |
| 时间与采样 | 区分设备刷新、采集器缓存、Prometheus抓取及事件发生时间。TTL按实际分组周期定，不能照搬GPU90秒；26.2.0文档的network_link/optical可为600秒，详见[E-CONFIG](#source-e-config)。 |
| 判据与恢复 | 以下均为候选，未启用。T_health/T_input/T_up等由项目确认；60s/120s只是早期工程提案。温限、错误增长线、光功率等无官方/现场证据则留空，不编造阈值。无效/缺数不解除已有硬件事件。 |
| 故障码与事件 | 错误码快照、原始健康等级和事件流分别保留。事件记录持久化，含发生/恢复与去重身份；地址、自由文本描述不做高基数时序标签。 |
| 来源与规则依据 | 末列区分官方字段/故障定义与项目触发/恢复设计。项目没有验证过的PromQL和通知等级不冠以“华为推荐”。无作业信息时不以高占用/低活动直接判断卡死、泄漏或性能下降。 |

### 采集路径与证据状态

| 标记 | 路径 | 当前含义 |
|---|---|---|
| E | NPU Exporter已有 | 复用上游导出；底层可为DCMI或hccn_tool。源码证据与仅文档证据逐行标明。 |
| D | DCMI直接读取/补采候选 | 官方A3接口提供此信息；程序未实现。确认语义补采、已阅collector未见和Exporter覆盖待核对分开登记，**不统称Exporter完全没有**。 |
| X | 外部或项目派生 | Prometheus内置、资产清单、维护记录、输入质量与事件管线；不是DCMI硬件指标。 |

## 分类与采集路径总览

下表数字是本版**清单行数**：一行可包含多个同语义字段/端口模板/结构字段，不能当作独立指标总数或覆盖率。分类与采集路径正交；同一物理量能由Exporter取得时优先复用，不因DCMI也有接口重复计数。

| 类别 | Exporter已有E | DCMI补采/待核对D | 外部/派生X | 阅读入口 |
|---|---:|---:|---:|---|
| 资产、身份与配置 | 7 | 2 | 0 | [第1节](#category-1) |
| NPU健康、错误与维护 | 12 | 4 | 0 | [第2节](#category-2) |
| 资源容量与占用 | 5 | 0 | 0 | [第3节](#category-3) |
| 计算活动与性能信号 | 5 | 0 | 0 | [第4节](#category-4) |
| 内存访问与带宽信号 | 2 | 1 | 0 | [第5节](#category-5) |
| 温度、功耗与时钟 | 5 | 3 | 0 | [第6节](#category-6) |
| 互联与网络 | 11 | 4 | 0 | [第7节](#category-7) |
| 监控链路可靠性 | 0 | 0 | 4 | [第8节](#category-8) |
| 外部输入与排除项 | 0 | 0 | 2 | [第9节](#category-9) |

<a id="category-1"></a>

## 1. 资产、身份与配置

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.identity"></a>**设备身份**<br>metric_id：`ascend.identity`<br>字段/API：`id / model_name / vdie_id / pcie_bus_info（标签）`<br>类型/单位：metadata<br>状态：已有标签；稳定身份待实机验证 | **候选，未启用**；身份缺失、重复或冲突时阻塞设备判定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 定位物理芯片；id是索引，不直接当永久身份 | 采集身份不可靠，不能据此判断缺卡或卡坏 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.serial_number"></a>**板卡序列号**<br>metric_id：`ascend.serial_number`<br>字段/API：`npu_chip_info_serial_number`<br>类型/单位：info=1；serial_number标签<br>状态：源码已有，现场未验证 | **候选，未启用**；观测视图，不设通用故障阈值<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 序列号元数据；板卡与芯片关系待整机拓扑核对 | 用于追溯备件与设备，不以序列号变化自动判坏 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.product_type"></a>**产品形态**<br>metric_id：`ascend.product_type`<br>字段/API：`npu_chip_info_product_type`<br>类型/单位：info=1；product_type标签<br>状态：源码已有，现场未验证 | **候选，未启用**；观测与能力准入视图<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 决定同为A3时不同机型的接口支持 | 未识别形态则相关能力保持unknown | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.node_versions"></a>**驱动与DCMI版本**<br>metric_id：`ascend.node_versions`<br>字段/API：`node_base_info`<br>类型/单位：info；driverVersion / dcmiVersion / exporterVersion标签<br>状态：源码已有，现场未验证 | **候选，未启用**；与批准版本不符时报告配置偏差，不直接判硬件故障<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 实际版本背景，不等同CANN版本 | 版本契约不满足或信息缺失 | [E-NODE](#source-e-node) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.exporter_version"></a>**Exporter版本**<br>metric_id：`ascend.exporter_version`<br>字段/API：`npu_exporter_version_info`<br>类型/单位：info=1<br>状态：源码已有，现场未验证 | **候选，未启用**；版本视图与配置审查<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 采集器版本 | 用于追踪字段和配置变化 | [E-VERSION](#source-e-version) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.visible_npu_count"></a>**当前可见芯片数**<br>metric_id：`ascend.visible_npu_count`<br>字段/API：`machine_npu_nums`<br>类型/单位：gauge；count<br>状态：源码已有，现场未验证 | **候选，未启用**；仅与独立预期资产清单比较；不可把当前值作为预期<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 当前枚举结果，非期望资产容量 | 数量下降需区分维护、驱动枚举与掉卡 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.visible_card_count"></a>**当前可见板卡数**<br>metric_id：`ascend.visible_card_count`<br>字段/API：`machine_card_nums`<br>类型/单位：gauge；count<br>状态：源码已有，现场未验证 | **候选，未启用**；与预期板卡清单比较，不推定一板等于一芯片<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 板卡数，与芯片数分开 | 资产枚举偏差，需结合物理身份 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

### D：DCMI可取得的补采项与覆盖待核对项

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.topology"></a>**芯片互联拓扑**<br>metric_id：`ascend.topology`<br>字段/API：`dcmi_get_topo_info_by_device_id`<br>类型/单位：enum / metadata<br>状态：DCMI可查询；Exporter等价输出待核对 | **候选，未启用**；与批准拓扑不符才报告；静态事实不设数值阈值<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | SELF/SYS/PHB/HCCS/PCIe/SIO等关系 | 定位链路/芯片映射偏差，不能据拓扑直接判链路实时健康 | [D-TOPO](#source-d-topo) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.cpu_affinity"></a>**CPU亲和性**<br>metric_id：`ascend.cpu_affinity`<br>字段/API：`DCMI CPU亲和性查询，具体声明见接口页`<br>类型/单位：bitmap / metadata<br>状态：条件候选：支持表仅Box8；其他列出机型不适用 | **候选，未启用**；仅支持机型纳入亲和视图<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 芯片与CPU绑定关系 | 性能定位上下文，不设置硬件故障告警 | [D-AFFINITY](#source-d-affinity) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
<a id="category-2"></a>

## 2. NPU健康、错误与维护

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.health_binary"></a>**芯片健康二值**<br>metric_id：`ascend.health_binary`<br>字段/API：`npu_chip_info_health_status`<br>类型/单位：gauge；1健康 / 0不健康<br>状态：源码已有，现场未验证 | **候选，未启用**；有效值==0持续T_health；暂定60s，仅工程提案<br>恢复：有效值==1连续2轮是候选必要条件；还需活动故障清除及对应处置证据 | Exporter将DCMI原始非零等级合并，不能用0=正常的DCMI枚举解释 | 芯片被判不健康，但不能单凭该值分Warning/Alarm/Critical | [E-NPU](#source-e-npu)；[D-HEALTH](#source-d-health) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.healthy_count"></a>**节点健康芯片数**<br>metric_id：`ascend.healthy_count`<br>字段/API：`machine_healthy_npu_nums`<br>类型/单位：gauge；count<br>状态：源码已有，现场未验证 | **候选，未启用**；与总数、未知、不健康数量交叉核对<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 健康数量视图 | 健康状态或采集覆盖异常，未知不能按健康处理 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.unhealthy_count"></a>**节点不健康芯片数**<br>metric_id：`ascend.unhealthy_count`<br>字段/API：`machine_unhealthy_npu_nums`<br>类型/单位：gauge；count<br>状态：源码已有，现场未验证 | **候选，未启用**；有效值>0持续T_health<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 节点存在不健康芯片；定位仍依赖逐芯片身份 | 健康状态或采集覆盖异常，未知不能按健康处理 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.unknown_count"></a>**节点健康未知芯片数**<br>metric_id：`ascend.unknown_count`<br>字段/API：`machine_unknown_npu_nums`<br>类型/单位：gauge；count<br>状态：源码已有，现场未验证 | **候选，未启用**；有效值>0持续T_input<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | DCMI健康查询未知，区别于硬件不健康 | 健康状态或采集覆盖异常，未知不能按健康处理 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.fault_code_snapshot"></a>**当前故障码快照**<br>metric_id：`ascend.fault_code_snapshot`<br>字段/API：`npu_chip_info_error_code / npu_chip_info_error_code_X`<br>类型/单位：gauge承载code；有限槽位<br>状态：源码已有，现场未验证 | **候选，未启用**；按产品/HDK故障字典分类，不能按码数值大小分级<br>恢复：查询成功、完整性与活动故障清除均需确认；空数组/序列消失不自动解除 | 当前错误集合的有限快照；槽位换位不等于新增事件 | 提示当前故障，不能推出完整发生/恢复次数或事件历史 | [E-NPU](#source-e-npu)；[FAULTS](#source-faults) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_enable"></a>**HBM ECC开关**<br>metric_id：`ascend.ecc_enable`<br>字段/API：`npu_chip_info_hbm_ecc_enable_flag`<br>类型/单位：gauge；enum，合法值需按头文件核实<br>状态：源码已有，现场未验证 | **候选，未启用**；配置视图；与批准配置不符才告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | ECC检测使能背景 | 缺失不是ECC关闭，关闭也不直接代表芯片损坏 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_single_bit_error_cnt"></a>**实时单比特错误**<br>metric_id：`ascend.ecc_single_bit_error_cnt`<br>字段/API：`npu_chip_info_hbm_ecc_single_bit_error_cnt`<br>类型/单位：gauge承载累计计数；count<br>状态：源码已有，现场未验证 | **候选，未启用**；验证重置后观察增量/频率；多比特新增结合故障码复核；增长阈值待定<br>恢复：不要求历史值回零；依新鲜有效输入、活动故障清除和官方复核证据 | 实时计数系统重启清零；total为生命周期累计，不能混用窗口 | 错误增长或历史诊断信号；历史>0不等于当前故障 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_double_bit_error_cnt"></a>**实时多比特错误**<br>metric_id：`ascend.ecc_double_bit_error_cnt`<br>字段/API：`npu_chip_info_hbm_ecc_double_bit_error_cnt`<br>类型/单位：gauge承载累计计数；count<br>状态：源码已有，现场未验证 | **候选，未启用**；验证重置后观察增量/频率；多比特新增结合故障码复核；增长阈值待定<br>恢复：不要求历史值回零；依新鲜有效输入、活动故障清除和官方复核证据 | 实时计数系统重启清零；total为生命周期累计，不能混用窗口 | 错误增长或历史诊断信号；历史>0不等于当前故障 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_total_single_bit_error_cnt"></a>**生命周期单比特错误**<br>metric_id：`ascend.ecc_total_single_bit_error_cnt`<br>字段/API：`npu_chip_info_hbm_ecc_total_single_bit_error_cnt`<br>类型/单位：gauge承载累计计数；count<br>状态：源码已有，现场未验证 | **候选，未启用**；验证重置后观察增量/频率；多比特新增结合故障码复核；增长阈值待定<br>恢复：不要求历史值回零；依新鲜有效输入、活动故障清除和官方复核证据 | 实时计数系统重启清零；total为生命周期累计，不能混用窗口 | 错误增长或历史诊断信号；历史>0不等于当前故障 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_total_double_bit_error_cnt"></a>**生命周期多比特错误**<br>metric_id：`ascend.ecc_total_double_bit_error_cnt`<br>字段/API：`npu_chip_info_hbm_ecc_total_double_bit_error_cnt`<br>类型/单位：gauge承载累计计数；count<br>状态：源码已有，现场未验证 | **候选，未启用**；验证重置后观察增量/频率；多比特新增结合故障码复核；增长阈值待定<br>恢复：不要求历史值回零；依新鲜有效输入、活动故障清除和官方复核证据 | 实时计数系统重启清零；total为生命周期累计，不能混用窗口 | 错误增长或历史诊断信号；历史>0不等于当前故障 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_single_isolated_pages"></a>**单比特隔离页**<br>metric_id：`ascend.ecc_single_isolated_pages`<br>字段/API：`npu_chip_info_hbm_ecc_single_bit_isolated_pages_cnt`<br>类型/单位：gauge；pages<br>状态：已有字段；A3预留，不纳入有效故障能力计数 | **候选，未启用**；A3文档为预留固定0，不作为有效故障检测项<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 字段存在与硬件有实际信息量是两回事 | 非零先报契约偏差；不能建立虚假的单比特隔离页告警 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_double_isolated_pages"></a>**多比特隔离页**<br>metric_id：`ascend.ecc_double_isolated_pages`<br>字段/API：`npu_chip_info_hbm_ecc_double_bit_isolated_pages_cnt`<br>类型/单位：gauge；pages<br>状态：源码已有，现场未验证 | **候选，未启用**；变化结合健康管理故障码复核；硬件上限不自定<br>恢复：隔离页可保留；依官方故障解除及复核，不强制页数归零 | 已隔离内存页面背景 | 存在隔离/容量影响；不能把任何历史隔离都定紧急故障 | [E-HBM](#source-e-hbm)；[D-ECC](#source-d-ecc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |

### D：DCMI可取得的补采项与覆盖待核对项

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.health_level"></a>**原始芯片健康等级**<br>metric_id：`ascend.health_level`<br>字段/API：`dcmi_get_device_health`<br>类型/单位：enum；0正常 / 1一般 / 2重要 / 3紧急 / 0xFFFFFFFF不存在<br>状态：确认语义补采：Exporter二值无法还原等级 | **候选，未启用**；1/2/3按官方等级分别产生候选告警；不存在进资产/输入异常<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 保留Exporter二值化丢失的原始级别 | 可分级处置；项目通知等级映射仍需审定 | [D-HEALTH](#source-d-health)；[E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.driver_health"></a>**驱动健康**<br>metric_id：`ascend.driver_health`<br>字段/API：`dcmi_get_driver_health`<br>类型/单位：enum；0正常 / 3紧急；其他预留<br>状态：DCMI可读；Exporter等价项待核对 | **候选，未启用**；有效活动值3触发驱动健康告警；确认窗口待定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 独立于芯片健康的驱动状态 | 驱动层健康异常，不推定单块硬件损坏 | [D-DRIVER](#source-d-driver) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.fault_event"></a>**故障发生与恢复事件**<br>metric_id：`ascend.fault_event`<br>字段/API：`dcmi_subscribe_fault_event；或dcmi_get_fault_event（二选一）`<br>类型/单位：event；含severity/assertion/时间/设备/序号<br>状态：确认事件语义补采；需事件存储，非普通gauge | **候选，未启用**；按官方事件级别与assertion建立发生/保持/恢复状态机<br>恢复：只接受匹配当前事件的有效恢复记录/官方复核；订阅断档保留未知，不宣告恢复 | 订阅后实时事件，非历史补账；与轮询码快照分开 | 完整事件生命周期；轮询失败不能伪造清除 | [D-EVENT](#source-d-event)；[E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.ecc_address_record"></a>**ECC地址级记录**<br>metric_id：`ascend.ecc_address_record`<br>字段/API：`dcmi_get_multi_ecc_record_info_v2`<br>类型/单位：record；地址/bank/stack/次数/时间<br>状态：HBM采集器已阅未输出；全发行包覆盖仍待核对 | **候选，未启用**；重复地址、多比特或位置聚集按官方策略复核；阈值待定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 定位具体地址和存储区域；已有汇总ECC不重复采集 | 深层故障定位，不用物理地址做无限增长标签 | [D-ECC-RECORD](#source-d-ecc-record)；[E-HBM](#source-e-hbm) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
<a id="category-3"></a>

## 3. 资源容量与占用

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.hbm_used"></a>**HBM已用容量**<br>metric_id：`ascend.hbm_used`<br>字段/API：`npu_chip_info_hbm_used_memory`<br>类型/单位：gauge；源容量单位待固定版核实<br>状态：源码已有，现场未验证 | **候选，未启用**；容量展示；总量>0且已用<=总量，单位一致才允许计算占比<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 物理HBM容量事实，不是带宽利用率 | 容量紧张提示，不单独判断泄漏、作业失败或卡坏 | [E-HBM](#source-e-hbm) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.hbm_total"></a>**HBM总容量**<br>metric_id：`ascend.hbm_total`<br>字段/API：`npu_chip_info_hbm_total_memory`<br>类型/单位：gauge；源容量单位待固定版核实<br>状态：源码已有，现场未验证 | **候选，未启用**；容量展示；总量>0且已用<=总量，单位一致才允许计算占比<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 物理HBM容量事实，不是带宽利用率 | 容量紧张提示，不单独判断泄漏、作业失败或卡坏 | [E-HBM](#source-e-hbm) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.process_count"></a>**设备进程数**<br>metric_id：`ascend.process_count`<br>字段/API：`npu_chip_info_process_info_num`<br>类型/单位：gauge；count<br>状态：源码已有，现场未验证 | **候选，未启用**；视图，不以进程数0判断设备故障<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 当前设备进程数量 | 无业务预期时0可能是空闲 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.process_memory"></a>**进程内存**<br>metric_id：`ascend.process_memory`<br>字段/API：`npu_chip_info_process_info`<br>类型/单位：gauge；HELP标MB，MB/MiB换算待验证<br>状态：源码已有，现场未验证 | **候选，未启用**；观测视图；进程PID重用不能连接为同一生命周期<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 进程占用内存；关联process_id/container_id | 定位占用，不据持续高值直接断言内存泄漏 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.container_memory"></a>**容器内存归属**<br>metric_id：`ascend.container_memory`<br>字段/API：`container_npu_total_memory / container_npu_used_memory`<br>类型/单位：gauge；HELP标MB；容器维度<br>状态：已有容器视图；不纳入首版物理设备必选输入 | **候选，未启用**；条件视图；CRI归属有效时启用，不能跨容器重复求和<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 按容器设备分配关联，不保证等同独立物理资源配额 | 租户/容器归属上下文；不能直接当物理卡唯一观测 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

**派生容量比：**同物理身份、同采样时间、单位一致且0≤used≤total、total>0时计算used/total。该比值属于项目派生，不伪造为上游原始指标；预警线与恢复迟滞未审定，不启用容量告警。
<a id="category-4"></a>

## 4. 计算活动与性能信号

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.utilization"></a>**AI Core利用率**<br>metric_id：`ascend.utilization`<br>字段/API：`npu_chip_info_utilization`<br>类型/单位：gauge；百分比，采样/分母按固定版接口确认<br>状态：A3采集路径已有；Cube依新接口，回退路径不能假定有效 | **候选，未启用**；观测和基线分析；不默认设置低利用率故障告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 不同计算单元/整体活动信号，不是算力效率或业务吞吐 | 无作业信息不能判断卡死、浪费或业务性能下降 | [E-UTIL](#source-e-util) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.overall_utilization"></a>**NPU整体利用率**<br>metric_id：`ascend.overall_utilization`<br>字段/API：`npu_chip_info_overall_utilization`<br>类型/单位：gauge；百分比，采样/分母按固定版接口确认<br>状态：A3采集路径已有；Cube依新接口，回退路径不能假定有效 | **候选，未启用**；观测和基线分析；不默认设置低利用率故障告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 不同计算单元/整体活动信号，不是算力效率或业务吞吐 | 无作业信息不能判断卡死、浪费或业务性能下降 | [E-UTIL](#source-e-util) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.vector_utilization"></a>**Vector利用率**<br>metric_id：`ascend.vector_utilization`<br>字段/API：`npu_chip_info_vector_utilization`<br>类型/单位：gauge；百分比，采样/分母按固定版接口确认<br>状态：A3采集路径已有；Cube依新接口，回退路径不能假定有效 | **候选，未启用**；观测和基线分析；不默认设置低利用率故障告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 不同计算单元/整体活动信号，不是算力效率或业务吞吐 | 无作业信息不能判断卡死、浪费或业务性能下降 | [E-UTIL](#source-e-util) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.cube_utilization"></a>**Cube利用率**<br>metric_id：`ascend.cube_utilization`<br>字段/API：`npu_chip_info_cube_utilization`<br>类型/单位：gauge；百分比，采样/分母按固定版接口确认<br>状态：A3采集路径已有；Cube依新接口，回退路径不能假定有效 | **候选，未启用**；观测和基线分析；不默认设置低利用率故障告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 不同计算单元/整体活动信号，不是算力效率或业务吞吐 | 无作业信息不能判断卡死、浪费或业务性能下降 | [E-UTIL](#source-e-util) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.container_utilization"></a>**容器计算利用率**<br>metric_id：`ascend.container_utilization`<br>字段/API：`container_npu_utilization`<br>类型/单位：gauge；%<br>状态：已有容器视图；vNPU不自动适用 | **候选，未启用**；条件视图；不能将同卡多容器值简单相加<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 容器关联的AI Core活动 | 不是独立硬件故障判据 | [E-UTIL](#source-e-util) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
<a id="category-5"></a>

## 5. 内存访问与带宽信号

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.hbm_utilization"></a>**HBM利用率**<br>metric_id：`ascend.hbm_utilization`<br>字段/API：`npu_chip_info_hbm_utilization`<br>类型/单位：gauge；分母/单位待接口核实<br>状态：源码已有，现场未验证 | **候选，未启用**；先展示，语义明确前不代替容量占比<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 通过HbmUtilization接口取得，与Usage/MemorySize不同来源 | 不能单凭高值判容量耗尽或memory-bound | [E-HBM](#source-e-hbm) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.hbm_bandwidth_utilization"></a>**HBM带宽利用率**<br>metric_id：`ascend.hbm_bandwidth_utilization`<br>字段/API：`npu_chip_info_hbm_bandwidth_utilization`<br>类型/单位：gauge；归一化口径待固定接口核实<br>状态：源码已有，现场未验证 | **候选，未启用**；趋势视图，阈值随采样和业务基线制定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 内存带宽活动，与容量占用分开 | 高活动不等于故障，也不等于精确bytes/s | [E-HBM](#source-e-hbm) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

### D：DCMI可取得的补采项与覆盖待核对项

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.llc_performance"></a>**LLC缓存性能**<br>metric_id：`ascend.llc_performance`<br>字段/API：`dcmi_get_device_llc_perf_para`<br>类型/单位：read/write hit rate：%；吞吐：KB/s（源口径）<br>状态：DCMI可读；Exporter等价项待核对；部分AVI不支持 | **候选，未启用**；性能诊断视图，不设置统一故障阈值<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | LLC命中率与吞吐，非HBM容量/带宽替代项 | 定位访存特征，单独不能证明硬件故障 | [D-LLC](#source-d-llc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
<a id="category-6"></a>

## 6. 温度、功耗与时钟

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.temperature"></a>**芯片温度**<br>metric_id：`ascend.temperature`<br>字段/API：`npu_chip_info_temperature`<br>类型/单位：gauge；温度单位待固定版核实<br>状态：源码已有，现场未验证 | **候选，未启用**；超过机型官方限值且持续T_thermal；温限/恢复迟滞暂空<br>恢复：低于机型恢复线持续T_recover并确认有效新鲜；参数未核定不启用 | 当前温度信号 | 散热或运行环境异常候选；需结合设备保护状态 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.hbm_temperature"></a>**HBM温度**<br>metric_id：`ascend.hbm_temperature`<br>字段/API：`npu_chip_info_hbm_temperature`<br>类型/单位：gauge；温度单位待固定版核实<br>状态：源码已有，现场未验证 | **候选，未启用**；超过机型官方限值且持续T_thermal；温限/恢复迟滞暂空<br>恢复：低于机型恢复线持续T_recover并确认有效新鲜；参数未核定不启用 | 当前温度信号 | 散热或运行环境异常候选；需结合设备保护状态 | [E-HBM](#source-e-hbm) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.power"></a>**实时功率**<br>metric_id：`ascend.power`<br>字段/API：`npu_chip_info_power`<br>类型/单位：gauge；功率换算与粒度待核实<br>状态：源码已有，现场未验证 | **候选，未启用**；趋势视图；只有官方界限/原因依据齐备才制定告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 功率、电压与时钟状态；不等于额定值或节流原因 | 频率低可能空闲；功率高不直接判供电故障 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.voltage"></a>**电压**<br>metric_id：`ascend.voltage`<br>字段/API：`npu_chip_info_voltage`<br>类型/单位：gauge；源电压单位待核实<br>状态：源码已有，现场未验证 | **候选，未启用**；趋势视图；只有官方界限/原因依据齐备才制定告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 功率、电压与时钟状态；不等于额定值或节流原因 | 频率低可能空闲；功率高不直接判供电故障 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.aicore_frequency"></a>**AI Core频率**<br>metric_id：`ascend.aicore_frequency`<br>字段/API：`npu_chip_info_aicore_current_freq`<br>类型/单位：gauge；MHz<br>状态：源码已有，现场未验证 | **候选，未启用**；趋势视图；只有官方界限/原因依据齐备才制定告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 功率、电压与时钟状态；不等于额定值或节流原因 | 频率低可能空闲；功率高不直接判供电故障 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

### D：DCMI可取得的补采项与覆盖待核对项

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.throttle_reason"></a>**AI Core降频原因**<br>metric_id：`ascend.throttle_reason`<br>字段/API：`dcmi_get_device_info：DCMI_MAIN_CMD_LP / AICORE_FREQREDUC_CAUSE`<br>类型/单位：uint64 bitmask；100ms更新、无历史<br>状态：DCMI可读；常规采集路径未见，全包仍待核对 | **候选，未启用**；按已知位分别处理；THERMAL等结合温度/功率；IDLE不视为故障<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 区分空闲、热、功率限制等原因，不能按位掩码数值排序 | 性能受限原因；功率封顶可能是策略行为 | [D-LP](#source-d-lp) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.rated_power"></a>**SOC额定功率**<br>metric_id：`ascend.rated_power`<br>字段/API：`dcmi_get_device_info：DCMI_MAIN_CMD_LP / GET_POWER_INFO`<br>类型/单位：metadata；单位/换算按固定头文件核实<br>状态：DCMI可读；Exporter等价项待核对 | **候选，未启用**；配置背景视图，不与瞬时功率混用<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 额定功率信息，不是瞬时功耗 | 用于功率配置核对 | [D-LP](#source-d-lp) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.sensor_temperatures"></a>**扩展温度传感器**<br>metric_id：`ascend.sensor_temperatures`<br>字段/API：`dcmi_get_device_sensor_info：A3仅sensor 11—14`<br>类型/单位：SOC最高温/光模块最高温/N_DIE温度/HBM最高温；单位待核实<br>状态：条件补采；光模块/HBM存在已有等价信息，禁止重复计覆盖 | **候选，未启用**；同语义已由Exporter提供则复用；否则按机型温限补采<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 不能把枚举中其他sensor都当A3支持 | 细分散热定位；-8008、0x7EFF等需区别无模块/不支持 | [D-SENSOR](#source-d-sensor) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
<a id="category-7"></a>

## 7. 互联与网络

### E：NPU Exporter已有指标

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.hccs_packets"></a>**HCCS收发计数**<br>metric_id：`ascend.hccs_packets`<br>字段/API：`HCCS tx_cnt_<port> / rx_cnt_<port>（完整Prometheus前缀待固定版映射）`<br>类型/单位：gauge承载计数；count<br>状态：源码已有，现场未验证 | **候选，未启用**；流量视图；零流量不等于断链<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | GetHccsStatisticInfo*；端口按机型从1或2开始 | 通信活动背景，不能当有效链路数 | [E-HCCS](#source-e-hccs) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.hccs_crc"></a>**HCCS CRC错误**<br>metric_id：`ascend.hccs_crc`<br>字段/API：`HCCS crc_err_cnt_<port>（完整前缀待映射）`<br>类型/单位：gauge承载计数；count<br>状态：源码已有，现场未验证 | **候选，未启用**；校验sentinel/reset后对新增CRC按窗口告警；阈值待定<br>恢复：有效窗口不再增长仅代表安静；还需预期链路健康与故障复核 | 端口错误计数，与收发数量分开 | 链路质量异常候选，不直接判根因 | [E-HCCS](#source-e-hccs) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.hccs_bandwidth"></a>**HCCS收发带宽**<br>metric_id：`ascend.hccs_bandwidth`<br>字段/API：`HCCS BW tx_<port> / rx_<port> / total_tx / total_rx / profiling_time（完整前缀待映射）`<br>类型/单位：gauge；带宽/采样间隔单位待核实<br>状态：源码已有，现场未验证 | **候选，未启用**；视图；方向/汇总不能重复求和<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | GetHccsBandwidthInfo的逐链路、汇总带宽与采样区间 | 不能单凭低带宽判互联故障 | [E-HCCS](#source-e-hccs) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.sio_crc_tx"></a>**SIO TX CRC错误**<br>metric_id：`ascend.sio_crc_tx`<br>字段/API：`npu_chip_info_sio_crc_tx_err_cnt`<br>类型/单位：gauge/实际TYPE待发行版核对；count<br>状态：官方指标文档已有A3范围；未取得完整SIO源码 | **候选，未启用**；确认计数与reset后按增长窗口检测；阈值待定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | SIO方向CRC错误 | 本地互联质量候选；不直接等于全Fabric不可用 | [E-METRICS](#source-e-metrics) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.sio_crc_rx"></a>**SIO RX CRC错误**<br>metric_id：`ascend.sio_crc_rx`<br>字段/API：`npu_chip_info_sio_crc_rx_err_cnt`<br>类型/单位：gauge/实际TYPE待发行版核对；count<br>状态：官方指标文档已有A3范围；未取得完整SIO源码 | **候选，未启用**；确认计数与reset后按增长窗口检测；阈值待定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | SIO方向CRC错误 | 本地互联质量候选；不直接等于全Fabric不可用 | [E-METRICS](#source-e-metrics) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.network_health"></a>**芯片网络健康**<br>metric_id：`ascend.network_health`<br>字段/API：`npu_chip_info_network_status`<br>类型/单位：gauge；1健康 / 0不健康（Exporter映射）<br>状态：源码已有，现场未验证 | **候选，未启用**；仅在预期使用网络的场景，有效0持续T_network<br>恢复：新鲜健康值、预期链路及相关事件恢复共同复核 | 设备网络健康汇总，不替代每端口Link状态 | 网络异常候选；未使用网络不自动告警 | [E-NPU](#source-e-npu) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.network_link"></a>**网口链路状态**<br>metric_id：`ascend.network_link`<br>字段/API：`npu_chip_info_link_status`<br>类型/单位：enum；0/1含义需按固定版核实<br>状态：文档已有；端口身份及枚举待发行版验证 | **候选，未启用**；预期启用端口不处于UP持续T_link才告警<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | hccn_tool采集；与网络汇总健康字段分开 | 预期链路中断；不对未用/维护端口报故障 | [E-METRICS](#source-e-metrics)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.network_speed"></a>**网口速率及重连**<br>metric_id：`ascend.network_speed`<br>字段/API：`npu_chip_link_speed / npu_chip_link_up_num`<br>类型/单位：speed单位存在历史文档差异，待核实；up_num为计数<br>状态：源码已有，现场未验证 | **候选，未启用**；与预期速率比较或观察重连增长；reset/单位验证后启用<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 速率配置/协商与Link UP次数，不是实时吞吐 | 潜在降速/抖动；不能仅计数>0永久告警 | [E-METRICS](#source-e-metrics)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.network_bandwidth"></a>**网口收发吞吐**<br>metric_id：`ascend.network_bandwidth`<br>字段/API：`npu_chip_info_bandwidth_tx / npu_chip_info_bandwidth_rx`<br>类型/单位：gauge；HELP标MB/s，十进制/二进制口径待核实<br>状态：源码已有，现场未验证 | **候选，未启用**；吞吐视图；不得再次rate，零吞吐不等于链路故障<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | hccn_tool采集的实时方向速率 | 只反映流量，需结合链路及业务预期解释 | [E-METRICS](#source-e-metrics)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.roce_mac"></a>**RoCE/MAC错误与拥塞**<br>metric_id：`ascend.roce_mac`<br>字段/API：`npu_chip_roce_rx_err_pkt_num / npu_chip_roce_tx_err_pkt_num / npu_chip_mac_rx_bad_pkt_num / npu_chip_mac_tx_bad_pkt_num；另含CNP/PFC等组内字段`<br>类型/单位：计数；TYPE/reset逐字段核实<br>状态：文档已有分组；代表字段非完整字段全集 | **候选，未启用**；按错误增长与业务/网络基线检测；CNP/PFC不直接等于故障<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | Exporter已有RoCE/MAC分组；尚未将组内所有字段逐项展开 | 错误/拥塞信号，不能单独证明交换机或NPU损坏 | [E-METRICS](#source-e-metrics)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.optical"></a>**光模块状态与遥测**<br>metric_id：`ascend.optical`<br>字段/API：`npu_chip_optical_state / npu_chip_optical_temp / npu_chip_optical_vcc / npu_chip_optical_tx_power_<lane> / npu_chip_optical_rx_power_<lane>`<br>类型/单位：状态/温度/电压/光功率；单位/枚举待固定版核实<br>状态：文档已有；具体A3产品/模块支持需核实 | **候选，未启用**；仅有预期光模块时，按模块厂家/机型阈值与状态判断<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | hccn_tool采集；铜缆/不存在模块不按缺数告硬件故障 | 模块健康与光路质量；不套用统一光功率阈值 | [E-METRICS](#source-e-metrics)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

### D：DCMI可取得的补采项与覆盖待核对项

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.hccs_credit"></a>**HCCS可用信用**<br>metric_id：`ascend.hccs_credit`<br>字段/API：`dcmi_get_hccs_avail_credit_info`<br>类型/单位：count；16个PCS<br>状态：已阅HCCS采集器未输出；全发行包待核对 | **候选，未启用**；先做诊断视图；阈值、采样窗口和PCS映射待定<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 与已有吞吐/CRC不同的信用状态 | 拥塞与流控定位，低信用不直接判断断链 | [D-CREDIT](#source-d-credit)；[E-HCCS](#source-e-hccs) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.serdes_quality"></a>**SerDes眼图质量**<br>metric_id：`ascend.serdes_quality`<br>字段/API：`dcmi_get_serdes_quality_info`<br>类型/单位：macro/lane；SNR/HEH等，依SerDes型号<br>状态：条件补采；h32仅Box8，完整适用性见官方页 | **候选，未启用**；仅按机型/SerDes有效字段与官方限值判断<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | h60与h32字段不同；断口全0不表示健康 | 物理层质量诊断；未知字段不做通用阈值 | [D-SERDES](#source-d-serdes) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.pcie_errors"></a>**PCIe错误计数**<br>metric_id：`ascend.pcie_errors`<br>字段/API：`dcmi_get_device_info：DCMI_MAIN_CMD_PCIE / PCIE_ERROR_INFO`<br>类型/单位：tx/rx/lcrc/ecrc/retry；count<br>状态：仅Box8候选；Atlas900/9000/800T/800I A3支持表为N | **候选，未启用**；仅支持机型，在计数窗口/reset核实后检测增长<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | PCIe错误，不是Exporter PCIe带宽；后者源码无A3支持表项 | PCIe链路质量；不能扩展到所有A3 | [D-PCIE](#source-d-pcie)；[E-PCIE](#source-e-pcie) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。故障解释须匹配[官方故障码](#source-faults)的型号与HDK版本。 |
| <a id="m-ascend.pfc_duration"></a>**PFC暂停持续时间**<br>metric_id：`ascend.pfc_duration`<br>字段/API：`dcmi_get_pfc_duration_info`<br>类型/单位：8优先级tx/rx时长；源单位待核实<br>状态：条件候选：Atlas9000 A3不支持；Exporter等价项待核对 | **候选，未启用**；与已有PFC包计数分开；归一化窗口后按基线分析<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 暂停时长和暂停包数量不是同一指标 | 拥塞定位，非直接硬件故障 | [D-PFC](#source-d-pfc) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

**覆盖说明：**HCCS完整指标前缀仍须从固定发行版本解析，不把此处语义模板直接当作可执行PromQL。RoCE和光模块当前按组与代表字段登记，尚非全字段展开表。A3 PCIe带宽不得从910B/910A5的Exporter支持推导；PCIe错误仅按对应DCMI整机支持表准入。
<a id="category-8"></a>

## 8. 监控链路可靠性

### X：外部及项目派生输入

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.target_up"></a>**Exporter抓取状态**<br>metric_id：`ascend.target_up`<br>字段/API：`up{job="ascend-npu-exporter"}`<br>类型/单位：gauge；0/1<br>状态：外部/派生输入，未接入 | **候选，未启用**；0持续T_up，暂定120s；target消失需独立清单检测<br>恢复：抓取连续成功2轮；底层接口是否恢复需独立验证 | Prometheus内置，不是Exporter/DCMI硬件字段 | HTTP抓取失败，不证明DCMI失效的具体原因 | [E-METRICS](#source-e-metrics) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.collector_success"></a>**逐接口采集成功**<br>metric_id：`ascend.collector_success`<br>字段/API：`项目计划字段：collector_success / last_success_time / error_reason（未实现，不是上游原名）`<br>类型/单位：boolean / 时间 / error enum<br>状态：项目自研质量输入；不能称DCMI内置指标 | **候选，未启用**；失败或距离最后成功超过该组TTL，进入输入异常<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 区分HTTP抓取、接口成功与缓存新鲜度 | 防止旧缓存、空错误码被误当健康或恢复 | [E-COMMON](#source-e-common)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.required_input"></a>**必需字段缺失/非法/重复/陈旧**<br>metric_id：`ascend.required_input`<br>字段/API：`项目派生：expected field / validity / duplicate / freshness`<br>类型/单位：派生状态<br>状态：外部/派生输入，未接入 | **候选，未启用**；按已声明型号能力和采样周期判断；拒绝sentinel、冲突及非有限数<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 输入契约可靠性，不是硬件状态 | 受影响硬件规则暂不执行或保持未知，不自动清除活动事件 | [E-COMMON](#source-e-common)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.event_continuity"></a>**事件订阅连续性**<br>metric_id：`ascend.event_continuity`<br>字段/API：`项目计划：订阅状态 / 断档 / 持久化进度 / 去重状态`<br>类型/单位：event pipeline metadata<br>状态：外部/派生输入，未接入 | **候选，未启用**；订阅异常、进程重启或存储失败报告事件覆盖缺口<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | DCMI不能回补订阅前历史，连续性由自研负责 | 不允许因事件通道断开就宣告设备恢复 | [D-EVENT](#source-d-event) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
<a id="category-9"></a>

## 9. 外部输入与排除项

### X：外部及项目派生输入

| 监控指标 | 告警规则（触发条件） | 监控指标代表的意义 | 告警规则触发代表什么意义 | 监控指标的来源 | 告警规则的来源 |
|---|---|---|---|---|---|
| <a id="m-ascend.expected_inventory"></a>**预期资产与链路清单**<br>metric_id：`ascend.expected_inventory`<br>字段/API：`外部CMDB/配置：expected_device / expected_link / expected_speed`<br>类型/单位：metadata<br>状态：外部/派生输入，未接入 | **候选，未启用**；实际观测与独立预期不符持续T_missing才检测<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 不能用当前枚举结果反向制造期望值 | 缺卡、链路缺失和速率偏差判据的前提 | [E-NPU](#source-e-npu)；[E-CONFIG](#source-e-config) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |
| <a id="m-ascend.maintenance"></a>**维护与处置恢复确认**<br>metric_id：`ascend.maintenance`<br>字段/API：`外部维护记录、运维确认与审计`<br>类型/单位：state / event<br>状态：外部/派生输入，未接入 | **候选，未启用**；绑定设备、当前事件和有效期；管理禁用不等于硬件恢复<br>恢复：恢复需新鲜、有效、身份一致的观测；缺数不作为恢复 | 维护窗口、退役和受控复核上下文 | 避免维护误报，保持原始事件可追溯 | [FAULTS](#source-faults) | 项目制定触发/窗口/恢复策略；字段含义依据左列官方来源。 |

**排除范围：**set/clear/reset/upgrade/create/start/stop、故障注入、PRBS/压力测试等控制或主动诊断，不计为常态只读监控指标。CANN/应用算子耗时、HCCL作业性能、业务成功率及交换机/整机风扇电源并非本文DCMI可读性的自然延伸，需单独数据源与范围。

## 10. 候选规则采用与实施顺序

| 阶段 | 选择的指标/输入 | 候选规则及采用理由 | 阻塞项 |
|---|---|---|---|
| P0：输入契约 | E身份/数量；X预期资产、质量、抓取与时间 | Exporter不可达、必需输入缺失/非法/重复/陈旧、预期设备缺失 | 具体整机、固定版本、周期、独立资产清单；不把当前值当预期 |
| P1：健康与错误 | E健康/故障码/ECC；D原始健康、驱动健康、事件 | 按健康/故障码分级与ECC新增复核，保留事件生命周期 | 故障字典、事件持久化/去重、恢复政策；驱动健康等价项仍需核对 |
| P1：温度与链路 | E芯片/HBM温度、预期Link/CRC；D降频原因 | 温限检测、预期链路异常、CRC增长，降频原因用于解释 | 官方机型限值、端口清单、计数重置、采集周期 |
| P2：容量与性能 | E容量/计算/带宽；D LLC | 容量预警与性能视图；不据高低利用率判硬件故障 | 单位、分母、采样口径、现场基线；无业务输入不推断作业失败 |
| P2：深度诊断 | D ECC地址、HCCS信用、SerDes、条件PCIe/PFC | 按需诊断和专项检测 | 机型支持、字段有效性、限值及成本；未证明Exporter缺失的先核实再开发 |

所有类别当前均未实机采集验收、未生成全表可执行规则、未部署。旧[candidates.yaml](../candidates.yaml)仅12项设计子集，不能据本表新增行推断已有对应规则实现。

## 11. 来源与证据登记

E-*为官方Exporter源码/指标文档，D-*为A3 HDK26.1 DCMI接口，FAULTS为官方故障查询。源码master会变化；此版未固定不可变快照，不用链接存在代替发行包核验。2026-11-17整理，部分资料核读于2026-11-16。

| 来源ID | 官方入口 | 用途与限制 |
|---|---|---|
| <a id="source-e-npu"></a>E-NPU | [E-NPU](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_npu.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-hbm"></a>E-HBM | [E-HBM](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_hbm.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-hccs"></a>E-HCCS | [E-HCCS](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_hccs.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-util"></a>E-UTIL | [E-UTIL](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_utilization.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-pcie"></a>E-PCIE | [E-PCIE](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_pcie.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-node"></a>E-NODE | [E-NODE](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_node_base.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-version"></a>E-VERSION | [E-VERSION](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_version.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-common"></a>E-COMMON | [E-COMMON](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/common_utils.go) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-metrics"></a>E-METRICS | [E-METRICS](https://github.com/Ascend/mind-cluster/blob/master/docs/zh/scheduling/06_api/00_npu_exporter/01_prometheus_metrics_api.md) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-e-config"></a>E-CONFIG | [E-CONFIG](https://github.com/Ascend/mind-cluster/blob/master/docs/zh/scheduling/05_developer_guide/00_installation_deployment/00_manual_installation/03_npu_exporter.md) | Exporter源码/文档；逐字段仍需固定发行版与现场核验 |
| <a id="source-faults"></a>FAULTS | [FAULTS](https://info.support.huawei.com/computing/tools/om-info-query) | 按型号、HDK版本查询故障意义及处置 |
| <a id="source-d-health"></a>D-HEALTH | [D-HEALTH](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_027.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-driver"></a>D-DRIVER | [D-DRIVER](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_028.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-ecc"></a>D-ECC | [D-ECC](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_047.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-sensor"></a>D-SENSOR | [D-SENSOR](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_058.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-llc"></a>D-LLC | [D-LLC](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_067.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-lp"></a>D-LP | [D-LP](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_078.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-pcie"></a>D-PCIE | [D-PCIE](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_084.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-event"></a>D-EVENT | [D-EVENT](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_125.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-ecc-record"></a>D-ECC-RECORD | [D-ECC-RECORD](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_129.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-topo"></a>D-TOPO | [D-TOPO](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_131.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-affinity"></a>D-AFFINITY | [D-AFFINITY](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_132.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-pfc"></a>D-PFC | [D-PFC](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_142.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-credit"></a>D-CREDIT | [D-CREDIT](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_158.html) | A3接口定义；须阅读该页产品/权限支持表 |
| <a id="source-d-serdes"></a>D-SERDES | [D-SERDES](https://www.hiascend.com/doc_center/source/zh/HDK/2610/A3/A3DCMI/dcmia3_136.html) | A3接口定义；须阅读该页产品/权限支持表 |

## 12. 初版待验证清单与检查

1. 固定A3整机/板卡/芯片/端口拓扑、OS/架构、驱动26.1.x精确补丁及配套固件，核对CANN 9.2.0完整组合。
2. 固定Exporter26.2.0镜像digest和发行源码；逐行对照实际HELP/TYPE、字段名称、单位、特殊值、支持矩阵及采集开关。
3. 补全HCCS完整原名、RoCE/光模块组内字段；检查所有D项是否已由其他collector/插件提供等价输出，已等价则转为E复用。
4. 验证物理身份稳定性、枚举数量、计数重启/复位行为；原始事件与快照不能互相替代。
5. 采样覆盖各组刷新周期，不能用几轮15秒抓取否定600秒组；每接口最后成功时间与样本时间分别验证。
6. 在语义与适用性明确后再生成规则和模拟输入，验证正常/触发/保持/恢复，以及缺数、非法、陈旧、冲突、重置、订阅断档和维护边界。

本版结构检查只验证分类、路径、六列、稳定ID、来源引用与派生索引一致性，不验证PromQL求值或硬件支持：

```bash
python modules/devices/huawei-npu/scripts/sync_monitoring_index.py --check
python modules/devices/huawei-npu/scripts/check_catalog.py
python scripts/check_module_layout.py
```

变更记录：0.1（2026-11-16）建立26项指标与12项规则候选；0.2（2026-11-17）按GPU文档组织分类主表，分开Exporter已有、DCMI补采/待核对和外部/派生输入，新增规则意义、恢复、适用性及官方证据。
