# H100覆盖目标与综合实现映射

本表补充原始24项目标审查，区分模拟实现和现场适用性。规则卡见[候选目录](README.md)，输入字段、单位和数值有效性见[catalog.yaml](catalog.yaml)。真实H100验证全部为not_run。

| 覆盖目标 | 当前实现与证据 | 现场门槛或边界 |
| --- | --- | --- |
| C01 型号、实体模式 | GPU/交换机/链路分别建身份，模拟实体显式标记 | PCIe/SXM/NVL、MIG状态与真实拓扑待核实 |
| C02 字段语义 | 42项输入契约；固定DCGM字段ID及类型、单位、范围 | 现场Exporter导出支持待核实 |
| C03 采集失败 | collector_down | 生产目标清单与维护策略 |
| C04 设备消失 | entity_missing，含GPU、预期链路、交换机 | 从未出现设备必须有预期清单 |
| C05 缺失/陈旧 | field_missing、input_stale，含HBM门槛缺失 | 现场采样周期、新鲜度参数 |
| C06 无效/重复 | input_invalid、input_duplicate，含未知交换机状态 | 原始权限/不支持原因需采集日志 |
| C07 平台失败 | 5条查询、调度、通知和组件健康规则 | 夜莺停机不能由自身可靠通知，独立看门狗保留可用性记录；生产需外部监控 |
| C08 不可纠正ECC | ecc_new单一汇总告警；历史与分域只读视图 | 现场选择主数据源，核对重置与累计域 |
| C09 可纠正ECC | total/device_memory/sram趋势视图 | 未审定CE风暴阈值，不新增无依据故障阈值 |
| C10 SRAM阈值 | sram | 官方标志的实际支持；不重建RMA算法 |
| C11 重映射失败 | remap_failed | 现场支持和维修复核 |
| C12 重映射待维护 | remap_pending | 维护窗口及作业退出流程 |
| C13 重映射资源与记录 | 原始候选字段台账保留；本轮未新增资源耗尽规则 | 尚无审定的资源策略；不能据累计记录数推断RMA |
| C14 XID分类 | node/reset/app/unknown/scope五类规则、上下文视图；79→45→0不会自动清除 | 当前为last-XID指标模拟；完整有序事件采集和真实恢复动作尚未实现 |
| C15 InfoROM/驱动管理 | 原始候选台账保留 | 实际字段支持与状态含义待核实，本轮未新增生产判断 |
| C16 GPU/HBM温度 | gpu_thermal、memory_thermal及温度余量视图 | 设备提供运行门槛，生产回差需验收 |
| C17 热降频 | sw_thermal、hw_thermal、thermal_time | 位定义、时长单位和持续参数 |
| C18 功率限制 | power_cap信息规则及观察视图 | 不把正常功率封顶当作硬件损坏 |
| C19 外部限制 | power_brake、hw_slowdown、sync_boost | 主机/BMC供电根因仍需外部输入 |
| C20 PCIe | pcie_replay、pcie_degraded；空闲降速抑制 | 预期代际/宽度与作业上下文需真实配置 |
| C21 Hopper NVLink | CRC/recovery/replay及预期端口掉线；未使用端口不报警 | 预期端口与对端拓扑需现场清单 |
| C22 NVSwitch/fabric | 交换机温度、SXid、端口、错误活动；FM状态/能力/fabric健康 | 仅存在并依赖NVSwitch/FM的拓扑适用 |
| C23 容量效率 | 保留可选策略输入台账，本轮不设利用率故障阈值 | 需作业阶段、profiling及业务策略 |
| C24 主动诊断边界 | 文档保留外部诊断和人工操作要求 | 不自动重启、隔离或执行主动诊断 |

这三项交付的完成范围是候选卡、夜莺集成及无GPU模拟验收。C13/C15/C23的现场策略、完整事件采集以及生产发行版门禁仍按开发计划跟踪，不能以本表推断已完成生产覆盖。
