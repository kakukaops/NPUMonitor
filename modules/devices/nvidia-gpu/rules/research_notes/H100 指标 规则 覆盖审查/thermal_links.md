# H100温度功耗互联与性能覆盖审查

## 温度、功耗和时钟应覆盖什么

### Takeaway

当前正式目录只有ECC样例，本范围内尚无正式指标卡或规则卡；温度实验阈值85°C不能作为H100依据。本版需至少区分温度接近设备门槛、实际热降频、电源限制/外部power brake以及单纯负载变化。

### Cited Findings

- 本地现状：monitoring/coverage.md只登记ECC；rules/lab-catalog.json的温度规则自述85°C仅为模拟值，没有功耗、时钟、PCIe或NVLink规则。此项是仓库直接审查结果，不是官方支持结论。证据文件：[覆盖矩阵](../../monitoring/coverage.md)、[实验规则](../../rules/lab-catalog.json)。
- NVIDIA区分GPU温度、slowdown、max operating、shutdown、memory温度等语义；特定读数并非所有设备都支持。温度门槛应读设备能力，不能从营销规格或通用示例发明统一H100数值。[nvidia-smi温度定义](https://docs.nvidia.com/deploy/nvidia-smi/index.html#temperature)（rolling，核对2026-11-06）。
- 固定源码提供候选字段：GPU/Memory温度150/140、最大运行温度152/151、温度余量153、slowdown158、shutdown159；旧常用名包括DCGM_FI_DEV_GPU_TEMP、MEMORY_TEMP、GPU_MAX_OP_TEMP、MEM_MAX_OP_TEMP、GPU_TEMP_LIMIT、SLOWDOWN_TEMP，部分已是新字段名的兼容别名。[DCGM固定字段源码](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)
- 同一固定源码将clock reasons 112定义为位掩码；温度/功耗限制累计时长240/241的旧单位是ns。常用名为DCGM_FI_DEV_CLOCKS_EVENT_REASONS、POWER_VIOLATION、THERMAL_VIOLATION；旧CLOCK_THROTTLE_REASONS是兼容别名。此类标志不是次数，旧ns字段也不能直接按秒计算。[DCGM固定字段源码](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)
- 功耗候选：POWER_USAGE 155、POWER_USAGE_INSTANT 157、POWER_MGMT_LIMIT 160、ENFORCED_POWER_LIMIT 164；SM_CLOCK 100、MEM_CLOCK 101辅助解释频率变化。现有固定Exporter CSV启用温度、功耗和时钟读数，但power/thermal violation和功率限制行被注释，不意味着现场一定已采集。[固定Exporter配置](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- NVIDIA把SW power cap、HW thermal slowdown、external power brake、sync boost和SW thermal slowdown区分开；高功耗和主动功率限制本身不等于GPU硬件坏了。[nvidia-smi clock event reasons](https://docs.nvidia.com/deploy/nvidia-smi/index.html#clock-event-reasons)
- H100规格里SXM与NVL的功率、互联等配置不同；TDP是规格值，不是告警阈值。[H100官方产品规格](https://www.nvidia.com/en-us/data-center/h100/)（rolling）；固定R550支持列表同时列出H100 PCIe/NVL以及不同HGX拓扑，但仅证明产品/平台身份，不证明上述字段逐项可用。[R550支持列表](https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-550-90-07/index.html)

### Inferences

- 建议拆成至少六个检测目标：GPU热余量不足、显存热余量不足、持续热降频、持续功率限制/异常限制配置、外部power-brake或可靠性降频、负载下异常低频。前五者要字段和上下文匹配；最后一项需负载、配置频率和业务背景，不能单凭低频默认报硬件故障。
- 设备提供门槛时优先用余量/门槛比较；门槛缺失则标覆盖缺口，不回退到未经核实的85/90°C。duration、窗口和严重度即使合理也属于工程参数，需样本验证和现场审定。
- 当前可见GPU温度不能证明显存温度和热降频均受监控；同类每个检测目标都需独立覆盖项。

### Gaps

- 未取得现场H100形态、驱动/DCGM/Exporter版本、真实指标及温度门槛。所有列出的字段是候选，不是该H100配置的已验证支持列表。
- 只读Prometheus中没有的温度门槛、位掩码或duration字段，无法靠编写规则补出来。BMC风扇/进风温度/PSU根因也不能由GPU指标单独确认。
- 温度/功率字段在新源码中的命名和量纲演进，必须与实际安装版本和CSV匹配，不直接迁移最新名字替换已有指标。

## H100互联应覆盖什么，哪些代际字段不能混用

### Takeaway

Hopper专用的NVLink错误字段与pre-Hopper和Blackwell+字段必须区分。NVSwitch是独立监控实体；有GPU指标不等于有交换芯片、端口、预期拓扑或Fabric Manager状态覆盖。

### Cited Findings

- 固定Exporter CSV明确把NVLink字段分组：Hopper使用DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL、NVLINK_RECOVERY_TOTAL、NVLINK_REPLAY_TOTAL；固定字段ID分别497/498/499。这些行均被注释。pre-Hopper CRC flit/data及旧replay/recovery组和Blackwell+ recovery组分别列出，不宜复制其他代际规则。[固定Exporter配置](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- H100 SXM和NVL的互联规格不同；NVL是带NVLink bridge的PCIe方案。固定R550列表中HGX H100 8-GPU为NVSwitch，而4-GPU列为NVLink。因此不能按“H100型号”直接假定每台机器都有相同数量端口或交换机。[H100规格](https://www.nvidia.com/en-us/data-center/h100/)、[固定驱动支持列表](https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-550-90-07/index.html)
- 官方拓扑文档把端口up/down/disabled/unsupported区分；无支持端口不是链路故障，disabled也可能是配置。拓扑描述不等于带宽实测。最新1200–1219及1404–1419的NVLink计数族要求NVLink5+，不能为了覆盖H100直接纳入这些字段。[Topology and NVLink](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/topology-and-links.html)（rolling；页面明确讨论DCGM4.6新字段）。
- 可选字段：PCIe replay 202、max/current link generation235/237和width236/238；GPU NVLink link状态1508需link实体；Fabric Manager状态/错误170/171、fabric health mask/summary174/175是不同语义。summary中0为not supported，不能统一“非健康数值”解释。字段存在不构成H100支持保证。[固定字段源码](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)
- NVSwitch要单独发现switch/link实体；GPU端点和switch端点不是同一对象。缺失实体、N/A及不支持不能当作零错误；DCGM观察fabric，并不负责配置或修复Fabric Manager。[NVSwitch and ConnectX](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/nvswitch.html)（rolling，核对2026-11-06）。
- NVSwitch候选：fatal/nonfatal856/857、温度/slowdown858/859、端口状态870、端口fatal/nonfatal782/783及replay/recovery784/785。特别注意旧名NVSWITCH_FATAL_ERRORS/NON_FATAL_ERRORS对应856/857实际值是具体SXid码，不是累计次数；必须逐字段核对，不能把名字中的ERRORS直接当counter。[固定字段源码](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)
- PCIe主动诊断插件能测试P2P正确性、带宽和延迟；其replay阈值80与短时插件、PCIe Gen3假设绑定，不是H100生产连续监控的通用阈值。[官方PCIe诊断插件说明](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/diag-pcie-plugin.html)

### Inferences

- 建议检测目标：Hopper NVLink CRC/replay/recovery新增；预期GPU端口掉链；GPU或fabric未就绪；NVSwitch fatal/nonfatal/SXid；交换机过热；预期switch端口掉链/错误；PCIe replay新增及负载下链路速率/宽度降级。各自有独立设备/端口身份与数据要求。
- 链路吞吐低只说明流量低，不能默认判链路故障。link-state需要“哪些端口预期启用”的基线；单纯对所有端口state!=up告警必然误报未使用端口。
- Switch/Fabric Manager、主机AER/驱动日志或实际带宽诊断若没有进入Prometheus，应标“输入缺失/需其他诊断”；不能把这些目标从覆盖分母中悄悄删掉。

### Gaps

- 未确认现场有没有NVSwitch、NVLink bridge或隔离/虚拟化限制，无法确定switch监控在该部署是必需还是有据不适用。
- 最新拓扑文档给出的Hopper旧per-link展示与新Exporter CSV按代际分组，不应理解为字段全互换；需要现场dcgmi目录、具体SDK/Exporter适配和样本才能完成精确映射。
- 当前GPU-only Exporter是否导出switch/link实体、FM健康信息及对应稳定标签未知。只能用已有Prometheus的约束可能使若干目标成为明确的采集缺口。

## 性能容量指标与完整性验收如何划界

### Takeaway

资源利用率、占用率、流量是容量/效率证据，不能默认升级为硬件故障。覆盖审查应建立“故障目标→所需字段→实际采集→规则→测试”的可追溯链，而不是给原始字段数量一个看似全面的百分比。

### Cited Findings

- 固定Exporter配置中GPU_UTIL203/MEM_COPY_UTIL204是百分数；FB_FREE251/FB_USED252是MiB；profiling的GR_ENGINE_ACTIVE1001、SM_ACTIVE1002、SM_OCCUPANCY1003、PIPE_TENSOR_ACTIVE1004、DRAM_ACTIVE1005是比率。PROF_PCIE_TX_BYTES1009/RX1010虽然名字含BYTES，在该CSV为gauge、值是B/s，不能再套rate；新*_BYTES_TOTAL是不同累计字段。[固定Exporter配置](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- Profiling数据是区间平均，不定位CUDA源码或kernel；即使SM activity高也不等价有效计算，occupancy更高也不一定更有效。应在目标GPU运行时发现支持的profiling目录，不能从其他代际推断。[Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)（rolling）。
- 同一官方profiling模块要求与Nsight等工具协调资源；暂停期间返回blank，不能解释为空闲。[Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)
- 较早的Feature Overview还描述了硬件不兼容指标组的multiplexing和高频采集零值，例子明确是T4/V100而非H100。可作为采集风险清单，但不能声称H100一定使用相同分组/复用机制。[Feature Overview](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html#multiplexing-of-profiling-counters)
- 同一NVLink profiling字节字段的负载/协议头口径在新固定header描述与rollingprofiling文档存在差异：header说包括header/payload，guide说不含protocol headers。因此精确利用率分母和单位要按目标安装版本实现/实测核对，不在本审查中擅自选择其一。[固定header](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)、[Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)

### Inferences

- 可选业务策略候选：已分配但持续空闲、显存压力、算力/显存带宽长期不均衡、同作业副本偏斜、通信流量异常。必须加作业分配/运行状态、吞吐或副本信息才能解释；DCGM alone不具备“有任务本应忙”的完整上下文。
- “监控全面”的可验收定义应是：对选定H100配置及明确范围内的全部检测目标，每一行都有已实现、输入缺失、待核实、有证据不适用或明确不在范围的结论。已实现的行必须同时有字段/单位/版本证据、实际序列、表达式和正负测试。原始字段的alias不能当多个独立覆盖项。
- 三个分母分别计算：①文档目标处置率（所有目标有明确处置）；②可检测目标实现率（具备输入且在范围的目标已实现规则）；③已实现规则验证率（表达式/夜莺/现场分别）。当前只有ECC草案且缺现场清单，不应给H100一个“百分之多少全面”的数值。
- 推荐优先补硬件健康与监控质量，容量效率为可选策略；每个健康规则必须有对应字段缺失/陈旧/无效的可见性，否则“无告警”可能只是无输入。

### Gaps

- 未知实际工作负载、调度器和profiling权限，不能设统一空闲、显存或利用率阈值。
- 主机/机箱的风扇、进风温度、PSU供电、OS PCIe AER、通信库错误和主动诊断结果如未被采集，现有GPU指标无法单独保证其可见性或根因判断。
- 本笔记提供的是覆盖审查候选和证据，不创建新规则卡，不更改现有夜莺/Prometheus环境，不声称H100硬件验收通过。
