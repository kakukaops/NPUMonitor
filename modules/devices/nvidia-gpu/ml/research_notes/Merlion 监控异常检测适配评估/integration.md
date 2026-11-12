# Merlion与现有GPU监控系统集成适配

## 是否能替代现有系统提供完整生产方案

### Takeaway
Merlion适合作为算法评估参考或隔离的候选推理后端，不能直接替代Prometheus接入、任务控制面、制品注册、在线水位与质量契约、夜莺对接。更重要的是，官方仓库已于2026-03-11归档只读，不建议将其作为新生产平台的唯一主依赖；如采用应明确由本方维护fork及锁定依赖。

### Cited Findings
- 官方GitHub页明确显示“archived … Mar 11, 2026 … read-only”，并将项目定位为Python时序智能库。它提供共享模型接口、AutoML、集成、前后处理和历史模拟评估；这不等于完整监控产品。— [官方仓库](https://github.com/salesforce/Merlion)
- Dashboard是用于训练和测试模型的Dash应用；文档流程以CSV文件上传、选择特征、训练/测试和下载模型为主，模型保存在本地目录。— [官方Dashboard文档](https://opensource.salesforce.com/Merlion/merlion.dashboard.html)
- Spark模块提供多时序并行训练和推理的PySpark API、脚本和spark-on-k8s部署模板。官方介绍是计算能力而非自动获得生产监控控制面的承诺。— [官方Spark文档](https://opensource.salesforce.com/Merlion/latest/merlion.spark.html)
- Evaluator在历史数据上模拟初始训练、周期重训、预测节奏；它是评估器，不等于我们在线服务的任务调度/租约/重试/幂等工作流。— [官方评估文档](https://opensource.salesforce.com/Merlion/latest/merlion.evaluate.html)
- 本地当前架构按“GPU实体＋指标/不可变指标组”配置，独立模型制品、真实源时间、质量检查、历史回放和夜莺固定结果网关已实现；仍是单实例SQLite、按任务短窗口查询，跨卡共享/HA/容量未准入。此项为本地代码与方案审阅而非上游事实。— [本地方案](../../docs/02-技术方案.md)

### Inferences
- 不宜用Merlion Dashboard替换现有Web：保留自己的实体/策略/角色/训练发布回滚/夜莺界面，算法页中按能力展示Merlion候选；Dashboard只做算法研究工具。理由是它的公开交互契约是文件实验，不是现场Prometheus实体与告警闭环。
- 能力边界建议表：

| 层 | Merlion提供 | 我们保留或补建 |
|---|---|---|
| 原始存储 | TimeSeries/Pandas输入格式 | PromQL选择器、鉴权、批量查询、设备标签与单位、源时间/质量 |
| 算法 | 单/多指标算法与部分在线更新、集成 | GPU适用性、工作负载分组、指标选择、效果门禁 |
| 训练 | train和可选标签、保存加载 | 调度/重试/取消、并发资源、不可变快照、制品注册/摘要/审批、版本指针 |
| 在线服务 | get_anomaly_score/label | 历史上下文、水位、幂等、补算、状态检查点、限流分片、故障隔离 |
| 后处理 | 校准和阈值/时间窗过滤 | 检测持续状态恢复与未知态契约；避免叠加过滤造成延迟 |
| 展示 | Python图和实验Dashboard | 同源GPU曲线、能力声明、模型版本、缺口与告警证据 |
| 事件处理 | 后处理分数，不是夜莺事件 | 夜莺事件创建/恢复/关联/通知；不在ML重造事件聚合 |

- 若依赖兼容评估通过也应将Merlion运行环境与当前API服务隔离：控制面通过稳定批量train/score协议调用工作进程/独立镜像，保证以后可切换引擎。这个建议主要基于归档状态和依赖隔离需求；具体冲突版本由维护研究员核实，不在这里假称已经安装成功。

### Gaps
- 未发现官方开箱即用Prometheus＋夜莺插件的可靠证明；这不是证明世界上不存在任何第三方适配。
- 未在现场GPU历史运行Merlion，也未完成其依赖安装、延迟/内存/冷启动/并发容量测试，不能说效果比当前算法更好。
- 未证明官方Dashboard有完整生产RBAC、跨租户、发布审批、HA、模型治理与外部监控连接器；不能把“界面存在”当“平台完整”。

## 具体模型API与模型实例应怎样映射

### Takeaway
Merlion确实统一了训练/评分/后处理与制品接口，但并不决定“每个指标一个独立模型文件”还是共享训练策略。集成时保留当前每GPU每指标/指标组的检测身份，将模型实例与算法名称分离；不要把get_anomaly_label误当布尔标签或故障概率。

### Cited Findings
- DetectorBase支持`train(train_data, anomaly_labels=None, train_config=None, post_rule_train_config=None)`；`get_anomaly_score(time_series,time_series_prev=None)`返回每个时间戳的原始异常分数时序。`get_anomaly_label`返回经过校准/阈值后处理的分数时序，仍不是通用0/1布尔类型。可选labels用于后处理监督训练。— [官方检测API](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.html)
- 模型保存采用`model.save(dirname)`，默认目录含`config.json`及`model.pkl`；加载可用模型类load。工厂支持创建模型及加载示例。编辑config.json可能影响加载配置，因此制品不可变性需我们额外保障。— [官方模型API](https://opensource.salesforce.com/Merlion/latest/merlion.models.html)
- 后处理可组合校准及稀疏化，校准学习单调映射使分数具有z-score解释；这不等于输出GPU故障概率。— [官方后处理API](https://opensource.salesforce.com/Merlion/latest/merlion.post_process.html)
- 正式API包含`MultipleTimeseriesDetectorMixin.train_multiple`，说明库存在多序列训练扩展协议；不能据此推断所有模型都支持跨GPU共享训练。— [官方检测API](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.html#merlion.models.anomaly.base.MultipleTimeseriesDetectorMixin)

### Inferences
- 适配协议建议：`train(snapshot, model_spec) -> immutable_model_directory + report`；`score(model_version, current_batch, previous_context) -> source_timestamp + raw_score + calibrated_score + filtered_score/anomaly + quality`。保存算法、前后处理参数、schema/列顺序、采样周期、环境锁版本、训练快照摘要，沿用现有模型版本与发布流程。
- 真实接口调用示意（概念示例，不是已执行验证）：

```python
from merlion.utils import TimeSeries
from merlion.models.anomaly.isolation_forest import IsolationForest, IsolationForestConfig

# train_df: 时间索引DataFrame；一列=单变量，多列=联合变量。
# 模型必须支持该维度/预处理，不能对所有模型套用任意列数。
model = IsolationForest(IsolationForestConfig())
model.train(train_data=TimeSeries.from_pd(train_df))
raw = model.get_anomaly_score(
    time_series=TimeSeries.from_pd(batch_df),
    time_series_prev=TimeSeries.from_pd(context_df),
)
# 对这一次raw结果应用已训练post_rule，避免对在线可变模型再次评分而重复更新。
filtered = model.post_rule(raw)
model.save(model_dir)
restored = IsolationForest.load(model_dir)
```

- 第一步只做隔离对照评估：同一时序快照、同一正常负载和故障回放、同一告警预算比较当前算法与Merlion候选。不应直接迁移替换在线服务，更不能用算法数量作为采用理由。
- 单指标可按GPU＋metric维护配置并批量展开；多指标按GPU＋字段schema维护配置，先独立训练验证，再研究共享模型。多指标不是“必须预先知道多少种GPU故障目标”，也不能把所有不同作业GPU列拼为一个向量后直接宣称找出故障卡。
- 标准结果不强制`expected/bounds/contributions`非空：只有预测型模型可提供预测参考，重构模型须显式标记重构参考，只有评分能力模型允许仅分数。图表不能为IsolationForest等模型伪造灰色预期线。

### Gaps
- 这里的API示意是根据文档设计，尚未在锁定版本上验证；ModelFactory.load在文档示例与生成签名存在细节差异，落地前应依固定版本实际签名，直接模型类.load更明确。
- 不应声称所有模型都自动输出逐指标贡献，或输出一致的预测置信区间；统一的DetectorBase接口没有这项承诺。

## 时间对齐、数据泄漏与在线恢复怎样保证

### Takeaway
Merlion能表示、对齐和重采样时序，但监控适配层必须控制原始样本时间、缺失质量及因果上下文。自动插值、整段批量评分与部分在线更新不能不加审查地搬进生产。

### Cited Findings
- TimeSeries以多个UnivariateTimeSeries表示多变量，支持Unix时间与Pandas时间索引；各列可不对齐，`align()`默认使用时间并集并插值缺失。— [官方TimeSeries文档](https://opensource.salesforce.com/Merlion/latest/merlion.utils.html)
- `TemporalResample`默认`aggregation_policy='Mean'`、`missing_value_policy='Interpolate'`，有granularity/origin等配置；`Shingle`将相邻观测堆叠为向量，存在左侧补值行为。— [官方Transform文档](https://opensource.salesforce.com/Merlion/latest/merlion.transform.html)
- 某些模型使用`time_series_prev`上下文，不传时可能假定评分批紧跟训练数据。RandomCutForest有`online_updates`配置，不是全部模型都无状态或自动在线学习。— [官方检测API](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.html)

### Inferences
- Prometheus适配保留`source_timestamp`和`evaluation_timestamp`，训练/推理使用同一列顺序、时区UTC、桶边界和聚合定义。若重采样，保存bucket_start/bucket_end和真实源样本范围；不能将插值点伪装为真实采样。
- 在线只处理水位之后的新数据，显式提供紧邻评分批的上下文；源故障、过大缺口、重复序列、无效值、跨列时间偏差按unknown处理，不能插值后当正常解除告警。模型需要规则网格时按事先验证的缺口策略，不盲用默认Interpolate。
- 因果回放按与线上相同批量/窗口执行，先按时间拆分再训练变换/归一化/阈值；不以未来点插值历史缺口，不在测试集重新拟合校准。时序窗口只含当时可获取的数据。
- 支持在线更新的模型需要单写者、模型状态检查点和源水位原子一致，避免重启后同一数据重复更新；禁用在线更新时要安排受控重训。不能把“可以update”当成自动漂移识别和安全重训。
- 停机补算使用有上限的source-time范围及去重；历史补算结果默认不倒灌实时通知。夜莺仍负责外部事件处理，ML只输出现有固定网关契约或后续派生指标。
- 验收至少包含：正常工作负载切换、历史异常污染、缺口/迟到/重复、重采样边界、持续偏移、重启与版本切换、单卡及多卡容量。性能未测前不能把Spark能力等同2秒级每指标服务SLO。

### Gaps
- 当前没有现场GPU标签数据来确定采样周期、上下文长度、阈值、重训频率、所需模型数量以及真实检测率；Merlion不会自动给出这些业务答案。
