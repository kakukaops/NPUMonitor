# A3 NPU指标初版

状态：research_draft。**当前分类与采集路径统一入口为[0.2版指标与规则说明表](../rules/docs/01-A3-NPU监控指标与告警规则说明表.md)**（2026-11-17），明确区分Exporter已有、DCMI补采/待核对及外部/派生。下文及catalog/metrics.yaml保留2026-11-16的26项研究子集；不能当作Exporter全集，也不能用旧unknown覆盖新引用的官方定义。尚未接入硬件。

## 阅读入口

- [选型与版本基线](catalog/baseline.yaml)
- [指标结构化台账](catalog/metrics.yaml)
- [指标速览](metric-inventory.md)
- [来源与证据状态](catalog/sources.yaml)
- [候选规则](../rules/README.md)

## 版本选择

按用户选择保留A3、驱动26.1.x最新补丁、CANN 9.20（暂按9.2.0理解）。官方NPU Exporter发布说明目前标注26.2.0，初版记录该具体版本，不使用浮动latest作为部署标识。

[MindCluster中文版本说明](https://github.com/Ascend/mind-cluster/blob/master/docs/zh/release_notes.md)的26.2.0兼容表，分别对CANN 9.2.X、HDK 26.1.X标Y；推荐套件为CANN 9.2.0、HDK 26.2.0。故用户组合有组件矩阵依据，但仍需CANN自身与A3硬件的驱动/固件配套证据及实机验证。不能仅凭推荐套件不同就判为不兼容，也不能从两个Y宣称完整组合通过。

未取得A3驱动26.1.x补丁完整列表，resolved_patch暂空；不能把网上出现的26.1.1直接称为最新。固件版本也必须一同记录。尚未固定Exporter镜像digest和源码commit；当前master资料用于研究，不冒充26.2.0不可变快照。

## 已确认的语义差异

[基础采集器](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_npu.go)会将DCMI结果转换成健康/不健康，再通过[常量](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/common/constants.go)输出1/0。因此不能把DCMI原始0/1/2/3健康等级直接用于Exporter规则。查询失败、未上报和不支持的实际输出还需固定发行版验证。

HBM容量、HBM利用率和HBM带宽利用率分别登记；容量比例仅在容量单位一致、总量大于0且已用量不超过总量时计算。源码明确支持A3的HBM采集器，不代表每个固件都支持所有子字段。[HBM源码](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_hbm.go)

ECC名称带cnt不证明Prometheus类型是counter，也不证明重启清零或终身累计。先核对接口和实际# TYPE，再决定差分与重置处理。历史错误不能以必须回零作为恢复条件。

## 身份、缺数和时间契约

物理芯片候选键为instance+vdie_id，但须验证非空、唯一及重启稳定性；instance地址变化还需独立资产映射。id、card_id、chip_id和logic_id分开保留，不相互替代。A3具体整机/板卡形态尚未选择，不能假定一板一卡或固定8芯片。

pod/namespace/container属于归属信息，不能作为硬件身份。物理芯片因容器归属出现重复序列时，先验证值及时间戳一致再折叠；冲突交给输入质量告警，不用max掩盖。

每个字段区分available、missing、invalid、stale、query_failed、unsupported。缺数不补零；无效或陈旧数据不触发健康判断，也不能作为恢复证据。是否不支持由型号/版本能力清单决定，不能由缺失反推。

采集周期、抓取周期、样本显式时间戳和缓存更新时间分别记录。up=1仅说明抓取成功；Exporter可能仍输出缓存。未知TTL不设置通用固定值；须取得配置与连续样本后制定各组TTL。

## 早期第二批清单（分类主表已部分展开，字段核验仍待完成）

| 分组 | 当前证据与限制 | 下一步 |
| --- | --- | --- |
| AI Core/Vector/AI CPU利用率 | Exporter有独立utilization分组；固定发行版字段未逐项核实 | 取得26.2.0源码与样本后补字段和采样语义 |
| HCCS | 源码支持A3，链路起始下标按整机类型变化 | 固定机型，核对前缀、端口、CRC、吞吐单位及重置 |
| SIO | 指标文档标注A3范围 | 逐字段验证CRC及链路映射 |
| RoCE、网口、光模块 | 采集配置区分网络分组，依赖hccn_tool | 确认预期使用的网口与光模块后建能力矩阵 |
| PCIe | 不能把文档中其他芯片的PCIe分组直接认定A3支持 | 核实A3 HDK接口与Exporter实际输出 |
| vNPU与逻辑分区 | 首版限定物理设备 | 分区能力、身份及资源归属另行验证 |

依据：[接口目录](https://github.com/Ascend/mind-cluster/blob/master/docs/zh/scheduling/06_api/00_npu_exporter/01_prometheus_metrics_api.md)、[采集配置](https://github.com/Ascend/mind-cluster/blob/master/docs/zh/scheduling/05_developer_guide/00_installation_deployment/00_manual_installation/03_npu_exporter.md)、[HCCS实现](https://github.com/Ascend/mind-cluster/blob/master/component/npu-exporter/collector/metrics/collector_for_hccs.go)。未知单位留unknown，不依据指标名称猜测。

## 实机验收输入

1. 整机型号、芯片/板卡拓扑、CPU架构、OS，驱动26.1.x精确补丁及配套固件。
2. CANN安装包精确版本与A3配套说明；确认9.20确指9.2.0。
3. Exporter版本、镜像digest、发行源码commit、采集开关和各分组周期。
4. 至少连续3轮原始/metrics（保留HELP、TYPE、标签和显式时间戳），以及同时间的只读npu-smi健康、设备映射和ECC结果。
5. 独立预期芯片/链路清单；空闲/运行场景样本；重启、迁移、维护后的身份及计数语义证据。

本阶段不执行复位、链路断开或压测，不把GPU实验结果作为NPU证据。各来源的不可变版本与字段单位补齐后，才能形成可执行规则、promtool用例和夜莺接入。
