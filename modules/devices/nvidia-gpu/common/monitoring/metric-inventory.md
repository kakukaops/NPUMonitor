# H100 第一版指标与输入台账

日期：2026-11-09；状态：候选输入清单，不是已支持H100的白名单。

共92项：82个唯一DCGM字段ID，另有10项采集状态/配置/平台或外部上下文。后者不冒充已有GPU指标。6项已有draft指标/输入卡，其余尚未建卡。

来源为固定DCGM header和固定Exporter配置；别名按字段ID合并。新版字段存在不证明所选DCGM 4.3.x及以上任一版本都支持，reference CSV存在/启用也不证明现场已发出。具体提交与哈希见[构建证据](catalog/inventory-evidence.yaml)。

“类型/单位”是源码或配置驱动的候选语义，目标栈仍需核对；没有CSV条目的字段不猜测实际Prometheus名称。label/string字段可能是标签或元信息，不保证有独立数值时序。

所有项的真实采集状态均unknown，逐H100形态字段支持未验证。规则引用表示候选输入池，不代表所有字段必须同时采集。新旧时长字段、总计数和位置明细不重复相加。

| 指标ID | 名称 / 字段ID | 固定header名称 | 参考CSV映射 / 类型 / 状态 | 语义类型 / 单位 | 用途与边界 | 对应目标 |
| --- | --- | --- | --- | --- | --- | --- |
| nvidia.driver_version | 驱动版本 / 1 | DCGM_FI_SYSTEM_DRIVER_VERSION | DCGM_FI_DRIVER_VERSION / label / 启用 | label / version | 用于匹配固定驱动基线，不作为独立数值告警 | H100-C01, H100-C02, H100-C15 |
| nvidia.gpu_name | GPU产品名称 / 50 | DCGM_FI_DEV_GPU_NAME | 未在参考CSV列出/实际映射待核实 | string / text | 用于核实H100形态，名称字符串不能单独完成准入 | H100-C01, H100-C02 |
| nvidia.gpu_uuid | GPU UUID / 54 | DCGM_FI_DEV_GPU_UUID | 未在参考CSV列出/实际映射待核实 | string / text | 设备稳定身份；不能用GPU序号替代 | H100-C01, H100-C02, H100-C04 |
| nvidia.inforom_valid | InfoROM有效性 / 84 | DCGM_FI_DEV_INFOROM_VALID | 未在参考CSV列出/实际映射待核实 | state / boolean | 需核实值域、读失败及不支持的表示 | H100-C15 |
| nvidia.sm_clock | SM时钟 / 100 | DCGM_FI_DEV_SM_CLOCK | DCGM_FI_DEV_SM_CLOCK / gauge / 启用 | gauge / MHz | 低频需负载和限制原因上下文 | H100-C23 |
| nvidia.mem_clock | 显存时钟 / 101 | DCGM_FI_DEV_MEM_CLOCK | DCGM_FI_DEV_MEM_CLOCK / gauge / 启用 | gauge / MHz | 配置/负载相关，不能直接设统一低频故障阈值 | H100-C23 |
| nvidia.clock_reasons | 时钟限制原因 / 112 | DCGM_FI_DEV_CLOCKS_EVENT_REASONS | 未在参考CSV列出/实际映射待核实 | bitmask / bitmask | 按位解释，不能对位掩码使用increase | H100-C17, H100-C18, H100-C19 |
| nvidia.memory_temp | HBM/显存温度 / 140 | DCGM_FI_DEV_MEMORY_TEMP_CELSIUS | DCGM_FI_DEV_MEMORY_TEMP / gauge / 启用 | gauge / celsius | 存储域与H100可用性待核实 | H100-C16, H100-C17 |
| nvidia.gpu_temp | GPU温度 / 150 | DCGM_FI_DEV_GPU_TEMP_CELSIUS | DCGM_FI_DEV_GPU_TEMP / gauge / 启用 | gauge / celsius | 与设备门槛/余量配合，不使用实验85度 | H100-C16, H100-C17 |
| nvidia.memory_max_temp | 显存最大运行温度门槛 / 151 | DCGM_FI_DEV_MEMORY_MAX_OP_TEMP_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 设备提供的门槛是否可见待核实 | H100-C16 |
| nvidia.gpu_max_temp | GPU最大运行温度门槛 / 152 | DCGM_FI_DEV_GPU_MAX_OP_TEMP_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 运行门槛与shutdown门槛不可互换 | H100-C16 |
| nvidia.gpu_temp_margin | GPU热余量 / 153 | DCGM_FI_DEV_GPU_TEMP_MARGIN_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 方向/有效范围需按目标版本核实 | H100-C16 |
| nvidia.board_power | 板卡功耗 / 155 | DCGM_FI_DEV_BOARD_POWER_WATTS | DCGM_FI_DEV_POWER_USAGE / gauge / 启用 | gauge / watts | 高功耗可能为正常训练负载 | H100-C18, H100-C19 |
| nvidia.board_power_raw | 板卡瞬时功耗 / 157 | DCGM_FI_DEV_BOARD_POWER_RAW_WATTS | 未在参考CSV列出/实际映射待核实 | gauge / watts | 与平均功耗口径不同，不重复解释 | H100-C18 |
| nvidia.slowdown_temp | GPU降频温度门槛 / 158 | DCGM_FI_DEV_GPU_TEMP_SLOWDOWN_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 门槛本身不是当前降频状态 | H100-C16 |
| nvidia.shutdown_temp | GPU关断温度门槛 / 159 | DCGM_FI_DEV_GPU_TEMP_SHUTDOWN_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 不把关断门槛用作早期预警阈值 | H100-C16 |
| nvidia.requested_power_limit | 请求的功率限制 / 160 | DCGM_FI_DEV_BOARD_POWER_LIMIT_REQUESTED_WATTS | DCGM_FI_DEV_POWER_MGMT_LIMIT / gauge / 注释 | gauge / watts | 需比对配置基线；TDP不能代替 | H100-C18 |
| nvidia.enforced_power_limit | 实际执行的功率限制 / 164 | DCGM_FI_DEV_BOARD_POWER_LIMIT_ENFORCED_WATTS | DCGM_FI_DEV_ENFORCED_POWER_LIMIT / gauge / 注释 | gauge / watts | 按当前平台限制条件解释 | H100-C18 |
| nvidia.fm_status | Fabric Manager状态 / 170 | DCGM_FI_DEV_FABRIC_MANAGER_STATUS | 未在参考CSV列出/实际映射待核实 | enum / enum | 仅适用于需要FM的系统，值域字典待核实 | H100-C22 |
| nvidia.fm_error | Fabric Manager错误 / 171 | DCGM_FI_DEV_FABRIC_MANAGER_ERROR | 未在参考CSV列出/实际映射待核实 | enum / error_code | 不是错误发生次数 | H100-C22 |
| nvidia.fabric_health_mask | Fabric健康位掩码 / 174 | DCGM_FI_DEV_FABRIC_HEALTH_MASK | DCGM_FI_DEV_FABRIC_HEALTH_MASK / gauge / 注释 | bitmask / bitmask | 不支持位与异常位需区分 | H100-C22 |
| nvidia.fabric_health_summary | Fabric健康摘要 / 175 | DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY | DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY / gauge / 注释 | enum / enum | 不支持状态不等于故障 | H100-C22 |
| nvidia.pstate | GPU性能状态 / 190 | DCGM_FI_DEV_GPU_PSTATE | 未在参考CSV列出/实际映射待核实 | enum / enum | 只作解释上下文，不把非最高性能态一概告警 | H100-C23 |
| nvidia.pcie_replay | PCIe replay累计 / 202 | DCGM_FI_DEV_PCIE_REPLAY_TOTAL | DCGM_FI_DEV_PCIE_REPLAY_COUNTER / counter / 启用 | counter / events | 候选新增检测，阈值/重置按H100栈核实 | H100-C20 |
| nvidia.gpu_util | GPU利用率 / 203 | DCGM_FI_DEV_GPU_UTIL | DCGM_FI_DEV_GPU_UTIL / gauge / 启用 | gauge / percent | 高利用率常为正常训练；低利用率需作业上下文 | H100-C23 |
| nvidia.mem_copy_util | 显存控制器利用率 / 204 | DCGM_FI_DEV_MEM_COPY_UTIL | DCGM_FI_DEV_MEM_COPY_UTIL / gauge / 启用 | gauge / percent | 不是显存容量占用率 | H100-C23 |
| nvidia.xid_last | 最近XID代码 / 230 | DCGM_FI_DEV_XID_ERROR | DCGM_FI_DEV_XID_ERRORS / gauge / 启用 | gauge / error_code | 轮询最近值不保证事件完整，不得使用increase统计码值 | H100-C14 |
| nvidia.pcie_max_gen | PCIe最大链路代际 / 235 | DCGM_FI_DEV_PCIE_MAX_LINK_GEN | 未在参考CSV列出/实际映射待核实 | gauge / generation | 仅能力上下文，不能假设实际总达到最大值 | H100-C20 |
| nvidia.pcie_max_width | PCIe最大链路宽度 / 236 | DCGM_FI_DEV_PCIE_MAX_LINK_WIDTH | 未在参考CSV列出/实际映射待核实 | gauge / lanes | 与预期平台配置匹配 | H100-C20 |
| nvidia.pcie_gen | PCIe当前链路代际 / 237 | DCGM_FI_DEV_PCIE_LINK_GEN | 未在参考CSV列出/实际映射待核实 | gauge / generation | 需负载与预期配置，低负载可降速 | H100-C20 |
| nvidia.pcie_width | PCIe当前链路宽度 / 238 | DCGM_FI_DEV_PCIE_LINK_WIDTH | 未在参考CSV列出/实际映射待核实 | gauge / lanes | 需预期拓扑与配置，不跨形态套用 | H100-C20 |
| nvidia.power_violation_ns | 功率限制累计时长旧字段 / 240 | DCGM_FI_DEV_POWER_VIOLATION | DCGM_FI_DEV_POWER_VIOLATION / counter / 注释 | counter / nanoseconds | 已弃用候选；新秒字段为替代映射，不能相加或重复告警 | H100-C18 |
| nvidia.thermal_violation_ns | 热限制累计时长旧字段 / 241 | DCGM_FI_DEV_THERMAL_VIOLATION | DCGM_FI_DEV_THERMAL_VIOLATION / counter / 注释 | counter / nanoseconds | 先换算ns到s，不当事件次数 | H100-C17 |
| nvidia.fb_free | 显存剩余容量 / 251 | DCGM_FI_DEV_FB_FREE | DCGM_FI_DEV_FB_FREE / gauge / 启用 | gauge / MiB | 分母/保留内存口径待核实 | H100-C23 |
| nvidia.fb_used | 显存已用容量 / 252 | DCGM_FI_DEV_FB_USED | DCGM_FI_DEV_FB_USED / gauge / 启用 | gauge / MiB | 高占用不直接等于硬件故障 | H100-C23 |
| nvidia.ecc_mode | 当前ECC模式 / 300 | DCGM_FI_DEV_ECC_MODE | 未在参考CSV列出/实际映射待核实 | state / boolean | 字段不支持/缺失不能当作ECC关闭 | H100-C08 |
| nvidia.ecc_pending | 待生效ECC模式 / 301 | DCGM_FI_DEV_ECC_PENDING | 未在参考CSV列出/实际映射待核实 | state / boolean | 与当前模式区分，属于配置上下文 | H100-C08 |
| nvidia.ecc_sbe_volatile | 纠正ECC易失总计数 / 310 | DCGM_FI_DEV_ECC_SBE_VOL_TOTAL | DCGM_FI_DEV_ECC_SBE_VOL_TOTAL / counter / 注释 | counter / errors | 无H100统一呼叫阈值，先趋势/诊断分类 | H100-C09 |
| nvidia.ecc_dbe_volatile_total | 不可纠正ECC易失总计数 / 311 | DCGM_FI_DEV_ECC_DBE_VOL_TOTAL | DCGM_FI_DEV_ECC_DBE_VOL_TOTAL / counter / 注释 | counter / errors | 已有指标卡；不等于完整DRAM/SRAM或真实H100验收 | H100-C08 |
| nvidia.ecc_sbe_aggregate | 纠正ECC持久总计数 / 312 | DCGM_FI_DEV_ECC_SBE_AGG_TOTAL | DCGM_FI_DEV_ECC_SBE_AGG_TOTAL / counter / 注释 | counter / errors | 累计范围/清零限制按目标版本核实 | H100-C09 |
| nvidia.ecc_dbe_aggregate | 不可纠正ECC持久总计数 / 313 | DCGM_FI_DEV_ECC_DBE_AGG_TOTAL | DCGM_FI_DEV_ECC_DBE_AGG_TOTAL / counter / 注释 | counter / errors | 首次非零与近期新增分开解释 | H100-C08 |
| nvidia.dram_sbe_volatile | 设备内存纠正ECC易失明细 / 318 | DCGM_FI_DEV_ECC_SBE_VOL_DEV | 未在参考CSV列出/实际映射待核实 | counter / errors | DEV域到H100 DRAM的对应关系待核实 | H100-C09 |
| nvidia.dram_dbe_volatile | 设备内存不可纠正ECC易失明细 / 319 | DCGM_FI_DEV_ECC_DBE_VOL_DEV | 未在参考CSV列出/实际映射待核实 | counter / errors | 不能与总计数叠加造成重复 | H100-C08 |
| nvidia.dram_sbe_aggregate | 设备内存纠正ECC持久明细 / 328 | DCGM_FI_DEV_ECC_SBE_AGG_DEV | 未在参考CSV列出/实际映射待核实 | counter / errors | 与总计数及存储位置口径分别核实 | H100-C09 |
| nvidia.dram_dbe_aggregate | 设备内存不可纠正ECC持久明细 / 329 | DCGM_FI_DEV_ECC_DBE_AGG_DEV | 未在参考CSV列出/实际映射待核实 | counter / errors | 首次发现历史非零不冒充近期新增 | H100-C08 |
| nvidia.sram_sbe_volatile | SRAM纠正ECC易失明细 / 342 | DCGM_FI_DEV_ECC_SBE_VOL_SRM | 未在参考CSV列出/实际映射待核实 | counter / errors | SRM为源码字段命名，具体计数口径待核实 | H100-C09 |
| nvidia.sram_dbe_volatile | SRAM不可纠正ECC易失明细 / 343 | DCGM_FI_DEV_ECC_DBE_VOL_SRM | 未在参考CSV列出/实际映射待核实 | counter / errors | 不可据总计数重建bank级RMA判据 | H100-C08 |
| nvidia.sram_sbe_aggregate | SRAM纠正ECC持久明细 / 344 | DCGM_FI_DEV_ECC_SBE_AGG_SRM | 未在参考CSV列出/实际映射待核实 | counter / errors | 不与汇总和其他细分重复相加 | H100-C09 |
| nvidia.sram_dbe_aggregate | SRAM不可纠正ECC持久明细 / 345 | DCGM_FI_DEV_ECC_DBE_AGG_SRM | 未在参考CSV列出/实际映射待核实 | counter / errors | 与SRAM超阈值标志分开 | H100-C08 |
| nvidia.sram_exceeded | SRAM超阈值标志 / 346 | DCGM_FI_DEV_SRAM_EXCEEDED | 未在参考CSV列出/实际映射待核实 | state / boolean | 官方标志候选，不能从ECC总数代算 | H100-C10 |
| nvidia.remap_bank_max | 重映射资源Max桶 / 385 | DCGM_FI_DEV_BANK_REMAP_AVAIL_MAX | 未在参考CSV列出/实际映射待核实 | gauge / banks | 表示资源分桶，不是错误计数 | H100-C13 |
| nvidia.remap_bank_high | 重映射资源High桶 / 386 | DCGM_FI_DEV_BANK_REMAP_AVAIL_HIGH | 未在参考CSV列出/实际映射待核实 | gauge / banks | 不能自行映射为RMA标准 | H100-C13 |
| nvidia.remap_bank_partial | 重映射资源Partial桶 / 387 | DCGM_FI_DEV_BANK_REMAP_AVAIL_PARTIAL | 未在参考CSV列出/实际映射待核实 | gauge / banks | 结合其他桶及官方语义 | H100-C13 |
| nvidia.remap_bank_low | 重映射资源Low桶 / 388 | DCGM_FI_DEV_BANK_REMAP_AVAIL_LOW | 未在参考CSV列出/实际映射待核实 | gauge / banks | 少量资源不等于已失败 | H100-C13 |
| nvidia.remap_bank_none | 重映射资源None桶 / 389 | DCGM_FI_DEV_BANK_REMAP_AVAIL_NONE | 未在参考CSV列出/实际映射待核实 | gauge / banks | 资源告警阈值/处置需核实，不任意设数 | H100-C13 |
| nvidia.remapped_uncorrectable | 不可纠正重映射记录数 / 393 | DCGM_FI_DEV_ROW_REMAP_UNCORRECTABLE_TOTAL | DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS / counter / 启用 | counter / rows | InfoROM记录数，不等于硬件已生效行数 | H100-C13 |
| nvidia.remapped_correctable | 纠正重映射记录数 / 394 | DCGM_FI_DEV_ROW_REMAP_CORRECTABLE_TOTAL | DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS / counter / 启用 | counter / rows | 不直接用累计非零判断新故障 | H100-C13 |
| nvidia.remap_failed | 行重映射失败 / 395 | DCGM_FI_DEV_ROW_REMAP_FAILED | DCGM_FI_DEV_ROW_REMAP_FAILURE / gauge / 启用 | state / boolean | 需固定版本名称映射、失败保持与维护清除语义 | H100-C11 |
| nvidia.remap_pending | 行重映射待生效 / 396 | DCGM_FI_DEV_ROW_REMAP_PENDING | 未在参考CSV列出/实际映射待核实 | state / boolean | 维护状态不等于立即硬件失效 | H100-C12 |
| nvidia.nvlink_crc | Hopper NVLink CRC累计 / 497 | DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL | DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL / counter / 注释 | counter / errors | Hopper字段；不套用pre-Hopper或NVLink5+字段 | H100-C21 |
| nvidia.nvlink_recovery | Hopper NVLink recovery累计 / 498 | DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL | DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL / counter / 注释 | counter / events | 与正常负载/链路上下文区分 | H100-C21 |
| nvidia.nvlink_replay | Hopper NVLink replay累计 / 499 | DCGM_FI_DEV_NVLINK_REPLAY_TOTAL | DCGM_FI_DEV_NVLINK_REPLAY_TOTAL / counter / 注释 | counter / events | 候选新增检测，阈值需证据 | H100-C21 |
| nvidia.switch_link_fatal | 交换机端口fatal信息 / 782 | DCGM_FI_DEV_NVSWITCH_LINK_FATAL_ERRORS | 未在参考CSV列出/实际映射待核实 | unknown / unknown | 数值类型/口径未核实，禁止先当counter | H100-C22 |
| nvidia.switch_link_nonfatal | 交换机端口nonfatal信息 / 783 | DCGM_FI_DEV_NVSWITCH_LINK_NON_FATAL_ERRORS | 未在参考CSV列出/实际映射待核实 | unknown / unknown | 名称不足以证明是累计次数 | H100-C22 |
| nvidia.switch_link_replay | 交换机端口replay累计 / 784 | DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERROR_TOTAL | 未在参考CSV列出/实际映射待核实 | counter / events | 需switch+port身份与预期拓扑 | H100-C22 |
| nvidia.switch_link_recovery | 交换机端口recovery累计 / 785 | DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERROR_TOTAL | 未在参考CSV列出/实际映射待核实 | counter / events | 需核对硬件代际和采集实体 | H100-C22 |
| nvidia.sxid_fatal | 交换机最近fatal SXid / 856 | DCGM_FI_DEV_SXID_FATAL_ERROR | 未在参考CSV列出/实际映射待核实 | gauge / error_code | 值是SXid码，不是错误次数 | H100-C22 |
| nvidia.sxid_nonfatal | 交换机最近nonfatal SXid / 857 | DCGM_FI_DEV_SXID_NON_FATAL_ERROR | 未在参考CSV列出/实际映射待核实 | gauge / error_code | 必须按码和上下文分类 | H100-C22 |
| nvidia.switch_temp | NVSwitch温度 / 858 | DCGM_FI_DEV_NVSWITCH_TEMP_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 不把GPU门槛直接用于交换机 | H100-C22 |
| nvidia.switch_slowdown_temp | NVSwitch降频门槛 / 859 | DCGM_FI_DEV_NVSWITCH_TEMP_SLOWDOWN_CELSIUS | 未在参考CSV列出/实际映射待核实 | gauge / celsius | 门槛是否采到、是否适用待核实 | H100-C22 |
| nvidia.switch_link_state | NVSwitch端口状态 / 870 | DCGM_FI_DEV_NVSWITCH_LINK_STATUS | 未在参考CSV列出/实际映射待核实 | enum / enum | 只对预期启用端口判断，不支持/未使用不是故障 | H100-C22 |
| nvidia.gr_engine_ratio | 图形/计算引擎活动比率 / 1001 | DCGM_FI_PROF_GR_ENGINE_UTIL_RATIO | DCGM_FI_PROF_GR_ENGINE_ACTIVE / gauge / 启用 | gauge / ratio | 区间平均，不等价有效训练吞吐 | H100-C23 |
| nvidia.sm_active_ratio | SM活动比率 / 1002 | DCGM_FI_PROF_SM_UTIL_RATIO | DCGM_FI_PROF_SM_ACTIVE / gauge / 注释 | gauge / ratio | 不是百分数，需核实profiling支持/暂停状态 | H100-C23 |
| nvidia.sm_occupancy_ratio | SM occupancy比率 / 1003 | DCGM_FI_PROF_SM_OCCUPANCY_RATIO | DCGM_FI_PROF_SM_OCCUPANCY / gauge / 注释 | gauge / ratio | 高occupancy不自动代表高效率 | H100-C23 |
| nvidia.tensor_active_ratio | Tensor管线活动比率 / 1004 | DCGM_FI_PROF_TENSOR_UTIL_RATIO | DCGM_FI_PROF_PIPE_TENSOR_ACTIVE / gauge / 启用 | gauge / ratio | 按训练精度/阶段解释，不作统一低值故障 | H100-C23 |
| nvidia.dram_active_ratio | DRAM活动比率 / 1005 | DCGM_FI_PROF_DRAM_UTIL_RATIO | DCGM_FI_PROF_DRAM_ACTIVE / gauge / 启用 | gauge / ratio | 带宽活动不是容量占用 | H100-C23 |
| nvidia.pcie_tx_rate | Profiling PCIe发送速率 / 1009 | DCGM_FI_PROF_PCIE_TX_BYTES | DCGM_FI_PROF_PCIE_TX_BYTES / gauge / 启用 | gauge / bytes_per_second | 已是速率，不能再次rate | H100-C23 |
| nvidia.pcie_rx_rate | Profiling PCIe接收速率 / 1010 | DCGM_FI_PROF_PCIE_RX_BYTES | DCGM_FI_PROF_PCIE_RX_BYTES / gauge / 启用 | gauge / bytes_per_second | 不要与新增TOTAL累计字段混用 | H100-C23 |
| nvidia.nvlink_link_state | GPU NVLink链路状态 / 1508 | DCGM_FI_DEV_NVLINK_LINK_STATUS | 未在参考CSV列出/实际映射待核实 | enum / enum | link实体、Exporter是否提供均未知 | H100-C21 |
| nvidia.recovery_action | GPU恢复动作 / 1523 | DCGM_FI_DEV_GPU_RECOVERY_ACTION | 未在参考CSV列出/实际映射待核实 | enum / enum | 新字段存在不代表当前DCGM4.3栈或Exporter具有 | H100-C14 |
| nvidia.power_throttle_seconds | 功率限制累计秒新字段 / 1617 | DCGM_FI_DEV_GPU_POWER_THROTTLE_SECONDS_TOTAL | 未在参考CSV列出/实际映射待核实 | counter / seconds | 240替代候选，需目标DCGM版本映射，不能同时计数 | H100-C18 |
| nvidia.thermal_throttle_seconds | 热限制累计秒新字段 / 1618 | DCGM_FI_DEV_GPU_THERMAL_THROTTLE_SECONDS_TOTAL | 未在参考CSV列出/实际映射待核实 | counter / seconds | 241替代候选，需核实采集与单位 | H100-C17 |
| prometheus.target_up | 采集目标up / 非DCGM | scrape_status | up（Prometheus自生） | scrape_status / boolean | 实际target清单和维护状态仍需核实 | H100-C03, H100-C04, H100-C05 |
| inventory.expected_devices | 预期物理GPU清单 / 非DCGM | configuration | 未在参考CSV列出/实际映射待核实 | configuration / device_set | 不能仅从已上报设备推断集群应该有多少卡 | H100-C03, H100-C04 |
| inventory.hardware_stack | H100形态/软件栈/VBIOS清单 / 非DCGM | configuration | 未在参考CSV列出/实际映射待核实 | configuration / inventory | 无虚拟化已确认；MIG模式、实际版本仍未知 | H100-C01, H100-C02, H100-C15, H100-C20 |
| inventory.expected_links | 预期链路与对端清单 / 非DCGM | configuration | 未在参考CSV列出/实际映射待核实 | configuration / link_set | 没有预期拓扑不能把未使用端口当故障 | H100-C20, H100-C21, H100-C22 |
| prometheus.field_quality | 逐设备字段完整性与新鲜度 / 非DCGM | derived_query | 未在参考CSV列出/实际映射待核实 | derived_query / quality_state | 具体查询和序列身份需审定，不伪造已存在的质量指标 | H100-C05, H100-C06 |
| platform.evaluation_status | 数据源查询与规则评估状态 / 非DCGM | platform_api_or_metrics | 未在参考CSV列出/实际映射待核实 | platform_api_or_metrics / status | 平台原生API/指标名称尚待映射 | H100-C07 |
| platform.notification_status | 通知发送/重试/积压状态 / 非DCGM | platform_api_or_metrics | 未在参考CSV列出/实际映射待核实 | platform_api_or_metrics / status | 正向发送测试不等于失败/积压检测已实现 | H100-C07 |
| training.job_context | 训练任务分配与运行阶段 / 非DCGM | external_context | 未在参考CSV列出/实际映射待核实 | external_context / job_state | 现有GPU指标不能提供全部作业上下文；不擅自新增采集 | H100-C20, H100-C23 |
| host.power_context | 主机PSU/外部供电上下文 / 非DCGM | external_context | 未在参考CSV列出/实际映射待核实 | external_context / status | BMC/PSU输入若不存在，根因诊断明确缺口 | H100-C19, H100-C24 |
| diagnostics.results | 主动诊断/日志有序事件 / 非DCGM | external_diagnostic | 未在参考CSV列出/实际映射待核实 | external_diagnostic / diagnostic_result | 不在仅被动指标规则的默认执行范围 | H100-C14, H100-C24 |

逐项source_ids、正式卡片关联和规则引用见[metric-inventory.yaml](catalog/metric-inventory.yaml)。候选H100字段与R595/DCGM/Exporter适配必须单独核对，禁止直接整表导入或修改现有采集。
