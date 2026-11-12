# Merlion算法能力与GPU监控适配

## 单指标、多指标及默认算法是否真正存在

### Takeaway
Merlion确实是比当前自研Ridge/MAD＋PCA范围更广的时序机器学习算法框架，单指标时序和多指标联合检测都有具体实现。但它不是训练好的GPU异常模型，也不能自动确定GPU需要监控哪些指标。**官方仓库已于2026-03-11归档只读**，作为新生产核心应高度谨慎。本笔记依据2026-11-12实际查询的官方仓库及标示2.0.2的官方文档，无GPU实际运行测试。

### Cited Findings
- 官方README将其定位为数据转换、训练、后处理、评估的一体化Python时序框架，含单/多变量预测、异常与变点检测；GitHub顶栏明确2026-03-11归档、只读。[官方仓库](https://github.com/salesforce/Merlion)
- 文档的单指标检测模型包含DynamicBaseline、WindStats、SpectralResidual、StatThreshold、ZMS；多指标有IsolationForest、RandomCutForest、AutoEncoder、DAGMM、LSTM-ED、VAE与DeepPointAnomalyDetector。[官方异常模型目录](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.html)
- `DefaultDetector.train`按输入维度选固定组合：单变量为AutoETS(ETSDetector)+RCF+ZMS；多变量为VAE+RCF。RCF开启online_updates；并非全模型搜索后自动选出最优GPU模型。[defaults.py官方源码](https://raw.githubusercontent.com/salesforce/Merlion/main/merlion/models/defaults.py)
- IsolationForest实现包裹scikit-learn，支持多变量且不强制等间隔采样；默认前处理是差分＋Shingle(size=2)，多变量时是否跳过shingle取决于transform定义，因此不能把默认IF一概称为学习长时间依赖的模型。[IsolationForest源码](https://raw.githubusercontent.com/salesforce/Merlion/main/merlion/models/anomaly/isolation_forest.py)
- AutoEncoder使用可配置sequence_len的滚动窗口，默认sequence_len=1；训练使用PyTorch，输出重构误差范数作为分数。默认并不等于长序列时间模型。[AutoEncoder源码](https://raw.githubusercontent.com/salesforce/Merlion/main/merlion/models/anomaly/autoencoder.py)

### Inferences
- 我们可复用其算法与接口，减少自研；不应直接用DefaultDetector全覆盖上千条GPU时序：默认单指标引入Java RCF，多指标引入PyTorch VAE，模型数量、线程、内存、训练耗时需实测。
- 首批候选可限定单指标ZMS、MSESDetector、AutoETS/ETSDetector；多指标IsolationForest，再评估AutoEncoder/VAE是否有额外收益。这是候选实验计划，不是GPU验证后的算法推荐。
- 多指标输入一组GPU metric，通常训练一个联合模型实例；每卡独立还是按设备/负载分组共享不能由“支持multivariate”推导出来。不要把不同GPU的同名指标直接拼在一起就宣称共享模型已完成。

### Gaps
- 未找到官方提供适配H100监控的预训练模型、GPU故障覆盖矩阵或真实H100检出/误报基准；没有依据承诺开箱即用GPU效果。
- 未实际安装或执行；未获得指定模型在本系统2秒采样、8指标、目标GPU规模下的性能和准确率。

## 自动选模、训练、标签与评分是什么含义

### Takeaway
统一训练/评分接口、校准、阈值和组合器是明显价值；但“有AutoML”不等于无标签时自动找到最佳异常检测器。模型拟合与后处理训练应区分，生产上仍需时间切分、独立评估和真实负载验证。

### Cited Findings
- `DetectorBase.train(train_data, anomaly_labels=None, ...)`执行无监督模型训练；标签可选，有标签时用于后处理的监督训练。`get_anomaly_score`返回每个目标时间戳的分数时序；`get_anomaly_label`实际返回校准/阈值处理后的分数时序，而不是必然0/1布尔值；接口支持save/load。[DetectorBase官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.html)
- AutoML目录主要是AutoETS、AutoProphet、AutoSarima及季节性搜索；AutoETS根据AIC/AICc等准则搜索其模型结构，并不是对所有异常模型的统一无标签择优。[AutoML官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.models.automl.html)
- DetectorEnsemble有Mean/Median/Max等组合器，也有ModelSelector及按指标加权的组合器；ModelSelector依据指定评估指标给候选排序。[Ensemble官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.models.ensemble.html)
- ModelSelector源码在target=None且没有先前metric_values时为各模型给相同值1，而不是凭空推断检出优劣；存在ground_truth才调用指定指标计算排序。[combine.py官方源码](https://raw.githubusercontent.com/salesforce/Merlion/main/merlion/models/ensemble/combine.py)
- 分数校准学习单调映射使分数具有z-score解释；阈值可以用标签和评估指标挑选，也可用无监督分位数或固定默认值。`AggregateAlarms`默认2个点/60分钟窗口、抑制120分钟，是后处理过滤，不是监控事件平台。[后处理官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.post_process.html)

### Inferences
- 我们应统一保存raw_score、calibrated_score、threshold及is_anomaly，避免把get_anomaly_label当Boolean，或把标准化z-score当故障概率。
- 不能继续沿用当前score>threshold的假设而不适配符号：若Merlion后处理配置abs_score=True，判断应按该语义，不能漏掉负向异常。
- 用户无故障标签时，可做轻量基线对比、正常期告警率/稳定性与人工反馈验证，不能用AutoML宣传替代生产效果评估。
- Merlion AggregateAlarms若与我们3点确认和夜莺持续/抑制叠加，可能造成大延迟或恢复语义混乱。建议选一个明确ML分数后处理契约；跨模型事件关联/通知继续夜莺，不能把它的AggregateAlarms当完整告警系统。

### Gaps
- 未证明其无监督默认阈值适合现场误报预算；不能给固定训练天数或故障召回承诺。

## 在线推理、时间对齐与灰线可视化能否直接沿用

### Takeaway
框架能按源时间返回分数、支持历史上下文与部分在线更新模型，但它不是替我们管理消费offset、迟到数据和故障恢复的流平台；也不是每种模型都能给灰色预测线与预测区间。

### Cited Findings
- TimeSeries基于带时间索引的pandas Series/DataFrame，可由from_pd构造；时间戳与值逐点对应，有window、concat、bisect和重采样工具。[TimeSeries官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.utils.html)
- TemporalResample可以指定/学习granularity、聚合策略、缺值填充策略；Shingle将邻近观测堆叠成向量，支持stride，开头可能填充；多指标默认multivar_skip=True。[Transform官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.transform.html)
- RCF源码online_updates决定评分时是否更新，先getAnomalyScore再update，维护last_train_time；默认transform是差分+5点shingle。RCF通过Py4J启动JVM，序列化用AWS RCF JSON。[RCF官方源码](https://raw.githubusercontent.com/salesforce/Merlion/main/merlion/models/anomaly/random_cut_forest.py)
- MSESDetector有online_updates=True选项，预测基于多尺度平滑与近期历史；max_forecast_steps、max_backstep、recency_weight等明确可配置。[MSES官方文档](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.forecast_based.html#module-merlion.models.anomaly.forecast_based.mses)
- ForecastingDetectorBase以预测残差或除以预测标准误后的偏差评分，支持forecast/time_series_prev；预测型异常检测一次只针对一个目标单变量，即使底层使用多变量输入。[预测型检测文档](https://opensource.salesforce.com/Merlion/latest/merlion.models.anomaly.forecast_based.html)
- 预测型源码先对齐forecast.time_stamps，再对target_seq_index取目标；可绘预测与不确定性，但不确定性不是所有模型都支持。预测型异常检测默认不一定将变换反演回原指标单位。[ForecastingDetectorBase源码](https://raw.githubusercontent.com/salesforce/Merlion/main/merlion/models/anomaly/forecast_based/base.py)

### Inferences
- 我们的Prometheus适配仍需保证UTC源时间、固定周期/字段顺序、唯一性、质量掩码与缺口策略；Merlion插值和填充能力不意味着缺数可当健康，训练和在线必须同一transform及周期。
- get_anomaly_score(new_data, time_series_prev=context)是推理接口，不保证模型在线学习；只有明确支持的模型才更新。RCF/MSES等有状态更新需要checkpoint、offset和去重，不可将同一在线模型用于乱序回放/影子而污染生产状态。
- 用户问“取多少周期”：不存在Merlion统一答案；按模型的n_lags/shingle/sequence_len/max_backstep和采样周期固定并随制品保存。季节性模型要覆盖相应周期，不能直接复用我们的“最少240点”当通用门槛。
- 统一可视化输出应允许reference=null：预测模型给forecast reference及实际可用的区间；IF/RCF等通常仅有score，不伪造灰线；AE重构若另行暴露应标reconstruction而非forecast。若使用差分空间预测，不能直接叠到原始温度曲线上。
- Merlion替代算法层合理，但现有源读取、模型注册/审核/发布回滚、隔离回放、状态持久、Web、夜莺适配等生产工程仍需本系统负责。

### Gaps
- 没有实测在线更新持久化、乱序/重复输入、长缺口恢复、时间变换反演、置信区间覆盖和单进程线程安全；接入前需要针对候选模型建立契约测试。
- 官方API未提供通用多指标贡献/根因输出；不同模型不能承诺统一贡献值，不能将异常检测直接写成GPU故障诊断。
