# H100 第一版规则提案台账

日期：2026-11-09；共33项提案，包括告警、准入检查、看板、可选策略及外部范围说明。不是33条可执行告警。

提案台账全部disabled、expression为空；部分已关联独立的draft规则卡，验证状态按对应范围保留，不升级为已发布。ECC/XID 诊断查询见[统计域和逐码分级](ecc-xid-review.md)。台账使用h100.*提案ID，正式草案保持nvidia.* ID，formal_rule_id/formal_rule_ids显式关联，不重命名。

每项metric_ids是候选输入池，必须/可选/替代关系待正式建卡时核定；例如旧ns时长与新s时长择一映射，不能同时统计。所有阈值、窗口、for和严重度尚未最终审定，不用统一85°C、TDP或低利用率阈值替代依据。

完整结构化定义见[rule-inventory.yaml](catalog/rule-inventory.yaml)，每项有来源、目标、输入、判据提案、结束语义和阻塞项。

## h100.admission：型号与采集基线核验

- 分类/优先级：必须核验/P0；目标：H100-C01, H100-C02
- 候选输入：`nvidia.gpu_name`, `nvidia.gpu_uuid`, `nvidia.driver_version`, `inventory.hardware_stack`
- 适用条件：全部H100训练部署
- 判据提案：验证H100形态、R595参考/实际差异、DCGM兼容、标签与字段类型；不通过则显示未准入
- 结束语义：核验完成不等于GPU健康
- 当前缺口：现场样本、型号准入、字段映射未实现
- 来源：`project.scope`, `nvidia.driver.r595.notes`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.scrape_failed：采集目标不可用

- 分类/优先级：必须覆盖的告警目标/P0；目标：H100-C03
- 候选输入：`prometheus.target_up`, `inventory.expected_devices`
- 适用条件：已知且非维护中的采集目标
- 判据提案：up失败持续条件需匹配采样周期；目标被删除的无序列情况另检查
- 结束语义：采集恢复，不代表硬件恢复
- 当前缺口：生产target及维护契约缺失
- 来源：`prometheus.up`
- 卡片/验证：draft_card；表达式 passed_for_batch1_synthetic_binding_only；新提案夜莺和真实H100均not_run

## h100.device_missing：物理卡或整组卡指标消失

- 分类/优先级：必须覆盖的告警目标/P0；目标：H100-C04
- 候选输入：`inventory.expected_devices`, `nvidia.gpu_uuid`, `prometheus.target_up`
- 适用条件：已有预期设备清单或有限发现历史
- 判据提案：按cluster+UUID比对预期与当前，区分单卡、全卡及整源故障
- 结束语义：重新上报仅表示可见性恢复
- 当前缺口：目前只有温度序列实验，未知从未上报设备数
- 来源：`project.scope`
- 卡片/验证：draft_card；表达式 passed_for_batch1_synthetic_binding_only；新提案夜莺和真实H100均not_run

## h100.field_missing_stale：必需指标缺失或陈旧

- 分类/优先级：必须覆盖的告警目标/P0；目标：H100-C05
- 候选输入：`prometheus.field_quality`, `prometheus.target_up`
- 适用条件：经审定的逐设备必需字段
- 判据提案：按字段依赖和采样周期检查缺失、年龄、重复序列；不使用全查询空替代单卡检查
- 结束语义：数据质量恢复，不代表硬件恢复
- 当前缺口：必需字段清单及准确查询待实现
- 来源：`prometheus.functions`, `project.scope`
- 卡片/验证：draft_card；表达式 passed_for_batch1_synthetic_binding_only；新提案夜莺和真实H100均not_run

## h100.invalid_values：无效值或不可判断输入

- 分类/优先级：必须覆盖的告警目标/P0；目标：H100-C06
- 候选输入：`prometheus.field_quality`
- 适用条件：逐字段定义有效域及不支持映射
- 判据提案：检测NaN/Inf/sentinel/权限或不支持，不以统一零值处理
- 结束语义：有效输入恢复，不代表故障排除
- 当前缺口：Exporter实际特殊值映射未知
- 来源：`nvidia.dcgm.blank`, `project.scope`
- 卡片/验证：draft_card；表达式 passed_for_batch1_synthetic_binding_only；新提案夜莺和真实H100均not_run

## h100.evaluation_failed：数据源查询/评估失败

- 分类/优先级：必须覆盖的告警目标/P0；目标：H100-C07
- 候选输入：`platform.evaluation_status`
- 适用条件：平台可获取查询/评估状态
- 判据提案：检测持续失败、超时和评估延迟；预算/阈值待平台指标核实
- 结束语义：执行能力恢复
- 当前缺口：平台状态字段未映射
- 来源：`project.scope`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.notification_failed：通知失败与积压

- 分类/优先级：必须覆盖的告警目标/P0；目标：H100-C07
- 候选输入：`platform.notification_status`
- 适用条件：平台具备发送/重试状态
- 判据提案：区分发送失败、重试和积压；不能仅依赖业务接收器存活
- 结束语义：通知链路恢复
- 当前缺口：故障与积压测试未覆盖
- 来源：`project.scope`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.ecc_new_errors：不可纠正ECC近期新增

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C08
- 候选输入：`nvidia.ecc_dbe_volatile_total`, `nvidia.dram_dbe_volatile`, `nvidia.sram_dbe_volatile`, `nvidia.ecc_mode`, `nvidia.ecc_pending`
- 适用条件：H100字段支持/统计域已核实，物理卡身份有效
- 判据提案：分别核对汇总与细分；避免重复计数，使用counter重置语义
- 结束语义：窗口内无新增，不是硬件修复
- 当前缺口：总量已有告警草案，设备内存和 SRAM 已补诊断查询。现场主告警源择一和夜莺验证仍待完成。
- 来源：`nvidia.dcgm.fixed_fields`
- 卡片/验证：draft_card；表达式 passed_for_existing_draft_only；新提案夜莺和真实H100均not_run

## h100.ecc_history：首次发现既往不可纠正记录

- 分类/优先级：看板/上下文/P1；目标：H100-C08
- 候选输入：`nvidia.ecc_dbe_aggregate`, `nvidia.dram_dbe_aggregate`, `nvidia.sram_dbe_aggregate`
- 适用条件：持久字段可用
- 判据提案：非零历史标注/人工复核，不伪装本轮新增，不重复呼叫
- 结束语义：不通过观察窗口自行清除历史
- 当前缺口：现场持久字段及基线核实。当前查询展示历史非零，首次发现的事件记录仍待实现。
- 来源：`nvidia.dcgm.fixed_fields`
- 卡片/验证：review_query_written；表达式 passed_synthetic_review；新提案夜莺和真实H100均not_run

## h100.correctable_trend：纠正ECC活动趋势

- 分类/优先级：看板/上下文/P2；目标：H100-C09
- 候选输入：`nvidia.ecc_sbe_volatile`, `nvidia.ecc_sbe_aggregate`, `nvidia.dram_sbe_volatile`, `nvidia.sram_sbe_volatile`, `nvidia.dram_sbe_aggregate`, `nvidia.sram_sbe_aggregate`
- 适用条件：H100对应统计域有效
- 判据提案：先展示趋势及驱动事件上下文，没有H100依据不设置统一SBE故障阈值
- 结束语义：趋势回落不等于根因消失
- 当前缺口：现场统计域、持久趋势和驱动 CE 风暴判据待核实。
- 来源：`nvidia.dcgm.fixed_fields`
- 卡片/验证：review_query_written；表达式 passed_synthetic_review；新提案夜莺和真实H100均not_run

## h100.sram_threshold：SRAM超阈值状态

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C10
- 候选输入：`nvidia.sram_exceeded`
- 适用条件：H100字段支持且bool语义已验证
- 判据提案：依据官方阈值标志判断，不用DBE总数重建bank级RMA算法
- 结束语义：标志消失的原因需核实，不能自动宣布维修完成
- 当前缺口：字段采集、保持和清除行为未知
- 来源：`nvidia.dcgm.fixed_fields`
- 卡片/验证：draft_card；表达式 passed_for_batch1_synthetic_binding_only；新提案夜莺和真实H100均not_run

## h100.row_remap_failed：行重映射失败

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C11
- 候选输入：`nvidia.remap_failed`
- 适用条件：字段可用且无特殊值
- 判据提案：依据失败状态，不以累计重映射非零代替失败
- 结束语义：状态解除需核实维护原因
- 当前缺口：真实H100字段映射与清除语义未知
- 来源：`nvidia.memory.statistics`, `nvidia.dcgm.fixed_fields`
- 卡片/验证：draft_card；表达式 passed_for_batch1_synthetic_binding_only；新提案夜莺和真实H100均not_run

## h100.row_remap_pending：行重映射待生效

- 分类/优先级：条件适用告警/P1；目标：H100-C12
- 候选输入：`nvidia.remap_pending`
- 适用条件：字段有效并有维护流程
- 判据提案：待生效状态转维护提示；持续/分级不能推断立即停机
- 结束语义：pending清除需与生效/维护上下文关联
- 当前缺口：待生效标志复核查询已测试。维护窗口、持续时间与解除语义待现场审定。
- 来源：`nvidia.memory.statistics`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.row_remap_resource：重映射资源退化

- 分类/优先级：条件适用告警/P1；目标：H100-C13
- 候选输入：`nvidia.remap_bank_max`, `nvidia.remap_bank_high`, `nvidia.remap_bank_partial`, `nvidia.remap_bank_low`, `nvidia.remap_bank_none`
- 适用条件：H100资源桶可用且官方处置映射审定
- 判据提案：资源分桶用于退化判断；无依据不设low/none银行数量统一阈值
- 结束语义：资源状态变化不等于维修完成
- 当前缺口：尚无逐形态资源判据与字段证据
- 来源：`nvidia.memory.statistics`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.row_remap_history：重映射记录趋势

- 分类/优先级：看板/上下文/P2；目标：H100-C13
- 候选输入：`nvidia.remapped_uncorrectable`, `nvidia.remapped_correctable`
- 适用条件：统计域与采集映射明确
- 判据提案：记录InfoROM活动，不等同当前硬件已完成重映射
- 结束语义：累计历史不按窗口恢复
- 当前缺口：字段新旧别名待部署版本核对
- 来源：`nvidia.memory.statistics`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.xid_classified：H100适用XID分类与处置

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C14
- 候选输入：`nvidia.xid_last`, `nvidia.recovery_action`
- 适用条件：逐码审定适用性和处置，实际输入路径可用
- 判据提案：78项先分类；信息/IGNORE不呼叫，需告警项按影响分级；最近码不做increase
- 结束语义：码值改变不等于旧故障恢复
- 当前缺口：78 码已完成处置草案。节点事件和 GPU 重置复核有查询，通知与有序事件关联待实现。
- 来源：`nvidia.xid.catalog`
- 卡片/验证：review_query_written；表达式 passed_synthetic_review；新提案夜莺和真实H100均not_run

## h100.xid_event_context：有序XID与恢复动作关联

- 分类/优先级：条件适用告警/P1；目标：H100-C14
- 候选输入：`nvidia.xid_last`, `nvidia.recovery_action`, `diagnostics.results`
- 适用条件：现有输入包含足够有序事件及动作信息
- 判据提案：关联contained/uncontained与恢复动作；缺事件流时只声明状态观测
- 结束语义：根据事件/动作语义，不用最近值清零代替修复
- 当前缺口：仅轮询码值无法保证事件完整性
- 来源：`nvidia.xid.catalog`, `nvidia.memory.recovery`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.inforom_driver：InfoROM与驱动管理状态

- 分类/优先级：条件适用告警/P1；目标：H100-C15
- 候选输入：`nvidia.inforom_valid`, `nvidia.driver_version`, `inventory.hardware_stack`
- 适用条件：有效状态可读，已核实支持/不支持字典
- 判据提案：分别检测有效性/初始化问题和版本不匹配，状态不可读单列
- 结束语义：管理状态恢复不代表所有硬件正常
- 当前缺口：驱动状态/初始化输入不一定在已有Prometheus
- 来源：`nvidia.dcgm.fixed_fields`, `nvidia.driver.r595.notes`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.gpu_thermal_margin：GPU热余量不足

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C16
- 候选输入：`nvidia.gpu_temp`, `nvidia.gpu_max_temp`, `nvidia.gpu_temp_margin`, `nvidia.slowdown_temp`, `nvidia.shutdown_temp`
- 适用条件：有效温度及设备门槛/余量可读
- 判据提案：以设备门槛审定预警余量和持续时间，无门槛则显示缺口，不回退85度
- 结束语义：温度余量恢复，根因需排查
- 当前缺口：设备运行门槛差值查询已测试。现场温度门槛采集和预警余量待审定。
- 来源：`nvidia.smi`, `nvidia.dcgm.fixed_fields`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.memory_thermal_margin：显存热余量不足

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C16
- 候选输入：`nvidia.memory_temp`, `nvidia.memory_max_temp`
- 适用条件：H100显存温度和对应门槛可读
- 判据提案：单独核对HBM热风险，不用GPU温度替代显存温度
- 结束语义：热条件退出，不等于负载或散热根因消失
- 当前缺口：独立显存运行门槛差值查询已测试。现场 HBM 门槛字段仍待核验。
- 来源：`nvidia.smi`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.thermal_throttle：持续热降频

- 分类/优先级：必须覆盖的告警目标/P1；目标：H100-C17
- 候选输入：`nvidia.clock_reasons`, `nvidia.thermal_violation_ns`, `nvidia.thermal_throttle_seconds`, `nvidia.gpu_temp`, `nvidia.memory_temp`
- 适用条件：状态位或累计时长可读且单位映射完成
- 判据提案：按热限制原因/时长判断；ns和s字段择一，不重复汇总
- 结束语义：热限制解除
- 当前缺口：已测试 SW/HW 热降频位和 ns 累计时长换算。持续性及分级仍待审定。
- 来源：`nvidia.smi`, `nvidia.dcgm.fixed_fields`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.power_limited：训练功率限制状态

- 分类/优先级：条件适用告警/P1；目标：H100-C18
- 候选输入：`nvidia.board_power`, `nvidia.board_power_raw`, `nvidia.requested_power_limit`, `nvidia.enforced_power_limit`, `nvidia.clock_reasons`, `nvidia.power_violation_ns`, `nvidia.power_throttle_seconds`
- 适用条件：具备预期功率配置/负载上下文
- 判据提案：正常功率管理仅展示；异常配置或有影响的持续限制才告警
- 结束语义：限制解除或配置确认，不是硬件维修
- 当前缺口：SW 功率限制位视图已测试。功率预算、配置一致性及训练影响仍待核实。
- 来源：`nvidia.smi`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.external_power_brake：外部供电限制或不可读

- 分类/优先级：条件适用告警/P1；目标：H100-C19
- 候选输入：`nvidia.clock_reasons`, `nvidia.board_power`, `host.power_context`
- 适用条件：限制原因明确，根因需要主机输入
- 判据提案：区分power-brake信号与PSU根因；读失败报数据质量，不臆断PSU损坏
- 结束语义：信号解除，根因需确认
- 当前缺口：外部 power-brake 与通用 HW slowdown 分列观察。BMC/PSU 根因输入仍待接入。
- 来源：`nvidia.smi`, `project.scope`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.pcie_errors：PCIe replay异常新增

- 分类/优先级：条件适用告警/P1；目标：H100-C20
- 候选输入：`nvidia.pcie_replay`, `inventory.hardware_stack`
- 适用条件：硬件/驱动计数口径、基线和阈值审定
- 判据提案：记录新增趋势并核实告警判据；不套主动诊断插件阈值
- 结束语义：近期错误条件退出，不表示物理修复
- 当前缺口：五分钟 replay 新增查询已测试。持续监测阈值与现场驱动口径待核验。
- 来源：`nvidia.dcgm.fixed_fields`, `nvidia.diag.pcie`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.pcie_degraded：负载下PCIe链路退化

- 分类/优先级：条件适用告警/P1；目标：H100-C20
- 候选输入：`nvidia.pcie_max_gen`, `nvidia.pcie_max_width`, `nvidia.pcie_gen`, `nvidia.pcie_width`, `inventory.expected_links`, `training.job_context`
- 适用条件：预期配置与工作负载可知
- 判据提案：按预期链路与负载判断代际/宽度退化；空闲降速不直接故障
- 结束语义：链路配置恢复
- 当前缺口：预期链路及训练上下文缺失
- 来源：`nvidia.topology`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.nvlink_errors：Hopper NVLink错误活动

- 分类/优先级：条件适用告警/P1；目标：H100-C21
- 候选输入：`nvidia.nvlink_crc`, `nvidia.nvlink_recovery`, `nvidia.nvlink_replay`
- 适用条件：实际存在NVLink且Hopper字段可读
- 判据提案：分别核实CRC/replay/recovery新增和严重度，不搬用其他代际字段
- 结束语义：近期错误条件退出
- 当前缺口：Hopper CRC/recovery/replay 分列查询已测试。现场拓扑、标签与持续参数待核验。
- 来源：`nvidia.exporter.counters`, `nvidia.topology`
- 卡片/验证：review_query_written；表达式 passed_offline_and_streaming_review；新提案夜莺和真实H100均not_run

## h100.nvlink_link_down：预期NVLink端口掉链

- 分类/优先级：条件适用告警/P1；目标：H100-C21
- 候选输入：`nvidia.nvlink_link_state`, `inventory.expected_links`
- 适用条件：预期启用链路/对端清单完整
- 判据提案：只检查预期启用端口；disabled/unsupported分开解释
- 结束语义：预期链路恢复
- 当前缺口：link实体是否导出与预期拓扑未知
- 来源：`nvidia.topology`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.fabric_unhealthy：Fabric Manager/fabric异常

- 分类/优先级：条件适用告警/P1；目标：H100-C22
- 候选输入：`nvidia.fm_status`, `nvidia.fm_error`, `nvidia.fabric_health_mask`, `nvidia.fabric_health_summary`, `inventory.expected_links`
- 适用条件：实际需要FM/fabric管理且状态输入存在
- 判据提案：按状态字典区分未就绪、异常和不支持，关联预期拓扑
- 结束语义：fabric状态恢复
- 当前缺口：不是所有H100形态都有FM/NVSwitch输入
- 来源：`nvidia.nvswitch`, `nvidia.driver.r595.notes`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.switch_sxid：交换机SXid异常

- 分类/优先级：条件适用告警/P1；目标：H100-C22
- 候选输入：`nvidia.sxid_fatal`, `nvidia.sxid_nonfatal`
- 适用条件：系统确有NVSwitch，实体身份及码值语义已核实
- 判据提案：按SXid码分类，不把856/857当counter
- 结束语义：码值变化不等于修复
- 当前缺口：交换机实体和SXid处置表未完成
- 来源：`nvidia.nvswitch`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.switch_links：NVSwitch端口与错误

- 分类/优先级：条件适用告警/P1；目标：H100-C22
- 候选输入：`nvidia.switch_link_state`, `nvidia.switch_link_fatal`, `nvidia.switch_link_nonfatal`, `nvidia.switch_link_replay`, `nvidia.switch_link_recovery`, `inventory.expected_links`
- 适用条件：实际NVSwitch和预期端口存在
- 判据提案：核实端口状态、错误值类型和对端，不对未使用端口告警
- 结束语义：预期端口恢复
- 当前缺口：782/783类型仍未核实，采集实体未知
- 来源：`nvidia.nvswitch`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.switch_thermal：NVSwitch温度异常

- 分类/优先级：条件适用告警/P1；目标：H100-C22
- 候选输入：`nvidia.switch_temp`, `nvidia.switch_slowdown_temp`
- 适用条件：实际NVSwitch且温度/门槛可读
- 判据提案：使用交换机自身门槛，不套GPU阈值
- 结束语义：热条件退出
- 当前缺口：门槛与交换机实体采集未知
- 来源：`nvidia.nvswitch`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.training_efficiency：训练容量与效率策略

- 分类/优先级：可选训练策略/P2；目标：H100-C23
- 候选输入：`nvidia.gpu_util`, `nvidia.mem_copy_util`, `nvidia.fb_free`, `nvidia.fb_used`, `nvidia.gr_engine_ratio`, `nvidia.sm_active_ratio`, `nvidia.sm_occupancy_ratio`, `nvidia.tensor_active_ratio`, `nvidia.dram_active_ratio`, `nvidia.pcie_tx_rate`, `nvidia.pcie_rx_rate`, `nvidia.sm_clock`, `nvidia.mem_clock`, `nvidia.pstate`, `training.job_context`
- 适用条件：有训练任务分配/阶段、profiling支持和权限
- 判据提案：看板优先；空闲、偏斜和压力策略按作业审定，不给统一高利用率故障阈值
- 结束语义：策略条件退出，不等于硬件恢复
- 当前缺口：现有GPU指标没有完整作业上下文
- 来源：`nvidia.profiling`, `project.scope`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run

## h100.diagnostics_boundary：主动诊断/RMA及整机根因

- 分类/优先级：范围外/外部诊断/P2；目标：H100-C24
- 候选输入：`diagnostics.results`, `host.power_context`
- 适用条件：明确仅被动指标范围
- 判据提案：保留外部诊断入口；不自动施加负载、重置设备或模拟RMA结论
- 结束语义：由授权诊断流程判定
- 当前缺口：需日志、主动诊断或BMC等外部证据
- 来源：`nvidia.triage`
- 卡片/验证：not_written；表达式 not_run；新提案夜莺和真实H100均not_run
