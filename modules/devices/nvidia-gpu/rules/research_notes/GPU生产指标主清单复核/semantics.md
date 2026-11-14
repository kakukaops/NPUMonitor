# GPU生产指标主清单的语义与来源复核

## 字段、枚举、单位与解除条件是否足够精确？

### Takeaway

第14篇可以作为生产需求主清单，但不能把当前软件的每个表达式当作已认证的通用硬件判据。需要明确“当前实现行为”和“生产目标契约”，尤其是NVLink状态、单位映射和设备恢复语义；官方字段定义、Collector声明与实际可采能力是三层证据。[Exporter指标参考](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)

### Cited Findings

| 检查项 | 官方定义/核查结果 | 第14篇建议措辞或边界 |
|---|---|---|
| GPU NVLink字段1508 | 固定DCGM头文件的canonical `DCGM_FI_DEV_NVLINK_LINK_STATUS`、旧别名`DCGM_FI_DEV_NVLINK_GET_STATE`使用`DCGM_FE_LINK`实体，并指向NVML field165；不是`dcgmGetNvLinkLinkStatus()`返回的0/1/2/3状态结构。NVML field状态为INACTIVE=0、ACTIVE=1、SLEEP=2；NVML620又增加ACTIVE_TRAFFIC_DISABLED=3。 | 不应笼统写“正数等于健康/可通流量”。现实现min0/max3（上界不含3）、0异常/>0解除，允许Sleep2解除；这是已有实现，不是已证明适合所有版本的生产恢复协议。若基线固定R595，3尚未属于其已准入集合，不能反过来断言排除3必然是该基线的代码bug。若要接620需扩枚举并另审3的处置。Sleep可正常低功耗，既不直接当掉链，也不能在目标要求traffic-ready时未经证明自动解除。 |
| NVSwitch端口字段870 | UNKNOWN=-1、OFF=0、SAFE=1、ACTIVE=2、ERROR=3。 | 与GPU field1508的1/2含义不同，禁止共用一个状态码表。当前预期端口非2为异常属于项目策略，SAFE是否通知须按期望拓扑/维护状态审定。-1和缺数为未知，不是健康。 |
| Fabric Manager170 | 固定DCGM枚举：0不支持、1未开始、2进行中、3成功、4失败、5未识别、6NVML过旧；7为枚举计数，不是有效状态。 | 仅OS声明需要Fabric的设备参与；1/2可能是启动过程，应有工程确认/宽限；3才是成功。0/5/6是能力/版本缺口，不能当硬件损坏或故障解除。当前合同0≤x<7与该枚举一致。 |
| Fabric健康175 | 0不支持、1健康、2不健康、3容量受限。 | 3与2应在解释/严重度上区别；0不能作为健康恢复。不要把health summary、health mask、FM状态混成同一枚举。 |
| NVSwitch856/857 | 固定头文件明确值是具体SXid代码，不是错误计数；别名NVSWITCH_FATAL_ERRORS/NON_FATAL_ERRORS容易误导。 | 持续观测码、非零判据及人工恢复是项目状态策略，不把increase(sxid_code)当事件次数。按硬件代际准入，不向所有GPU/Switch推广。 |
| 温度151/152/153/158 | 151为显存最大运行温度，152为GPU最大运行温度；153是距最近降速阈值的温度余量；158是降速温度。 | 现有“当前温度≥设备最大运行门槛”可保留原意；不要改称“GPU硬件slowdown温度”。应补温度余量/slowdown字段作为条件支持项，确认≤0的余量语义后再设计规则。5℃回差/60秒确认是项目参数。 |
| 时钟限制位 | Power Cap、Sync Boost、热限制与Power Brake是原因位，不是故障级别或业务影响证明。 | “原因存在”与“需处置故障”分开。位图新位应作为解码/版本缺口；不能把所有非零位统一升级为坏卡。 |
| FB_TOTAL/USED/FREE/RESERVED | Collector旧口径为MiB，FB_TOTAL是设备报告总量；板卡标称容量、ECC/驱动记账与进程可分配容量不能混同。canonical FB_USED_RATIO254定义Used/(Total−Reserved)，规范口径为0–1；旧宏FB_USED_PERCENT在固定头文件L4011只是该字段的别名，不能仅因名字PERCENT就认定已乘100。 | 优先记录canonical ratio的0–1口径；展示百分数时显式×100。可自定义Used/Total，但必须命名为另一种容量占比并明确分母，不得与field254混叫同一使用率。缺失、非正或单位不一时不算。 |
| 资源/Profiling | GPU_UTIL、MEM_COPY_UTIL是活动时间口径，不是理论算力效率和已分配显存占比。SM_ACTIVE、SM_OCCUPANCY、DRAM_ACTIVE是不同的区间平均活动/驻留比；等待内存的warp也可计SM active。 | 不以低GPU/Tensor/SM值在无上层目标时直接判故障；DRAM_ACTIVE不当作精确HBM GB/s。Profiling暂停可产生blank，资源组冲突需要协调，不补零为健康。 |
| PCIe/NVLink吞吐 | 固定CSV PCIe PROF TX/RX为bytes/s gauge，含协议头与数据。固定CSV L70 NVLINK_BANDWIDTH_TOTAL为gauge、MB/s；不是所有版本均如此。 | 对该已是速率的序列不再rate；方向值与聚合值不可直接相加。新NVLink5累计字段只在支持代际使用，H100不能直接继承。 |

来源定位：固定字段定义[DCGM 9fae2867头文件](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)（151–158、170–175、856–870、1508）；[固定DCGM structs枚举](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_structs.h)（dcgmFabricManagerStatus_t）；[NVML field value](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlFieldValueEnums.html)；[NVML620 NvLink](https://docs.nvidia.com/deploy/nvml-api/620/api/group__NvLink.html)；[NVML620变更](https://docs.nvidia.com/deploy/nvml-api/620/change-log.html)；[NVML R595 PDF宏值](https://docs.nvidia.com/deploy/pdf/NVML_API_Reference_Guide.pdf)；[固定Exporter CSV](https://raw.githubusercontent.com/NVIDIA/dcgm-exporter/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/index.html)；[Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)。

### Inferences

- 建议新增“版本化状态契约待审定”项，而不是把Sleep2直接认定故障，或在文档中悄悄宣称已有软件已经按ACTIVE=1解除。解除判据需先决定监控目标是“链路存在/可唤醒”还是“当前traffic-ready”。前者可能允许Sleep，后者需要额外证据；3则明确不能通流量。[NVML NvLink状态](https://docs.nvidia.com/deploy/nvml-api/620/api/group__NvLink.html)
- master必须承载Collector版本、canonical字段/ID、单位与转换规则、实体、合法枚举、unsupported/blank/invalid处理和当前支持状态；仅靠HELP/TYPE无法完成单位和语义验收。官方明确CSV类型被原样采用，未做语义匹配；commented选项不等于默认采集。[Exporter文档](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)
- 原代码/生成台账若与主文档目标不一致，应列“待实现差异”，不伪造已完成，也不为同步文档而更改线上配置。[当前指标契约](../../monitoring/os-sre/metrics.yaml)、[当前实现](../../scripts/build_os_sre.py)

### Gaps

- 本轮未取得实际GPU输出，不能给出目标环境每个字段的型号/驱动/采集可用性证明。即使固定源码定义存在，也必须由接入能力检查标支持、unsupported或unknown；这属于部署契约核对，不要求制造真实硬件故障。[Exporter运行输出边界](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)
- 当前NVLink生产恢复政策没有形成逐版本完整协议；现有表达式与模拟验收不能证明Sleep或新枚举值在目标硬件的业务可用性。[当前规则卡](../../monitoring/os-sre/cards/os_sre.gpu_link_down.md)

## 还有哪些重要健康状态不能从已列指标推断？

### Takeaway

生产主清单至少应显式处置恢复动作、不可修复内存、InfoROM、重映射资源余量、温度余量与传统page retirement等维度：按支持能力纳入或解释不适用，而不是默认为原37项已经覆盖全部健康。NVIDIA的软件部署检查与被动健康检查就包含这些维度。[DCGM软件检查](https://docs.nvidia.com/datacenter/dcgm/latest/reference/diagnostics/plugins/software.html)、[dcgmi health](https://docs.nvidia.com/datacenter/dcgm/latest/reference/command-line-reference/dcgmi/dcgmi-health.html)

### Cited Findings

| 建议明确处置项 | 官方名称/实体/语义 | master中的建议位置和告警/恢复边界 |
|---|---|---|
| 驱动恢复动作 | `DCGM_FI_DEV_GPU_RECOVERY_ACTION`1523，旧别名`DCGM_FI_DEV_GET_GPU_RECOVERY_ACTION`；GPU枚举，NVML定义NONE、RESET、NODE_REBOOT、DRAIN_P2P、DRAIN_AND_RESET，更新版本还可能有IMEX/BUS_RESET/SYSTEM_REBOOT。 | 健康/驱动状态，条件必选。代码不按大小排序；非NONE作为待处置线索，按版本查官方动作。当前NONE只能说明无该项恢复请求，不单独证明整卡修好；不得新增自动重置/重启动作。 |
| 不可修复内存 | `DCGM_FI_DEV_MEMORY_UNREPAIRABLE`1507，旧别名`...MEMORY_UNREPAIRABLE_FLAG`；1有不可修复错误、0无该标志。 | 内存可靠性，按版本/型号支持；1应进入维护复核，0不是整卡健康证明。当前OS契约未接入，不写成已有告警。 |
| InfoROM有效性 | `DCGM_FI_DEV_INFOROM_VALID`84，旧别名`...INFOROM_CONFIG_VALID`；读取并核验InfoROM checksum。 | 固件/健康维护状态；InfoROM corrupt是DCGM明确健康维度。需确认返回定义及读取成本，不以checksum数值本身非零认定故障；版本字符串是元数据。 |
| 重映射剩余资源/分桶 | 固定字段385–389 `BANK_REMAP_AVAIL_MAX/HIGH/PARTIAL/LOW/NONE`及旧别名`BANKS_REMAP_ROWS_AVAIL_*`。 | 维护容量趋势，按支持能力选用；桶内值是相关banks的数量，不能把LOW=1解读为整卡只剩1行。官方说明每bank精确可用行数参考值并不通过API直接给出。 |
| 已记录重映射数量 | `ROW_REMAP_CORRECTABLE_TOTAL`394与`UNCORRECTABLE_TOTAL`393，旧采集名`CORRECTABLE_REMAPPED_ROWS/UNCORRECTABLE_REMAPPED_ROWS`。 | 应把新增行定义收紧为“InfoROM记录的重映射条目数”，不是已经在硬件执行的重映射行数；pending说明下次reset才应用。 |
| 页退休 | 390/391累计SBE/DBE退休页；392 pending布尔；旧别名RETIRED_SBE/DBE/PENDING。 | 传统page-retirement适用架构按条件纳入；不能和Ampere+ row remap简单相加、强制所有卡必选。pending是状态gauge，不能因某版CSV误写counter就increase(pending)。 |
| 热余量与降速/关断门槛 | GPU153余量、GPU158slowdown；NVSwitch860shutdown。 | 温控风险、维护，不等价于当前max-op告警。模型不支持时显式缺口；不捏造统一温度值或硬件阈值。 |

上述字段ID/别名来自[固定DCGM头文件](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)。恢复动作语义见[NVIDIA Error Recovery Flags](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/error-recovery-and-response-flags.html)、[NVML620枚举](https://docs.nvidia.com/deploy/nvml-api/620/api/group__nvmlVgpuStructs.html)。重映射统计语义和bucket边界见[User Visible Statistics](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/user-visible-statistics.html)。

### Inferences

- RMA不能由项目自选ECC总量阈值或某个非零计数直接决定：NVIDIA说明须由Field Diagnostic确定，SRAM/row-remap flag仅是相关依据，型号不同还可能走不同RAS维修流程。[NVIDIA RMA Policy](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/rma-policy-thresholds-for-row-remapping.html)
- 生产完整性是已声明硬件、版本和OS SRE问题域内每个维度有去向，不是所有NVIDIA字段对所有GPU都必须可采。H100物理卡、带/不带NVSwitch、NVLink4与NVLink5必须区别；主清单应有必选/条件/可选/排除及理由。[NVLink代际支持](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/topology-and-links.html)

### Gaps

- 没有证据支持将全部新健康字段认定为H100/R595已支持；须保留条件准入，不因字段ID在最新头文件中存在就升级为基线必选。当前软件这些新增项没有规则/执行契约，不能用文档补齐代替实现。[字段可用性边界](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)

## 生产主文档应怎样标注已知限制而不虚报完成？

### Takeaway

可将第14篇提升为需求和语义权威，但实际运行能力必须仍引用版本化实现和证据，主文档不能用“规划要求”覆盖历史事实。完整XID采集和逐版本映射仍是明确缺口。[当前运行证据](../../runtime/evidence/summary.json)

### Cited Findings

- 固定CSV明确`DCGM_FI_DEV_XID_ERRORS`是最近错误码；数值快照不是时间完整的事件序列。官方Exporter另外提供可配置的XID窗口/累计族，也不意味着当前部署已启用这些扩展。[固定Collector L25,L35–36](https://raw.githubusercontent.com/NVIDIA/dcgm-exporter/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)、[Exporter专属指标](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)
- DCGM被动健康检查解释启用watch的保留样本，不等价于主动压力诊断通过；健康watch随hostengine重启丢失，约需先积累一段时间。不能把“Healthy”当作所有子系统已覆盖。[dcgmi health](https://docs.nvidia.com/datacenter/dcgm/latest/reference/command-line-reference/dcgmi/dcgmi-health.html)
- Profiling字段是interval average；资源冲突会要求pause，paused watches返回blank，因此缺失应显示覆盖缺口，不能当低利用率或健康零值。[DCGM Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)

### Inferences

- 对每个主清单项分别写清“生产要求”和“实现状态”（当前已支持/待补/按能力/仅元数据/外部采集/排除）。记录entity/labels、采样/计数复位、合法枚举、来源固定版本、derived公式和触发/确认/恢复/unknown，便于后续从同一主清单生成接入实现。
- 元数据与动态遥测分开；计数先按设备身份算增量/速率后再聚合，pending布尔和当前状态不做rate，代码枚举不做increase，速率gauge不做二次rate。事件关联及通知收敛仍按用户要求暂缓，不为“完整主清单”新增这些功能。
- 当前通知失败counter未覆盖所选实际发送路径，禁用边界保持；文档查漏不应把其变成生产已保障的投递失败检测。[实际负向证据](../../runtime/evidence/notification-counter-negative.json)

### Gaps

- 主文档查验能证明候选清单闭合和语义可追溯，不能证明当前软件已经实现新增采集、适用所有GPU或通过真实故障/生产长稳。应保留需要实现和发布前关闭的差异清单，不把“文档完整”写作“现在可直接搬运所有规则上线”。[当前发布边界](../../docs/13-生产规则运行与验收.md)
