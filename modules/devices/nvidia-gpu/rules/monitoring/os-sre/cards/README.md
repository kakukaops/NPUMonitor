# OS SRE规则卡

| 规则 | 类型 | 状态 |
|---|---|---|
| [SRAM超阈值标志](os_sre.sram.md) | stateful | candidate |
| [行重映射失败](os_sre.remap_failed.md) | stateful | candidate |
| [行重映射待维护](os_sre.remap_pending.md) | stateful | candidate |
| [GPU达到运行温度门槛](os_sre.gpu_thermal.md) | stateful | candidate |
| [HBM达到运行温度门槛](os_sre.memory_thermal.md) | stateful | candidate |
| [NVSwitch达到降速温度门槛](os_sre.switch_thermal.md) | stateful | candidate |
| [软件热降频持续](os_sre.sw_thermal.md) | stateful | candidate |
| [硬件热降频持续](os_sre.hw_thermal.md) | stateful | candidate |
| [设备功率限制状态（信息）](os_sre.power_cap.md) | stateful | candidate |
| [外部供电限制信号](os_sre.power_brake.md) | stateful | candidate |
| [硬件slowdown状态](os_sre.hw_slowdown.md) | stateful | candidate |
| [同步boost限制状态](os_sre.sync_boost.md) | stateful | candidate |
| [时钟原因存在未核实位](os_sre.clock_unknown.md) | stateful | candidate |
| [不可纠正ECC近期新增](os_sre.ecc_new.md) | stateful | candidate |
| [近期热限制时长增加](os_sre.thermal_time.md) | stateful | candidate |
| [PCIe replay近期活动](os_sre.pcie_replay.md) | stateful | candidate |
| [Hopper NVLink CRC近期活动](os_sre.nvlink_crc.md) | stateful | candidate |
| [Hopper NVLink recovery近期活动](os_sre.nvlink_recovery.md) | stateful | candidate |
| [Hopper NVLink replay近期活动](os_sre.nvlink_replay.md) | stateful | candidate |
| [NVSwitch端口replay近期活动](os_sre.switch_replay.md) | stateful | candidate |
| [NVSwitch端口recovery近期活动](os_sre.switch_recovery.md) | stateful | candidate |
| [XID节点事件待处置](os_sre.xid_node.md) | stateful | candidate |
| [XID GPU重置复核](os_sre.xid_reset.md) | stateful | candidate |
| [XID进程/软件排查线索（OS侧）](os_sre.xid_app.md) | stateful | candidate |
| [XID与部署范围需复核](os_sre.xid_scope.md) | stateful | candidate |
| [XID目录外码值待复核](os_sre.xid_unknown.md) | stateful | candidate |
| [NVSwitch fatal SXid待复核](os_sre.sxid_fatal.md) | stateful | candidate |
| [NVSwitch nonfatal SXid待复核](os_sre.sxid_nonfatal.md) | stateful | candidate |
| [预期GPU NVLink端口未连接](os_sre.gpu_link_down.md) | stateful | candidate |
| [预期NVSwitch端口未活动](os_sre.switch_link_down.md) | stateful | candidate |
| [持续PCIe传输时链路低于资产预期](os_sre.pcie_degraded.md) | stateful | candidate |
| [预期Fabric Manager未就绪](os_sre.fabric_manager.md) | stateful | candidate |
| [预期fabric能力或版本缺口](os_sre.fabric_capability.md) | stateful | candidate |
| [fabric不健康或容量受限](os_sre.fabric_health.md) | stateful | candidate |
| [预期设备观测消失](os_sre.entity_missing.md) | direct | candidate |
| [必需测量字段缺失](os_sre.field_missing.md) | direct | candidate |
| [测量样本陈旧](os_sre.input_stale.md) | direct | candidate |
| [测量值无效](os_sre.input_invalid.md) | direct | candidate |
| [重复采集输入](os_sre.input_duplicate.md) | direct | candidate |
| [DCGM采集目标不可用](os_sre.collector_down.md) | direct | candidate |
| [硬件身份标签缺失](os_sre.identity_missing.md) | direct | candidate |
| [平台-查询或评估失败](os_sre.platform_query_failure.md) | direct | candidate |
| [平台-评估调度停滞](os_sre.platform_evaluation_stall.md) | direct | candidate |
| [平台-主通知投递失败](os_sre.platform_notify_failure.md) | direct | blocked_missing_input |
| [平台-状态适配器不可用](os_sre.platform_adapter_down.md) | direct | candidate |
| [平台-夜莺自监控抓取不可用](os_sre.platform_nightingale_metrics_missing.md) | direct | candidate |
