# 当前GPU规则指标分类与覆盖核查

## 当前范围与跨模块覆盖是什么

### Takeaway

用户指出资源使用未出现是准确的：当前第14篇是以故障规则为中心的OS SRE清单，缺少独立的GPU繁忙度、显存容量占用、计算活动、显存访问活动、实际功耗和频率观测。缺口限定于当前OS SRE契约与说明表，不能表述为整个仓库从未考虑这些字段。

### Cited Findings

- 当前OS SRE catalog有46项规则、25个诊断视图、38个契约条目，其中37个名称以`DCGM_`开头，另1项为内部`os_sre_recovery_verified`。第14篇57行由46项规则、8项仅诊断ECC字段、1项可选gateway_health和2项Watchdog构成。— [当前catalog](../../monitoring/os-sre/catalog.json)、[第14篇](../../docs/14-GPU监控指标与告警规则说明表.md)
- 37个DCGM字段中没有`DCGM_FI_DEV_GPU_UTIL`、`MEM_COPY_UTIL`、`FB_USED`、`FB_FREE`，没有实际`POWER_USAGE`、`SM_CLOCK`、`MEM_CLOCK`；仅有时钟原因位和温度，不能将这些状态字段说成已有功耗或频率可视化。— [当前metrics.yaml](../../monitoring/os-sre/metrics.yaml)
- 公共指标台账有92项候选/reference inventory，已列GPU_UTIL、MEM_COPY_UTIL、FB_USED/FREE、功耗、SM/显存时钟、Profiling SM/Tensor/DRAM活动等；其中actual_collection等字段是unknown，不能作为当前规则链路已经实现的证据。— [公共92项候选台账](../../../common/monitoring/catalog/metric-inventory.yaml)
- ML通用bindings显式包含`gpu_temp`、`memory_temp`、`power`、`sm_clock`、`mem_clock`、`util`、`mem_util`、`fb_used`等，并有旧版/job_running绑定；当前v4场景主要使用前7项，场景清单不把FB_USED作为当前四类场景的核心输入。绑定存在不等于当前OS SRE实现，也不代表全仓库所有场景都已使用。— [ML bindings](../../../ml/config/bindings.json)、[ML当前DCGM场景契约](../../../ml/docs/10-DCGM场景清单与数据契约.md)、[机器可读场景](../../../ml/config/dcgm-scenarios.json)
- 当前只读规则与实际平台的46项清单、45启用/1禁用计数，以及32项运行测试属于已有实现证据；本次分类文档不能修改这些运行状态或制造新规则。— [当前UI清理验收](../../runtime/evidence/current-ui-cleanup.json)、[双通道方案](../../docs/16-XID事件与指标状态双通道监控方案.md)

### Inferences

- 文档标题仍可叫“指标与告警规则说明表”，但必须覆盖“观测而不告警”的指标，不能以“无通用告警阈值”为理由省略资源和性能指标。
- “监控领域”应与“检测角色”和“支持状态”正交：例如NVSwitch SXID的主领域是互联Fabric，角色是SXID事件检测；GPU内存ECC的主领域是健康错误，不应塞入显存带宽。
- 首批推荐补齐基础观测，不默认增加在线故障规则；高利用率、高显存占用、低Tensor活动均不能在缺乏工作负载上下文时直接解释为故障。

### Gaps

- 未检查实际物理GPU的Exporter端点；当前接入仍是声明契约模拟源。不能声称新增候选字段已被现有Prometheus抓取。
- 最新Exporter命名和单位可能已规范化；拟新增字段名应锚定本项目公共台账中的固定CSV映射，不混用新文档的规范名称与旧别名。具体最新别名/单位由NVIDIA专题研究核实。

## 推荐怎样分类全部现有行

### Takeaway

采用8个对象域：资产身份配置、健康错误、资源容量占用、计算活动与性能信号、显存访问与带宽、温度功耗时钟、互联Fabric、监控链路可靠性。所有当前57行可完整归位，其中资源/计算/显存带宽/独立资产观测是应明确补充的空白领域。

### Cited Findings

以下完整映射根据[当前46项规则定义](../../monitoring/os-sre/catalog.json)、[第14篇现有57行](../../docs/14-GPU监控指标与告警规则说明表.md)逐项核对；条目为rule_id去掉`os_sre.`前缀。

| 主分类 | 当前规则数 | 当前其他行数 | 对应规则/指标 |
|---|---:|---:|---|
| 1 资产、身份与配置 | 0 | 0 | 当前只有身份标签、静态OS预期清单及缺失检测，尚无独立资产概览指标行；建议增补信息/标签/事实视图 |
| 2 GPU健康与错误 | 9 | 8 | 规则：`xid_node`、`xid_reset`、`xid_app`、`xid_scope`、`xid_unknown`、`sram`、`remap_failed`、`remap_pending`、`ecc_new`；另8个ECC仅诊断指标见下 |
| 3 资源容量与占用 | 0 | 0 | 待补：GPU_UTIL、FB_USED/FREE/TOTAL等，明确繁忙时间与容量占用的差别 |
| 4 计算活动与性能信号 | 0 | 0 | 待补：SM_ACTIVE、SM_OCCUPANCY、Tensor activity等；不等同实际任务吞吐 |
| 5 显存访问与带宽 | 0 | 0 | 待补：MEM_COPY_UTIL、DRAM_ACTIVE；这两者不表示显存容量占用，也不能直接当HBM bytes/s |
| 6 温度、功耗与时钟 | 11 | 0 | `gpu_thermal`、`memory_thermal`、`switch_thermal`、`sw_thermal`、`hw_thermal`、`power_cap`、`power_brake`、`hw_slowdown`、`sync_boost`、`clock_unknown`、`thermal_time`；本类当前没有实际功耗/频率字段 |
| 7 互联与Fabric | 14 | 0 | `sxid_fatal`、`sxid_nonfatal`、`pcie_replay`、`nvlink_crc`、`nvlink_recovery`、`nvlink_replay`、`switch_replay`、`switch_recovery`、`gpu_link_down`、`switch_link_down`、`pcie_degraded`、`fabric_manager`、`fabric_capability`、`fabric_health` |
| 8 监控链路可靠性 | 12 | 3 | 数据质量7项：`entity_missing`、`field_missing`、`input_stale`、`input_invalid`、`input_duplicate`、`collector_down`、`identity_missing`；平台5项：`platform_query_failure`、`platform_evaluation_stall`、`platform_notify_failure`、`platform_adapter_down`、`platform_nightingale_metrics_missing`；额外gateway_health和2项Watchdog |
| 合计 | 46 | 11 | 57行，保持原六列、条件、来源和支持状态 |

健康领域8个仅诊断字段（全部保留，不新增告警）：

- `DCGM_FI_DEV_ECC_DBE_VOL_DEV`
- `DCGM_FI_DEV_ECC_DBE_VOL_SRM`
- `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL`
- `DCGM_FI_DEV_ECC_SBE_VOL_DEV`
- `DCGM_FI_DEV_ECC_SBE_VOL_SRM`
- `DCGM_FI_DEV_ECC_DBE_AGG_TOTAL`
- `DCGM_FI_DEV_ECC_DBE_AGG_DEV`
- `DCGM_FI_DEV_ECC_DBE_AGG_SRM`

唯一DCGM字段按主要对象域计数为：健康13、温度功耗时钟8、互联16，总计37；规则可能重复使用字段，不能用表行数当唯一指标数。来源：[契约字段](../../monitoring/os-sre/metrics.yaml)。

### Inferences

- 建议第14篇使用8个分节，每节重复原六列表头。在同一领域内部先列当前支持项，随后列“建议补充/未接入”项。分类可通过节标题表达，不必额外扩展第7列。
- 每个领域保留原角色标记：XID、SXID、指标独立检测、运行提示、诊断、数据质量、平台健康；另在候选行的规则列醒目标注“建议补充；当前OS SRE未接入；无已部署告警”。
- 温度既有GPU/HBM也有NVSwitch，以传感器功能统一放在温度类；交换机错误、端口和Fabric则放互联类。这样既避免一个规则重复出现，也不混淆设备类型。
- `entity_missing`继续放采集质量。它依据清单发现观测消失，并非已经拥有独立资产数量/实际可用卡资源统计面板。可在资产类交叉链接说明，不重复行和计数。

### Gaps

- 这些8类是结合公开最佳实践、项目现状及用户关切的设计，不是NVIDIA或云厂商发布的统一行业分类标准。
- 当前已部署运行规则本身没有主领域元数据；本次只要求文档分类，不应顺手改catalog、在线规则或代码以制造分类已经产品化的印象。

## 哪些遗漏应优先补充且怎样避免虚构告警

### Takeaway

优先补齐资源使用与容量、实际功耗/频率；随后补计算/内存活动和互联吞吐。新增项默认用于可视化/诊断，只有具备可验证运行前提时另行设计规则，不在本轮文档中发明阈值或宣称已经上线。

### Cited Findings

以下名称取自项目已固定参考CSV映射，单位为公共台账的候选契约；实际安装版本仍需核对。来源：[公共92项指标台账](../../../common/monitoring/catalog/metric-inventory.yaml)、[ML bindings](../../../ml/config/bindings.json)。

| 优先级 | 分类 | 建议字段 | 现有仓库覆盖与文档应写的状态 |
|---|---|---|---|
| P1 | 资源容量占用 | `DCGM_FI_DEV_GPU_UTIL` | 公共台账和ML绑定已有；当前OS SRE37字段契约未纳入；繁忙时间百分比，不是卡资源分配比例或真实算力效率 |
| P1 | 资源容量占用 | `DCGM_FI_DEV_FB_USED`、`DCGM_FI_DEV_FB_FREE` | 公共台账已有；ML通用binding有FB_USED；当前OS SRE未接入；固定参考口径MiB，不能混成百分比 |
| P1 | 资源容量占用 | 总显存、可分配显存、占用比的明确口径 | `FB_TOTAL`、保留显存名称与当前Exporter支持需由NVIDIA研究核实；不能直接把used+free说成物理总量，不能忽略驱动保留等分母差异 |
| P1 | 温度功耗时钟 | `DCGM_FI_DEV_POWER_USAGE`、`DCGM_FI_DEV_SM_CLOCK`、`DCGM_FI_DEV_MEM_CLOCK` | 公共台账和ML场景已涉及；当前OS SRE没有实际W/MHz值；不能用POWER_CAP/原因位替代实际测量 |
| P1/P2 | 显存访问与带宽 | `DCGM_FI_DEV_MEM_COPY_UTIL` | 公共台账、ML当前场景已有；当前OS SRE未接入；是控制器活动百分比，不是显存使用容量，也不是精确HBM bytes/s |
| P2 | 计算活动 | `DCGM_FI_PROF_SM_ACTIVE`、`DCGM_FI_PROF_SM_OCCUPANCY`、`DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` | 公共台账已有profiling候选；固定CSV映射下为ratio；不能未经换算直接标百分比；支持、暂停、采样复用条件需核验 |
| P2 | 显存访问与带宽 | `DCGM_FI_PROF_DRAM_ACTIVE` | 公共台账已有，ratio；不能改称HBM已使用容量或直接精确字节速率 |
| P2 | 互联吞吐 | 已有PCIe TX/RX bytes/s；新增NVLink TX/RX候选 | PCIe profiling两字段已经在37字段契约里，不算新增/遗漏；它们目前用于活跃链路降级判断，也可做展示。NVLink方向吞吐字段需按固定版本确认名字/单位，当前OS SRE没有这些吞吐指标 |
| P2 | 温度功耗时钟 | 总能耗、功率上限/受限时长 | 公共台账含功率上限、功率违规累计等候选；总能耗具体名字/单位需NVIDIA研究确认；无业务产出不能声称实现训练能效 |
| P2 | 资产身份配置 | UUID、PCI地址、型号、驱动/DCGM/Exporter版本、GPU总数/可见数、MIG配置 | 现有身份和OS预期清单提供部分事实，但不是完整资产可观测性；优先信息/标签展示和一致性核查，不凭空构造通用DCGM字段名 |

### Inferences

- 资源与性能的“遗漏”应在表中补为可观测项，不等于必须为每个metric指定一条故障告警。
- 无上层作业上下文，不能默认“GPU利用率低于10%持续10分钟”“Tensor不活跃”就是故障或空转浪费；这类指标先观测，后续有可比运行约束时再提策略。
- 显存高占用可能是正常缓存/模型驻留，不能直接表示硬件错误。若后续确需容量关注，必须明确连续时长、剩余容量、保留内存及运行目标，不能在本次表里擅定80%/90%阈值。
- 实际业务性能（tokens/s、samples/s、step latency）缺少作业信息，本轮不作为可由DCGM单独实现的指标；主机CPU、内存、磁盘和网络可用系统监控模块补足，不能把它们写成已有GPU DCGM字段。
- 保持事件关联和通知收敛“本期不做”的明确范围。新增观测不接入通知，旧46条检测和源台账不变；最终应验证当前57行和所有37字段仍在，46个rule_id唯一，六列完整，新增候选行有状态与来源。

### Gaps

- `FB_TOTAL`/reserved memory、NVLink吞吐和总能耗具体映射需另一研究者的官方资料补齐，不能仅靠记忆写成已确定部署契约。
- 实际硬件支持/数据可采性、profile多路复用开销、没有业务信息下的性能阈值均未在本次本地审计中证明。
