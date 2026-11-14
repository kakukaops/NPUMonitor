# 云厂商GPU监控实践与分类依据

## 公开方案怎样分类，项目可借鉴哪些监控域？

### Takeaway

公开方案不只围绕错误码：同时覆盖资源使用、显存容量、计算活动、温度/功耗、时钟和I/O。分类是产品面向使用场景的组织方式，未发现可据此宣称“整个业界唯一标准分类”的依据；建议项目按监控对象分章节，同时用独立标签表达检测角色和当前支持状态。

### Cited Findings

- Google GKE的DCGM监控文档直接给出Compute/Core Utilization、Memory Utilization、I/O Utilization、Power Utilization、GPU Performance分组；这可作为资源、计算、显存、互联和运行条件分域的官方例子。 — [GKE DCGM指标指南](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/dcgm-metrics)
- AWS CloudWatch NVIDIA GPU方案的仪表盘分别展示Utilization、Memory、Temperature/Power、Encoder、PCIe、Clock；文档明确用显存总量/已用/空闲观察容量、用代际/宽度检查PCIe能力、用时钟观察降频。Encoder是视频场景特有分组，不能因参考云厂商仪表盘就要求H100训练OS SRE首发实现。 — [AWS GPU监控方案](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Solution-NVIDIA-GPU-On-EC2.html)
- AWS EKS节点监测同时接收XID和执行周期DCGM健康检查；同一次故障可由两类信号报告，例如XID79后出现DCGM健康检查的fallen-off-bus结果。 — [EKS节点健康监测](https://docs.aws.amazon.com/eks/latest/userguide/node-health-nma.html)
- Google Ops Agent把性能/状态采集与profiling视为不同指标集，且profiler支持存在型号限制。这说明指标存在于文档不等于每张GPU、每种采集配置都可采。 — [Google Ops Agent DCGM集成](https://docs.cloud.google.com/monitoring/agent/ops-agent/third-party-nvidia)

### Inferences

- 推荐项目主分类（具体可由统稿者合并/拆分）：①资产身份/配置与能力；②资源容量与使用；③计算和显存活动/性能表征；④温度、功耗与时钟；⑤设备健康/错误与维护；⑥互联拓扑、链路状态与吞吐；⑦采集数据质量；⑧监控平台可靠性。它是基于上述公开实践的项目设计，不是照搬某一家或声称统一标准。
- XID不是与“互联/显存”互斥的物理域，可能表达不同子系统的事件。可将其集中放在设备健康/错误域，并在规则角色中标“错误事件”；互联ECC等状态规则仍按本身所属域放置，附交叉说明。检测角色（XID/SXID、独立状态、运行提示、仅诊断）与支持状态（已实现/建议补充/按硬件可选）均不替代主分类。
- 当前37个DCGM字段主要用于故障/状态检测；缺少资源和profiling字段不能以“有XID监控”解释为已经完整监控GPU。这来自本地当前catalog逐字段比较：[当前指标契约](../../monitoring/os-sre/catalog.json)（此链接需统稿时按目标文档位置调整）。

### Gaps

- 没有证据证明统一的一组指标或阈值适合所有GPU型号、互联形态及工作负载，不能写“业界最佳实践统一要求SM_ACTIVE>0.8”等固定目标。
- 资产身份与监控平台可靠性是本项目OS SRE可运维性所需的补充分组，上述云仪表盘分组并没有逐一按这两个名称列出；应明确为本项目设计。

## 当前缺哪些指标，资源使用与性能应如何区分？

### Takeaway

资源使用至少应补GPU活跃比例、显存总量/已用/空闲；计算活动与显存访问活动另列，不能把GPU_UTIL或显存占用率当作算力效率。新增指标先列为采集/展示和诊断建议，不自动变成硬件故障告警。

### Cited Findings

- AWS把GPU utilization定义为采样期内至少一个kernel在运行的时间比例，把memory utilization定义为设备内存被读写的时间比例；memory_total/used/free是容量量，另有温度、功率、PCIe代际宽度、各类时钟。这些是不同维度，不可把memory utilization当显存容量占用。 — [CloudWatch NVIDIA GPU指标定义](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-NVIDIA-GPU.html)
- AWS EKS实践明确：GPU利用率100%不等于所有SM或算术管线充分使用，需结合SM活动/occupancy、tensor等更细粒度信号；还把平台指标与模型/应用指标分层。 — [EKS GPU可观测性实践](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-observability.html)
- GKE列出原始DCGM字段GPU_UTIL、FB_USED/FREE/TOTAL、MEM_COPY_UTIL、SM_ACTIVE、GR_ENGINE_ACTIVE、PIPE_FP16/FP32/FP64/TENSOR_ACTIVE、DRAM_ACTIVE、POWER_USAGE、SM_CLOCK、TOTAL_ENERGY_CONSUMPTION、PROF_NVLINK_TX/RX_BYTES等。该页把FB容量字段写为MB、GPU_UTIL为%、SM活动等为比例、功率为W、SM时钟为MHz、累计能量为mJ；项目原始单位仍应以固定NVIDIA版本和实际Exporter契约为准。 — [GKE字段和用法](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/dcgm-metrics)
- GKE的推理扩缩容实践明确，GPU_UTIL度量duty cycle而不是活跃时做了多少工作；显存已用量对于预分配显存的服务也不能直接跟随请求量下降。因此不能仅由这两个指标判定业务负载、推理吞吐或扩缩容需求。 — [GKE推理扩缩容指标限制](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference/autoscaling)

### Inferences

建议补充清单（所有“当前缺失”均已与当前catalog逐字段对照；具体NVIDIA单位/型号由另一研究员核验）：

| 监控域 | 建议字段/视图 | 当前缺口和用途 | 告警边界 |
|---|---|---|---|
| 资源容量/使用 | DCGM_FI_DEV_GPU_UTIL | 当前缺失；GPU忙碌时间比例总览 | 高值可能正常；无作业预期时低值不能定为GPU故障 |
| 资源容量/使用 | DCGM_FI_DEV_FB_TOTAL / FB_USED / FB_FREE | 当前均缺失；显存容量、占用与剩余 | 容量占用不是带宽；高占用不直接证明泄漏、故障或已发生OOM |
| 资源容量派生视图 | FB_USED / FB_TOTAL * 100 | 依赖前三字段；容量占用百分比 | 分母为0/无效/单位不一致时不能算；不要偷设通用故障阈值 |
| 计算活动/性能表征 | DCGM_FI_PROF_GR_ENGINE_ACTIVE / SM_ACTIVE / SM_OCCUPANCY / PIPE_TENSOR_ACTIVE；按需FPxx | 当前均缺失；判断硬件活动分布/并行使用，需支持profiling | 不是业务吞吐、SLA或理论FLOPS利用率；本期只建议展示/诊断 |
| 显存访问活动 | DCGM_FI_DEV_MEM_COPY_UTIL / DCGM_FI_PROF_DRAM_ACTIVE | 当前缺失；内存访问/接口活跃程度 | 不等于显存已用比例，也不等于已测得的实际GB/s |
| 功耗/能量与时钟 | DCGM_FI_DEV_POWER_USAGE / TOTAL_ENERGY_CONSUMPTION / SM_CLOCK / MEM_CLOCK | 当前缺失；功耗、累计能量及运行频率，补充已有热限制/原因位 | 空闲低功耗/低时钟可正常；功率接近上限不自动是故障 |
| 互联吞吐 | DCGM_FI_PROF_NVLINK_TX_BYTES / RX_BYTES | 当前缺失；现有PCIe吞吐字段已经有，NVLink只有错误和状态 | 名称含BYTES不代表累计量；采集类型/单位必须核对，不将低流量当链路故障 |

### Gaps

- 云厂商文档存在转换后的指标和原始字段混用。例如Ops Agent导出的NVLink/PCIe io是CUMULATIVE，GKE原始PROF字段为GAUGE；不能把一个集成的rate用法复制给另一个。 — [Ops Agent类型表](https://docs.cloud.google.com/monitoring/agent/ops-agent/third-party-nvidia)；[GKE原始字段类型表](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/dcgm-metrics)
- 当前没有上层作业、队列、请求延迟、tokens/s等数据，不能承诺通过DCGM资源指标直接检测作业卡死、显存泄漏、业务性能异常或真实闲置浪费。建议仅提供OS可见证据与诊断线索，不构造这些告警。
- 本轮是文档分类和覆盖审查，不代表新增字段已经加入Exporter/Prometheus、运行契约或生产规则。
