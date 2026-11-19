# GPU指标动态基线适用性与准入清单

更新：2026-11-17。状态：需求选型与实现待办，不代表新增字段已接入或模型已通过效果验收。

语义权威为[GPU监控指标主清单](../../rules/docs/14-GPU监控指标与告警规则说明表.md)修订1.2。本文仅选择ML用途，不修改原始指标定义、规则或派生契约。附录逐项覆盖其A/B共103项；分类是本项目模型选型决策，不是NVIDIA官方算法推荐。后续主清单变化须复核本表，不能按旧数量静默通过。

## 1. 判断原则

动态基线适用于具有数量距离意义、随运行连续变化、可从历史学习正常行为的测量值。值必须有效、同实体、单位一致、采样可用，且历史对未来具有一定参考性。能画曲线不代表适合建模，Prometheus的gauge/counter标签也不足以决定用途。

- 温度、实际功率、活动率、真实吞吐速率可成为候选，但工作负载突变仍可能使自身历史不可比。
- MHz时钟、显存用量虽有数量意义，往往多档位/阶跃，须先证明历史可预测，不能因单位连续就默认适用。
- 功率上限、温度门槛、总容量等是配置/参考事实；变化优先作变更事件或模型分段依据。
- XID/SXID码、PState、链路状态、布尔标志和位图不具有通用数值距离含义，不送入当前连续量模型。二元占空比等衍生统计需新定义，不通过把状态直接平均来默认准入。
- 累计能耗/时长先转换；错误计数即使能算速率，也不自动适合动态基线。不能学习出“正常硬件错误额度”后抑制硬规则。

适用性、采集支持和效果准入分别记录。A/B仅为可评估候选；长期恒定、全零、离散档位过少或不可预测时，可保留原始曲线/规则，不强行生成动态参考。

## 2. 首期选择与扩展顺序

| 层级 | 指标 | 需求选择与输出解释 | 当前实现边界 |
|---|---|---|---|
| A 首批5项 | GPU温度、HBM温度、实际板卡功耗、GPU利用率、显存控制器活动率 | 优先验证单指标动态参考；高/低本身不代表坏卡，正常空闲/负载切换必须作为反例 | 已有gpu_temp、memory_temp、power、util、mem_util绑定与单指标配置基础；效果逐项验收 |
| B 当前3项 | SM时钟、显存时钟、已用显存 | 允许有条件评估，不默认全开；时钟优先条件关系/模式，显存只解释占用变化 | 已有sm_clock、mem_clock、fb_used绑定；需适用性门槛与UI分级 |
| B 扩展连续量 | SM/GR/Tensor/DRAM活动、PCIe/NVLink吞吐、热余量、显存空闲/占比、另一功率观测口径 | 核实采集/单位/模式后评估，避免同义或代数冗余 | 当前通用配置未接入这些扩展字段，不因公共规范存在而视为可选 |
| C 衍生量 | 累计能耗→窗口平均功率；累计限功率/热限制时长→窗口受限占比 | 需要独立衍生契约和效果评估；稀疏二元特征不适合时走统计/规则 | 当前通用单指标选择器不支持这些转换，不加入现有训练字段 |
| D/E/G 不作当前动态基线 | 错误、开关、枚举、位图、配置、静态元数据、未知语义 | 保留规则、事件、上下文和质量监测 | 不得为了“多指标”而把它们直接塞进PCA/森林 |
| F 后续实体扩展 | NVSwitch实际温度 | 物理量适合评估，但不是GPU UUID实体 | 需switch_id身份、查询、任务和模型契约另行实现 |

A是研发验证优先级，不是默认通知或对所有GPU自动开启。现有页面可选的8项仍保持原行为；按A/B分级、筛选和预检是待实现需求。本次仅更新文档。

## 3. C类转换要求

累计能耗按同实体相邻有效样本的能量增量除以真实时间间隔，mJ转J后得到W；这是窗口平均功率，不等同另一个功率字段的瞬时/平均采样口径，不重复作为独立证据。

累计限制时长按有效窗口计算Δ受限时长/Δ源时间，ns字段先转秒。须确认累计口径确实可解释为窗口占比，旧新同义字段二选一。超出物理范围应报语义/质量问题，不能裁剪为正常。受限已发生的硬规则保持独立，不用基线确认才报警。

重启/reset、长缺口、首点、重复/乱序和单位变化使窗口无效；不跨reset作差、不把缺口整段平均为有效样本、不用插值补窗口。衍生特征记录原metric_id、表达式、单位、窗口、采样、reset政策、时间对齐及契约版本。当前模型不支持这些转换时禁止提交对应训练。

## 4. 训练前适用性与页面需求

| 检查 | 需求行为 |
|---|---|
| 语义选择 | 动态基线选择器仅提供已实现的A/B字段；C待转换支持后提供衍生字段；D/E/F/G解释不可选原因 |
| 身份/单位/支持 | 逐设备核实真实字段、单位、重复与sentinel；正式身份job/instance/UUID与旧cluster/UUID迁移缺口继续登记 |
| 样本和模式 | 报告覆盖、有效连续窗口、有效取值/档位、零值占比及变化幅度；常量/多档位/长零给明确适用性提示，不把合法空闲零值当缺失 |
| 可预测性 | 时间顺序回放，与上一值/训练中位数等简单参考比较预测误差、正常标注告警和评分覆盖；复杂模型无增益时不声称动态基线有效 |
| 训练分布 | 核对负载切换、限功率和设备配置变更；不把正常配置切换默认认定故障，不自动用新异常重训成正常 |
| 告警与解释 | 允许仅看曲线或影子，先评估再人工发布；异常方向和预算按指标/工况约定，温度硬门槛独立 |

适用性检查的具体统计阈值需配置化并通过模拟/回放确定，本文件不编造统一GPU阈值；当前预检尚未完整实现以上项目。是否适用须有结论及理由，不能仅以“训练成功、240点足够”代替。

## 5. 验收与实施边界

新增验收：同为gauge的温度可选而XID/功率上限/链路宽度不可选；A/B逐项核对模型配置与解释；常量、合法空闲零、正常阶跃、长期漂移、采集缺口分开记录；单位/reset反例对C类转换有效性作独立验证。真实支持、数据质量、可预测性和告警收益分层报告，不凭一条平滑曲线判定准入。

多指标能力同样受语义门槛约束：A/B可作为连续目标/特征，E只能通过明确模板作为分段/可比性上下文；D/G不直接进入当前通用数值模型。错误事件可用于人工标注与解释，不能悄悄作为正常数值训练输入。

## 附录：正式主清单103项逐项去向

以下类型/单位按主清单记录；用途为ML需求判断。A首批候选、B条件候选、C转换后评估、D规则/事件统计、E配置/上下文、F当前实体范围外、G语义阻塞。所有非A/B项均不作为当前通用动态基线原值目标。

分类汇总：A 5项、B 17项、C 5项、D 54项、E 19项、F 1项、G 2项，合计103项。

| metric_id | 语义类型 / 单位 | ML去向 | 理由/前提 |
|---|---|---|---|
| `nvidia.driver_version` | label / version | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.gpu_name` | string / text | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.gpu_uuid` | string / text | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `inventory.expected_devices` | configuration / device_set | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `inventory.hardware_stack` | configuration / inventory | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.inforom_valid` | state / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.xid_last` | gauge / error_code | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.ecc_mode` | state / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.ecc_pending` | state / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.ecc_sbe_volatile` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.ecc_dbe_volatile_total` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.ecc_sbe_aggregate` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.ecc_dbe_aggregate` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.dram_sbe_volatile` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.dram_dbe_volatile` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.dram_sbe_aggregate` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.dram_dbe_aggregate` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.sram_sbe_volatile` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.sram_dbe_volatile` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.sram_sbe_aggregate` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.sram_dbe_aggregate` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.sram_exceeded` | state / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remap_bank_max` | gauge / banks | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remap_bank_high` | gauge / banks | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remap_bank_partial` | gauge / banks | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remap_bank_low` | gauge / banks | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remap_bank_none` | gauge / banks | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remapped_uncorrectable` | counter / rows | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.remapped_correctable` | counter / rows | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.remap_failed` | state / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.remap_pending` | state / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.recovery_action` | enum / enum | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.fb_free` | gauge / MiB | B 条件候选 | 与已用量强冗余；同口径通常二选一 |
| `nvidia.fb_used` | gauge / MiB | B 条件候选 | 容量占用呈分配/释放阶跃；只解释占用模式变化，不推断泄漏 |
| `nvidia.gpu_util` | gauge / percent | A 首批候选 | 首批候选；高低均可能正常，评估正常负载切换 |
| `nvidia.gr_engine_ratio` | gauge / ratio | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.sm_active_ratio` | gauge / ratio | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.sm_occupancy_ratio` | gauge / ratio | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.tensor_active_ratio` | gauge / ratio | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.mem_copy_util` | gauge / percent | A 首批候选 | 首批候选；显存控制器活动，不是容量或精确带宽 |
| `nvidia.dram_active_ratio` | gauge / ratio | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.sm_clock` | gauge / MHz | B 条件候选 | 离散调频/空闲切换影响大；模式可比后评估，优先条件关系 |
| `nvidia.mem_clock` | gauge / MHz | B 条件候选 | 常为少数档位；优先模式上下文，稳定可预测时才做基线 |
| `nvidia.clock_reasons` | bitmask / bitmask | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.memory_temp` | gauge / celsius | A 首批候选 | 首批候选；须真实支持HBM传感器，不借GPU温度替代 |
| `nvidia.gpu_temp` | gauge / celsius | A 首批候选 | 首批候选；受负载/环境影响，只解释自身温度变化 |
| `nvidia.memory_max_temp` | gauge / celsius | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.gpu_max_temp` | gauge / celsius | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.gpu_temp_margin` | gauge / celsius | B 条件候选 | 必须有有效对应运行温度门槛；不伪造分母/门槛 |
| `nvidia.board_power` | gauge / watts | A 首批候选 | 首批候选；负载和功率配置变动需区分 |
| `nvidia.board_power_raw` | gauge / watts | B 条件候选 | 需核实采样/平均口径；与board_power避免重复证据 |
| `nvidia.slowdown_temp` | gauge / celsius | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.shutdown_temp` | gauge / celsius | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.requested_power_limit` | gauge / watts | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.enforced_power_limit` | gauge / watts | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.pstate` | enum / enum | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.power_violation_ns` | counter / nanoseconds | C 转换后评估 | 有效窗口累计受限时长增量/窗口时长；ns显式换秒 |
| `nvidia.thermal_violation_ns` | counter / nanoseconds | C 转换后评估 | 累计时长先处理reset，再算窗口受限时间占比；旧新同义字段二选一 |
| `nvidia.power_throttle_seconds` | counter / seconds | C 转换后评估 | 累计时长先处理reset，再算窗口受限时间占比；旧新同义字段二选一 |
| `nvidia.thermal_throttle_seconds` | counter / seconds | C 转换后评估 | 累计时长先处理reset，再算窗口受限时间占比；旧新同义字段二选一 |
| `nvidia.fm_status` | enum / enum | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.fm_error` | enum / error_code | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.fabric_health_mask` | bitmask / bitmask | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.fabric_health_summary` | enum / enum | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.pcie_replay` | counter / events | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.pcie_max_gen` | gauge / generation | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.pcie_max_width` | gauge / lanes | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.pcie_gen` | gauge / generation | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.pcie_width` | gauge / lanes | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.nvlink_crc` | counter / errors | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.nvlink_recovery` | counter / events | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.nvlink_replay` | counter / events | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.switch_link_fatal` | unknown / unknown | G 语义阻塞 | 类型/单位未闭合，不训练，不推断健康 |
| `nvidia.switch_link_nonfatal` | unknown / unknown | G 语义阻塞 | 类型/单位未闭合，不训练，不推断健康 |
| `nvidia.switch_link_replay` | counter / events | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.switch_link_recovery` | counter / events | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.sxid_fatal` | gauge / error_code | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.sxid_nonfatal` | gauge / error_code | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.switch_temp` | gauge / celsius | F 当前实体范围外 | 连续温度可作为后续候选，但NVSwitch身份/任务/模型契约尚未纳入单GPU能力 |
| `nvidia.switch_slowdown_temp` | gauge / celsius | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.switch_link_state` | enum / enum | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.pcie_tx_rate` | gauge / bytes_per_second | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.pcie_rx_rate` | gauge / bytes_per_second | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.nvlink_link_state` | enum / enum | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `inventory.expected_links` | configuration / link_set | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `prometheus.target_up` | scrape_status / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `prometheus.field_quality` | derived_query / quality_state | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `platform.evaluation_status` | platform_api_or_metrics / status | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `platform.notification_status` | platform_api_or_metrics / status | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `training.job_context` | external_context / job_state | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `host.power_context` | external_context / status | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `diagnostics.results` | external_diagnostic / diagnostic_result | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.memory_unrepairable` | boolean / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.retired_sbe` | counter / pages | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.retired_dbe` | counter / pages | D 规则/事件统计 | 错误/维护计数优先增量规则；稀疏长零序列不套通用动态基线 |
| `nvidia.retired_pending` | boolean / boolean | D 规则/事件统计 | 状态、码值、位图或离散健康/链路观测，按语义规则解释 |
| `nvidia.fb_used_ratio` | ratio / 0–1 | B 条件候选 | 固定口径Used/(Total−Reserved)，需核实分母；不混USED/TOTAL |
| `nvidia.fb_total` | gauge / MiB | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.fb_reserved` | gauge / MiB | E 配置/上下文 | 用于身份、分段、可比性或规则门槛，不学习原值正常波动 |
| `nvidia.energy` | counter / mJ | C 转换后评估 | 先按实体处理reset，ΔmJ/(1000×Δ秒)得到窗口平均W；不直接拟合累计值 |
| `nvidia.nvlink_tx_rate` | gauge / bytes/s | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.nvlink_rx_rate` | gauge / bytes/s | B 条件候选 | 需Profiling/拓扑/单位和足够有效历史；正常负载变化不等于故障 |
| `nvidia.nvlink_aggregate_rate` | gauge / MB/s | B 条件候选 | 固定版本MB/s速率口径；与方向吞吐不重复相加 |

## 后续实现状态更新（0.6.0）

本轮已增加首批5项专用Web入口、合法零/常量与连续采样初步预检、预测误差与简单参考比较及运行参数展示。完整A/B分级选择、扩展字段、C类转换与真实效果仍待完成；上文“本次仅文档”的描述指本清单制定时，当前增量以[演示记录](16-单指标动态基线演示与验收.md)为准。
