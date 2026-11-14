# NVIDIA GPU监控分类与缺失指标核查

## 分类应怎样设计，才有官方实践依据？

### Takeaway

建议按“监控对象/问题域”组织主目录，将检测角色作为正交标注。NVIDIA自身的监控同时包含利用率、显存占用、功率、温度、时钟、错误和传输吞吐，因此仅围绕健康/XID组织指标清单会遗漏日常容量和活动观测；这不意味着每个观测都应产生故障通知。[NVIDIA SMI monitoring](https://docs.nvidia.com/deploy/nvidia-smi/index.html)

### Cited Findings

- NVIDIA SMI的dmon/daemon/replay按p（功率/温度）、u（利用率）、c（时钟）、v（限制状态）、m（FB/BAR1显存使用）、e（ECC/PCIe replay错误）、t（PCIe吞吐）选择指标，支持将资源/性能/环境/错误分开组织。[NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/index.html)
- DCGM Profiling面向设备活动、SM/Tensor活动、DRAM活动和PCIe/NVLink流量；是采样间隔上的平均值，不是核函数跟踪，也不能定位源码行。[DCGM Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)
- NVIDIA Fleet Intelligence将变化较少的机器元数据与周期性时序分开，并同时收集GPU显存、利用率、功率、时钟、错误及互连信息；这可作为资产/配置与运行时指标分离的依据。[Data Collection Rationale](https://docs.nvidia.com/fleet-intel/data-collection-rationale/)
- Exporter collector配置包含某字段，不保证现场一定有该序列；GPU/DCGM/驱动/权限/部署均影响可用性。配置的Prometheus TYPE是按配置采用，不自动校验字段真实语义。[DCGM Exporter Metrics](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)

### Inferences

- 建议主分类：①资源容量与使用；②计算活动与性能观测；③显存活动/带宽压力；④温度与散热；⑤功率/能耗/时钟限制；⑥互联与Fabric（再分PCIe、NVLink、NVSwitch/Fabric）；⑦健康/错误与维护状态；⑧资产、配置与可用性；⑨采集质量及监控平台可靠性。可将②③合并为一个“计算/内存活动与性能”大类以控制目录长度。
- “XID主要事件入口、独立指标状态检测、仅诊断、运行提示、缺口”应为角色字段，不能作为所有指标唯一分类。NVLink CRC属于互联子系统，同时具备健康/错误角色；MEM_COPY_UTIL属于显存活动，不能归为显存容量占用。
- 这是一份结合官方监控对象设计的项目分类，不应称为NVIDIA/业界统一强制分类标准。

### Gaps

- 未发现一个被所有GPU监控产品共同采用的唯一类别标准。当前任务可选用上述可解释体系，不必等“行业标准表”。

## 资源使用和性能观测应补充哪些指标？

### Takeaway

优先补齐资源占用、设备活动、基础功率/频率，再按硬件能力选用Profiling和NVLink吞吐。这些应明确标为“建议补充、当前OS SRE运行时未纳入契约/无独立告警”，不能因为官方CSV有字段，就写成项目已经支持。[固定版本Exporter CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)

### Cited Findings

本表以项目既有固定DCGM头文件`9fae2867e6e5264fa0fca22a07dc898d591baa21`和Exporter CSV`fafd151148052628061a80450b4ee037a5fa0c3c`为命名/单位依据；本地缓存`/tmp/h100-dcgm-fields.h`与该台账同名宏核对。代码定义来源：[固定DCGM字段头文件](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)，采集类型/单位来源：[固定Exporter CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)。

| 优先级/类别 | 建议字段（旧版采集名） | 单位与语义 | 告警建议与来源 |
|---|---|---|---|
| 必补/计算活动 | `DCGM_FI_DEV_GPU_UTIL`（203） | gauge，0–100%；采样期有一个或多个kernel执行的时间比例，不是理论算力利用率 | 默认展示；无作业/服务预期时，不能以低利用率判GPU故障。[CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[NVML利用率定义](https://docs.nvidia.com/deploy/nvml-api/620/api/structnvmlUtilization__t.html) |
| 必补/显存活动 | `DCGM_FI_DEV_MEM_COPY_UTIL`（204） | gauge，%；设备显存被读/写的时间占比，不是已分配显存百分比，也不应简单描述为专门copy engine占比 | 默认展示；高/低都可能符合工作负载。[CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[NVML](https://docs.nvidia.com/deploy/nvml-api/620/api/structnvmlUtilization__t.html) |
| 必补/资源容量 | `DCGM_FI_DEV_FB_TOTAL`（250）、`FB_FREE`（251）、`FB_USED`（252）、`FB_RESERVED`（253，均加`DCGM_FI_DEV_`前缀） | gauge，MiB；物理总容量、可用、已使用、驱动等预留。FB_TOTAL在固定头文件定义，但不在该固定默认CSV主动行里，应显式选取；它是建议补充的总容量分母字段，不是当前已采集事实 | 默认容量图；高占用不是故障，不证明内存泄漏/OOM。[头文件L893–915](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L893)；[CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv) |
| 必补/频率 | `DCGM_FI_DEV_SM_CLOCK`（100）、`DCGM_FI_DEV_MEM_CLOCK`（101） | gauge，MHz；实际SM与显存时钟 | 与时钟限制原因/功率/温度一起解释，不以低频单独判坏卡。[CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv) |
| 必补/功率 | `DCGM_FI_DEV_POWER_USAGE`（155）、`DCGM_FI_DEV_POWER_MGMT_LIMIT`（160）、可选`DCGM_FI_DEV_ENFORCED_POWER_LIMIT`（164） | gauge，W；设备功率、配置功率上限、驱动实际生效上限；155在不同架构可能有不同平均采样行为，不统一称瞬时值 | 默认展示，接近功率上限不必然是故障。[CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[NVIDIA SMI功率说明](https://docs.nvidia.com/deploy/nvidia-smi/index.html) |
| 基础增强/能耗 | `DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION`（156） | counter，mJ；自驱动重新加载以来累计能耗 | 统计能耗/平均功率，正确处理reset；不默认故障告警。[固定头文件L652](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L652) |
| 能力可用时/计算活动 | `DCGM_FI_PROF_GR_ENGINE_ACTIVE`（1001）、`DCGM_FI_PROF_SM_ACTIVE`（1002） | gauge，0–1；图形/计算引擎活动、SM至少有warp的活动周期比例 | 展示设备各层活动。不能直接当业务吞吐或精确FLOPS。[固定CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[DCGM Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html) |
| 能力可用时/计算资源 | `DCGM_FI_PROF_SM_OCCUPANCY`（1003） | gauge，0–1；驻留warp数相对理论最大值的比例 | 分析并行占用，不是GPU数量/显存占用，也不直接证明程序效率。[字段参考](https://docs.nvidia.com/datacenter/dcgm/3.1/dcgm-api/dcgm-api-field-ids.html#c.DCGM_FI_PROF_SM_OCCUPANCY) |
| 能力可用时/计算活动 | `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE`（1004），可选FP64/FP32/FP16活动（1006/1007/1008） | gauge，0–1；特定执行流水线活动周期比例；不同Tensor细分类型按型号/版本核对 | 与负载类型相关，不把Tensor低活动作为所有GPU的故障条件。[Profiling字段定义](https://docs.nvidia.com/datacenter/dcgm/3.1/dcgm-api/dcgm-api-field-ids.html#c.DCGM_FI_PROF_PIPE_TENSOR_ACTIVE) |
| 能力可用时/显存活动 | `DCGM_FI_PROF_DRAM_ACTIVE`（1005） | gauge，0–1；显存接口进行读写的活动周期比例，不是显存容量占比，也不自动等于“达到峰值带宽的比例” | 默认诊断展示，不以单指标直接判定memory-bound。[DCGM Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html) |
| 能力可用时/互联吞吐 | `DCGM_FI_PROF_NVLINK_TX_BYTES`（1011）、`DCGM_FI_PROF_NVLINK_RX_BYTES`（1012） | 按Profiling语义为bytes/s的区间平均速率/gauge；不要因名字含BYTES就再做rate | 判断通信量/方向，不把空闲无流量视作掉链。[DCGM 3.0 Feature Overview](https://docs.nvidia.com/datacenter/dcgm/3.0/user-guide/feature-overview.html) |
| 替代/互联吞吐 | `DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL`（Exporter采集别名；字段449，对应新宏NVLINK_THROUGHPUT_TOTAL） | 固定CSV声明gauge，聚合吞吐MB/s；不是累计字节数，不因为TOTAL后缀就做rate | 与Profiling TX/RX作为不同口径说明，避免并列相加重复统计。[固定CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv) |
| 按需/可靠性维护 | `DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS`、`DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS` | counter，行数；补充现有pending/failure标志的重映射活动数量 | 可用于维护趋势；不能仅累计非零就换卡。固定采集名对应官方ROW_REMAP_UNCORRECTABLE_TOTAL/CORRECTABLE_TOTAL。[固定CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv) |
| 按需/资源引擎 | `DCGM_FI_DEV_ENC_UTIL`、`DCGM_FI_DEV_DEC_UTIL` | gauge，%；视频编码/解码活动 | 视频任务才优先补充，H100通用计算监控不宜把它们列为所有卡必选。[NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/index.html) |

### Inferences

- 最小补充建议分两批：第一批GPU_UTIL、MEM_COPY_UTIL、FB_TOTAL/USED/FREE/RESERVED、SM/MEM_CLOCK、POWER_USAGE与功率上限；第二批Profiling活动、NVLink吞吐、能耗与维护趋势。文档应展示优先级，但不立刻创建健康告警。
- 对显存占用比例，要明确分母。NVIDIA定义的可用显存口径是`Used/(Total-Reserved)`；自行`Used/Total`可以作为“物理容量占比”，但不可混叫同一个使用率。在分母缺失/非正或单位混用时不计算；不能不注明保留量就用`Used/(Used+Free)`等替代。[NVIDIA字段定义](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html#c.DCGM_FI_DEV_FB_USED_RATIO)
- 没有作业/服务信息时，不创建GPU低利用率、Tensor低活动或固定吞吐下限故障告警；它们适合图表、容量分析和后续有条件的检测。资源高占用可以是正常目标状态；若要容量关注告警应单列业务/运维目标与参数，不宣称官方硬件故障规则。
- 当前只修改说明文档，新字段不进入OS SRE runtime `metric_contracts`、采集器或夜莺规则；“已被项目公共指标台账记录”与“当前OS SRE执行链路支持”是不同状态。

### Gaps

- 本次不取得真实GPU现场输出，因此逐型号采集可用性只能标待预检，不能把CSV主动行等价于现场可用。具体profiling并发组、MIG支持与版本需按目标GPU查询。[运行时Profiling能力查询](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)
- 本次未找到可直接当作标准Prometheus默认字段的通用“当前GPU计算进程数”名称。NVML/DCGM结构可以提供进程数据，但不能编造`DCGM_FI_DEV_COMPUTE_PROCESS_COUNT`字段；默认清单先不加进程数。[DCGM进程统计结构](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-structs.html)
- 上层作业吞吐、训练step时延、tokens/s、排队和任务占用不能从上述DCGM活动指标可靠替代，当前OS SRE可观测性不应虚构这些数据。[DCGM Profiling的粒度边界](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)

## 命名、类型、单位和“最佳实践”有哪些适用边界？

### Takeaway

采用项目现有固定来源快照中的命名和单位，最新版本作为兼容性备注；本次不做迁移工作。官方监控类目支撑本项目分类设计，但不自动认证本项目阈值、恢复语义和处置策略。[固定Exporter CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)；[最新Collector](https://github.com/NVIDIA/dcgm-exporter/blob/main/etc/default-counters.csv)

### Cited Findings

- 最新main collector已出现更明确单位名，例如GPU_UTIL_RATIO、FB_*_BYTES、SM_CLOCK_HERTZ、GPU_ENERGY_JOULES_TOTAL；项目固定版本仍使用%、MiB、MHz、mJ的旧采集名。不能只改名称而不转换单位。[最新Collector](https://github.com/NVIDIA/dcgm-exporter/blob/main/etc/default-counters.csv)；[固定Collector](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- 最新文档的别名表与最新main可能不同步，且CSV TYPE由配置直接采用。比如旧版文档曾将部分`NVLINK_BANDWIDTH_*`列为counter，而项目固定CSV明确其TOTAL为MB/s gauge。文档应以本项目固定版本+实际HELP/TYPE和官方字段语义核对，不仅依名字判断。[Exporter Metrics](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)；[固定CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- NVLink5新增累计字节字段`DCGM_FI_DEV_NVLINK_TX_BYTES_TOTAL/RX_BYTES_TOTAL`，不支持NVLink4及更早版本；不能直接当H100默认字段。[最新字段参考](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html#c.DCGM_FI_DEV_NVLINK_TX_BYTES_TOTAL)

### Inferences

- 主表每个新增字段应带“建议补充/未接入当前契约/无独立规则”的状态。现有37个DCGM字段/46项规则的口径保持，新增文档字段不应让用户以为夜莺已多出规则。
- 本次只能称“参考官方及公开实践设计的项目分类”；不要声称“全行业统一标准”或“列了某指标所以最佳实践要求立刻告警”。
- 健康状态、活动强度、容量占用、物理吞吐、业务效率是不同概念；分类和表中含义应把它们明确拆开。

### Gaps

- 当前无法仅凭已定义字段保证不同驱动/型号的完整类型、单位和支持集合；后续接入新增指标仍需契约预检。本文只研究说明文档，不更改生产阈值或通知策略。
