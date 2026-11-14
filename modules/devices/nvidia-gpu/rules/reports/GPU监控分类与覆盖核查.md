# GPU监控分类与覆盖核查

当前OS SRE清单确实遗漏资源使用和性能活动：**37个DCGM字段主要覆盖健康错误、温控限制及互联，没有GPU繁忙度、显存容量占用、SM/Tensor活动、实际功率和频率的独立观测**。公共候选台账和ML模块已涉及部分字段，但不等于当前OS规则链路已接入。参考NVIDIA、Google GKE及AWS公开实践，本项目采用8个监控对象域，同时保留检测角色和支持状态标记。第14篇已按此重排，保留原57行和46项规则，补充26行建议，涉及22个新DCGM字段、1项派生容量视图和3项资产视图。新增内容是文档覆盖计划，不改变采集、运行契约、在线告警或通知。

## 资源与性能不能被错误码清单替代

NVIDIA SMI将利用率、显存容量、功率/温度、时钟、错误和PCIe流量分别展示；GKE的DCGM指南覆盖计算、显存、I/O、功耗及性能；AWS GPU监控方案也分别组织利用率、Memory、Temperature/Power、PCIe和Clock。公开实践支持同时观察资源、活动和健康，而不是仅围绕XID组织全部指标。这些产品并未规定一套所有GPU必须采用的唯一分类，本文分类是结合OS SRE职责的项目设计。([NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/index.html)、[GKE DCGM指标](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/dcgm-metrics)、[AWS GPU监控方案](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Solution-NVIDIA-GPU-On-EC2.html))

| 监控领域 | 回答的问题 | 当前规则与覆盖 |
|---|---|---|
| 资产、身份与配置 | 哪张卡、何种型号/版本、具备哪些能力 | 身份标签/静态清单已使用；独立资产概览待补 |
| GPU健康、错误与维护 | 发生什么错误、是否有待维护状态 | 9项规则、8项ECC诊断，13个DCGM字段 |
| 资源容量与占用 | 显存总量、已用、空闲、预留是多少 | 独立容量字段当前缺失 |
| 计算活动与性能信号 | GPU、SM、Tensor有多活跃 | GPU_UTIL和Profiling活动当前缺失 |
| 显存访问与带宽信号 | 显存接口访问有多活跃 | MEM_COPY_UTIL、DRAM_ACTIVE当前缺失 |
| 温度、功耗与时钟 | 热状态、功率和频率约束是什么 | 11项规则、8个字段；实际W/MHz待补 |
| 互联与Fabric | 链路状态、错误、能力与吞吐怎样 | 14项规则、16个字段；NVLink吞吐待补 |
| 监控链路可靠性 | 数据和监控系统是否可信 | 12项规则，另有网关健康与2项Watchdog |

XID/SXID、独立指标检测、运行提示和仅诊断是**检测角色**，不是主分类。NVSwitch SXID按设备对象归互联域，GPU XID集中在健康域；它们仍可指向同一个物理问题，但本期不实现跨规则关联或通知收敛。现有规则、字段与运行状态均以项目台账和实际接入证据为准。([当前catalog](../monitoring/os-sre/catalog.json)、[当前接入证据](../runtime/evidence/current-ui-cleanup.json)、[双通道方案](../docs/16-XID事件与指标状态双通道监控方案.md))

## 优先补基础观测，再按能力补Profiling

第一批应补FB_TOTAL/USED/FREE/RESERVED、GPU_UTIL、MEM_COPY_UTIL、POWER_USAGE及SM/MEM_CLOCK，并对功率上限选择可用字段。第二批按型号、权限和采集能力补SM_ACTIVE、SM_OCCUPANCY、TENSOR、DRAM_ACTIVE、NVLink吞吐、累计能耗与重映射数量趋势。资源指标不是因缺乏通用告警阈值就可以省略；它们首先服务可视化、容量与诊断。新增字段采用项目固定Exporter/DCGM快照的名称和单位；FB_TOTAL虽在字段定义中，不是该默认CSV已主动采集的事实。([固定Exporter配置](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)、[固定DCGM字段](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h))

**显存容量、活动时间和计算效率必须分开解释。** GPU_UTIL表示采样期kernel活跃时间，不证明SM已充分使用；MEM_COPY_UTIL表示显存读写时间，不是显存已分配比例。SM_ACTIVE与SM_OCCUPANCY分别描述活动和驻留warp占比，DRAM_ACTIVE不等价于已经测得的精确HBM GB/s。显存容量占比需注明分母是设备报告的framebuffer总量还是扣除预留后的容量；该报告总量不保证等于板卡标称容量，扣除预留量也不保证某个进程实际可分配全部容量。缺失、非正或无效分母不能替代计算。([NVML利用率定义](https://docs.nvidia.com/deploy/nvml-api/620/api/structnvmlUtilization__t.html)、[DCGM Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)、[AWS GPU可观测性实践](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-observability.html))

## 单位、类型和支持状态决定能否接入

固定快照使用百分比、MiB、MHz、mJ等旧采集口径；上游版本存在规范化名称与单位变化，不能只通过metric_aliases改名就视为完成转换。尤其PCIe/NVLink字段名称含BYTES或TOTAL时，不能仅凭名字选择rate：当前PCIe Profiling和建议NVLink Profiling按bytes/s gauge解释，备选NVLINK_BANDWIDTH_TOTAL按固定CSV的MB/s gauge解释，不重复相加。云集成还可能将原始字段转换为累计指标，不能照搬另一集成的查询。([固定Exporter配置](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)、[Exporter指标参考](https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html)、[Google Ops Agent DCGM指标类型](https://docs.cloud.google.com/monitoring/agent/ops-agent/third-party-nvidia))

当前公共台账有92项候选，ML绑定及场景涉及GPU利用率、显存访问活动、功率和时钟，部分通用绑定还含FB_USED。这些属于不同模块及不同支持阶段，不能升级为OS规则已实现的证据。第14篇因此将新增行明确标为“建议补充、当前OS SRE未接入、无已部署告警”，同时保留原46项规则和通知counter禁用状态。([公共候选台账](../../common/monitoring/catalog/metric-inventory.yaml)、[ML绑定](../../ml/config/bindings.json)、[当前OS指标契约](../monitoring/os-sre/metrics.yaml))

## 新增观测不等于新增故障通知

高GPU利用率和高显存占用可以是正常目标状态，低Tensor活动也可能完全符合负载类型。在没有作业、请求、队列或调度信息时，不能默认判定闲置浪费、显存泄漏、作业卡死或业务性能下降。容量关注告警应在明确剩余容量、预留策略、运行目标与持续时长后另行设计，不套用统一80%/90%门槛。GKE也指出，GPU繁忙度与已用显存不能直接代表请求量或实际推理扩缩容需求。([GKE推理指标限制](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference/autoscaling))

下一步的验收对象应是新增字段的硬件适用性、原始单位/TYPE、有效性契约和图表口径，而不是先增加告警条数。当前文档覆盖检查只能证明分类及清单完整，不能证明新增指标已经可采或真实故障已经验证；完整XID事件流、跨规则关联和通知收敛仍保持原有未完成/暂缓边界。详细分类表见[第14篇](../docs/14-GPU监控指标与告警规则说明表.md)。
