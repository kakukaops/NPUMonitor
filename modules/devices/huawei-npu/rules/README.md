# A3 NPU候选规则初版

**分类指标、来源分层和新增规则语义见[0.2版主表](docs/01-A3-NPU监控指标与告警规则说明表.md)**。以下12项YAML设计是旧研究子集，不代表主表每行已有规则实现。

[candidates.yaml](candidates.yaml)包含12项候选设计，全部enabled=false、deployable=false。这是规则语义契约，不是可直接加载的Prometheus规则文件。表达式仅供审阅，尚未包含身份、有效性、缺失和新鲜度准入，不能直接复制上线。

| 候选 | 检测意图 | 当前关键缺口 |
| --- | --- | --- |
| exporter_down | HTTP抓取失败 | 固定job与独立target清单；up消失需额外覆盖 |
| health_unhealthy | 有效健康值精确为0 | 健康编码发行版验证与故障码分级 |
| health_unknown | 节点存在健康未知芯片 | 节点缓存及时间语义 |
| expected_device_missing | 预期物理芯片缺失 | 独立资产清单；不能使用当前枚举作为预期值 |
| input_missing_or_stale | 必需字段缺失或陈旧 | 组采集周期、TTL、能力矩阵 |
| input_invalid_or_duplicate | 非法输入、重复冲突 | 稳定物理键与输入质量层 |
| network_unhealthy | 预期网络健康异常 | 使能场景及未知值语义 |
| thermal | 芯片/HBM过温 | 官方机型温限、恢复迟滞与持续时间 |
| hbm_capacity_pressure | HBM容量压力 | 单位、容量比例及现场容量预警线 |
| hbm_uncorrectable_review | 多比特错误新增复核 | 实时/历史语义、重置、故障码关联 |
| hbm_correctable_trend | 单比特错误增长异常 | 有效差分窗口和增长基线 |
| fault_code_policy | 错误码分类与升级 | 全槽位、截断、机型/HDK字典 |

温度、容量和ECC增长阈值没有足够证据，明确留空；1分钟/2分钟是项目建议，尚未验证，不声称为华为推荐值。HBM容量压力属于容量提示，不自动判定硬件损坏或业务失败。

## 处置与恢复

告警展示应包含物理身份、原始值、样本时间、版本、故障码与官方证据链接。按数据质量、设备健康、容量压力分开报告，严重级别不能直接抄调度策略。维护状态由独立上下文提供；首版不假定已有该输入。

故障码按[官方查询工具](https://info.support.huawei.com/computing/tools/om-info-query)匹配产品/HDK；[Device Plugin接口](https://github.com/Ascend/mind-cluster/blob/master/docs/zh/scheduling/06_api/02_ascend_device_plugin.md)的频率/持续时间升级机制只作设计参考。多错误码应按集合关联，槽位移动不应计为新增故障。

原始触发条件消失不等于恢复：序列缺失、陈旧、查询失败、Exporter重启均不能作恢复证据。历史ECC不要求回零；需活动故障清除、采集恢复及对应官方复核依据。自动隔离、复位、重启、断链不属于初版范围。

## 验证状态与下一步

仅完成研究台账结构、输入引用及模块布局检查；PromQL求值、告警时间边界、夜莺集成和A3实机验证尚未执行。进入可执行规则阶段需覆盖：正常/异常/恢复、缺数、陈旧、sentinel、重复冲突、身份变化、计数重置、维护和预期资产丢失。
