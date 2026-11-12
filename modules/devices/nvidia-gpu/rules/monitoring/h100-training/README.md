# H100训练规则候选库

本目录完成输入契约、规则参数、处置和模拟验收的对应关系。生产默认策略为disabled，真实H100采集、版本、MIG及拓扑仍待现场验收。

[综合演示](http://localhost:19430) · [夜莺](http://localhost:17000) · [规则和指标目录](catalog.yaml)

## 规则

| 规则 | 严重度 | 目标持续时间 | 夜莺模拟验收 |
| --- | --- | --- | --- |
| [SRAM超阈值标志](rules/training.sram.md) | 1 | 0秒 | passed |
| [行重映射失败](rules/training.remap_failed.md) | 1 | 0秒 | passed |
| [行重映射待维护](rules/training.remap_pending.md) | 2 | 10秒 | passed |
| [GPU达到运行温度门槛](rules/training.gpu_thermal.md) | 2 | 10秒 | passed |
| [HBM达到运行温度门槛](rules/training.memory_thermal.md) | 2 | 10秒 | passed |
| [NVSwitch达到降速温度门槛](rules/training.switch_thermal.md) | 2 | 10秒 | passed |
| [软件热降频持续](rules/training.sw_thermal.md) | 2 | 10秒 | passed |
| [硬件热降频持续](rules/training.hw_thermal.md) | 1 | 10秒 | passed |
| [训练功率限制持续](rules/training.power_cap.md) | 3 | 10秒 | passed |
| [外部供电限制信号](rules/training.power_brake.md) | 2 | 10秒 | passed |
| [硬件slowdown状态](rules/training.hw_slowdown.md) | 2 | 10秒 | passed |
| [同步boost限制状态](rules/training.sync_boost.md) | 3 | 10秒 | passed |
| [时钟原因存在未核实位](rules/training.clock_unknown.md) | 3 | 10秒 | passed |
| [不可纠正ECC近期新增](rules/training.ecc_new.md) | 1 | 5秒 | passed |
| [近期热限制时长增加](rules/training.thermal_time.md) | 2 | 5秒 | passed |
| [PCIe replay近期活动](rules/training.pcie_replay.md) | 2 | 5秒 | passed |
| [Hopper NVLink CRC近期活动](rules/training.nvlink_crc.md) | 2 | 5秒 | passed |
| [Hopper NVLink recovery近期活动](rules/training.nvlink_recovery.md) | 2 | 5秒 | passed |
| [Hopper NVLink replay近期活动](rules/training.nvlink_replay.md) | 2 | 5秒 | passed |
| [NVSwitch端口replay近期活动](rules/training.switch_replay.md) | 2 | 5秒 | passed |
| [NVSwitch端口recovery近期活动](rules/training.switch_recovery.md) | 2 | 5秒 | passed |
| [XID节点事件待处置](rules/training.xid_node.md) | 1 | 0秒 | passed |
| [XID GPU重置复核](rules/training.xid_reset.md) | 1 | 0秒 | passed |
| [XID训练作业复核](rules/training.xid_app.md) | 2 | 0秒 | passed |
| [XID目录外码值待复核](rules/training.xid_unknown.md) | 2 | 0秒 | passed |
| [XID与部署范围需复核](rules/training.xid_scope.md) | 2 | 0秒 | passed |
| [NVSwitch fatal SXid待复核](rules/training.sxid_fatal.md) | 1 | 0秒 | passed |
| [NVSwitch nonfatal SXid待复核](rules/training.sxid_nonfatal.md) | 2 | 0秒 | passed |
| [预期GPU NVLink端口未连接](rules/training.gpu_link_down.md) | 2 | 10秒 | passed |
| [预期NVSwitch端口未活动](rules/training.switch_link_down.md) | 2 | 10秒 | passed |
| [训练负载下PCIe链路退化](rules/training.pcie_degraded.md) | 2 | 10秒 | passed |
| [预期Fabric Manager未就绪](rules/training.fabric_manager.md) | 2 | 10秒 | passed |
| [预期fabric能力或版本缺口](rules/training.fabric_capability.md) | 2 | 10秒 | passed |
| [fabric不健康或容量受限](rules/training.fabric_health.md) | 2 | 10秒 | passed |
| [预期设备观测消失](rules/training.entity_missing.md) | 2 | 5秒 | passed |
| [必需测量字段缺失](rules/training.field_missing.md) | 2 | 5秒 | passed |
| [测量样本陈旧](rules/training.input_stale.md) | 2 | 5秒 | passed |
| [测量值无效](rules/training.input_invalid.md) | 2 | 5秒 | passed |
| [重复采集输入](rules/training.input_duplicate.md) | 2 | 5秒 | passed |
| [模拟采集目标不可用](rules/training.collector_down.md) | 2 | 5秒 | passed |
| [H100平台-查询或评估失败](rules/platform_query_failure.md) | 1 | 5秒 | passed |
| [H100平台-评估调度停滞](rules/platform_evaluation_stall.md) | 1 | 5秒 | passed |
| [H100平台-主通知投递失败](rules/platform_notify_failure.md) | 1 | 0秒 | passed |
| [H100平台-状态适配器不可用](rules/platform_adapter_down.md) | 1 | 5秒 | passed |
| [H100平台-夜莺自监控抓取不可用](rules/platform_nightingale_metrics_missing.md) | 1 | 5秒 | passed |

## 诊断与上下文视图

这25项只读查询用于历史、趋势、统计域和事件上下文，不重复创建同一故障告警。

- [ecc.dbe_history.total](views/ecc.dbe_history.total.md)
- [ecc.sbe_trend.total](views/ecc.sbe_trend.total.md)
- [ecc.dbe_history.device_memory](views/ecc.dbe_history.device_memory.md)
- [ecc.sbe_trend.device_memory](views/ecc.sbe_trend.device_memory.md)
- [ecc.dbe_detail.device_memory](views/ecc.dbe_detail.device_memory.md)
- [ecc.dbe_history.sram](views/ecc.dbe_history.sram.md)
- [ecc.sbe_trend.sram](views/ecc.sbe_trend.sram.md)
- [ecc.dbe_detail.sram](views/ecc.dbe_detail.sram.md)
- [xid.node_incident_review](views/xid.node_incident_review.md)
- [xid.gpu_reset_review](views/xid.gpu_reset_review.md)
- [memory.remap_pending](views/memory.remap_pending.md)
- [thermal.gpu_operating_margin](views/thermal.gpu_operating_margin.md)
- [thermal.memory_operating_margin](views/thermal.memory_operating_margin.md)
- [clock.sw_thermal](views/clock.sw_thermal.md)
- [clock.hw_thermal](views/clock.hw_thermal.md)
- [clock.sw_power_cap](views/clock.sw_power_cap.md)
- [clock.hw_power_brake](views/clock.hw_power_brake.md)
- [clock.hw_slowdown](views/clock.hw_slowdown.md)
- [clock.sync_boost](views/clock.sync_boost.md)
- [clock.unknown_bits](views/clock.unknown_bits.md)
- [thermal.slowdown_seconds](views/thermal.slowdown_seconds.md)
- [pcie.replay_increase](views/pcie.replay_increase.md)
- [nvlink.crc_increase](views/nvlink.crc_increase.md)
- [nvlink.recovery_increase](views/nvlink.recovery_increase.md)
- [nvlink.replay_increase](views/nvlink.replay_increase.md)

## 验证入口

```bash
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh comprehensive suite --case hardware
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh comprehensive suite --case quality
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh comprehensive suite --case platform
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh comprehensive suite --case semantics
```

综合演示地址为 http://localhost:19430，夜莺业务组为H100训练综合演示。
