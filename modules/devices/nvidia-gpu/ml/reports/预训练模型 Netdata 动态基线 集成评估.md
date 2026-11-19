# 接入 预训练模型 借鉴 Netdata 改善 动态基线

调研日期：2026-11-17。**Chronos、Toto 和 TimesFM 的合适版本可以接入现有远程模型架构；建议先做小模型验证，不直接替换当前在线模型。** 我们已有HTTP连接、模型登记、试评分和结果校验，但还没有这些基础模型的运行时适配器，填写Hugging Face模型名不会自动完成接入。预训练权重可以保持不变，多张GPU共享一份加载后的权重；每个任务仍需独立的指标契约、上下文配置与异常评分校准。Netdata值得借鉴的是历史数据筛选、时间特征、异步训练与版本管理，其K-means路线输出异常评分，**不能直接提供动态预测曲线**。库选型建议先复用现有scikit-learn，暂不因Netdata使用dlib就增加一套C++依赖。本轮只调研，未下载或运行候选权重，未修改服务；下面的集成顺序是工程建议，不是实测准确率排名。

## 预训练模型可复用，但必须按具体权重选型

| 候选 | 已核实能力与许可 | 对本项目的判断 |
|---|---|---|
| Chronos-Bolt tiny / small | 9M / 48M参数，零样本单变量分位数预测；相关代码和两个具体权重卡为Apache-2.0 | 首轮单指标候选；批量预测多条序列不等于学习多指标联合关系。[模型卡](https://huggingface.co/amazon/chronos-bolt-tiny)、[small](https://huggingface.co/amazon/chronos-bolt-small) |
| Toto 2.0 4m / 22m | 4M / 22M，零样本、多变量、分位数预测；具体权重卡为Apache-2.0 | 与监控领域接近，可与Bolt并列验证；领域相关性不能代替GPU故障效果证据。[官方项目](https://github.com/DataDog/toto)、[4m权重](https://huggingface.co/Datadog/Toto-2.0-4m)、[22m权重](https://huggingface.co/Datadog/Toto-2.0-22m) |
| Chronos-2 | 120M，支持单变量、多变量和协变量，权重卡为Apache-2.0 | 作为后续多指标/协变量候选；首轮无须先做权重微调。[官方模型卡](https://huggingface.co/amazon/chronos-2) |
| TimesFM 2.5 | 200M，支持预测与分位数；该版本权重为Apache-2.0 | 可作为后续对照。不能把单变量批预测及XReg增强宣传为3.0的原生多变量能力。[2.5模型卡](https://huggingface.co/google/timesfm-2.5-200m-pytorch) |
| TimesFM 3.0 | 下载/自托管权重受非商业、非生产许可限制；官方云服务另按服务条款 | 不纳入当前商业自托管候选，不能从仓库代码的Apache标识推导权重许可。[官方许可区分](https://github.com/google-research/timesfm#license-notice-for-pretrained-weights) |

这些模型提供的是预测能力，不是已经针对我们GPU环境调好的告警器。以过去窗口预测当前点时，**零样本表示不更新预训练权重，并不表示不输入历史，也不表示无需校准异常阈值**。q10～q90等分位数可以形成参考带，但其实际覆盖率必须在自身正常历史上测量；越带不直接等于硬件故障概率或固定事件误报预算。持续漂移还可能被模型逐步追随，使预测残差下降，因此必须同时测试尖峰、持续水平变化和慢漂移。

候选依赖应独立锁定。Toto 2当前README与包定义的PyTorch最低版本存在差异，不能只照安装说明混装；CPU可运行示例也不证明本项目CPU时延达标。实施前需固定代码提交、包版本、权重revision及摘要，再测冷启动、内存和批量吞吐。[Toto包定义](https://github.com/DataDog/toto/blob/main/toto2/pyproject.toml)、[官方要求](https://github.com/DataDog/toto#requirements)

## 复用HTTP边界，在模型服务端增加预测和校准适配

建议保留监控主进程的轻量依赖，在独立预测服务中加载预训练权重并实现现有info、目录、模型描述、部署与predict协议。部署前下载并校验权重，推理热路径不临时联网拉取。**服务端按不可变checkpoint共享权重缓存，按GPU任务创建轻量部署清单**；清单保存实体、指标/单位、采样周期、上下文长度、预测步长、预处理、评分公式和校准版本。这样既不按每张卡复制权重，也不放松当前实体/schema隔离。[现有登记校验](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/model_backends/services.py)、[接口契约](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/docs/17-远程模型接入与登记.md)

因果适配须用`x[t-L]…x[t-1]`预测`x[t]`，当前实际值仅在预测之后用于计算残差或区间外距离；HTTP请求虽然包含当前点，服务端不能把它混入预测上下文。预测值映射`expected`，有依据的分位数映射`bounds`，经过独立历史校准的非负分数与阈值映射`score/threshold/anomaly`。返回的评分时间须是请求中的当前源时间，不能将未来时间戳直接充作在线结果。[现有结果合同](/home/mqq/github/zj/NPUMonitor/modules/model-services/contracts/model_contracts/__init__.py:30)

现有参考Runtime的fit、joblib制品类型检查和检测器白名单不能直接加载任意基础权重，需新增运行时或独立服务。当前240源点及60/20/10/10切分是既有流水线门槛，校准段至少12个评分点，比较/测试各至少6个评分点；基础模型长上下文必须按预热后的有效评分数另行预检。**4～60点只限制现有滞后回归配置，远程协议允许最多12000个历史样本**，不能把两者混为一谈。[现有流水线](/home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/pipeline.py:74)

现有默认2秒轮询、15秒新鲜度、12秒HTTP超时及逐任务顺序评分，尚不能视为基础模型的容量承诺。应在服务端批处理、缓存共享权重，并测队列等待及端到端p95/p99；若需要较慢分析周期，应显式配置，而不是静默放宽新鲜度或将超时当正常。已有多个推理服务连接也不等于已具备多个训练后端调度。[监控设置](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/settings.py)、[当前调用循环](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/engine.py)

## Netdata学习近期变化模式，不预测下一点

Netdata源码固定为提交`5ddadd98e40e597a205cba6e2835693becefabce`。其流程是每个指标分别查询已存储历史，检查有效样本，处理缺失，再依次做差分、滑动平均、滞后向量，抽样后训练两个K-means中心。实时评分使用包含当前观测的同类时间特征；这里是在识别当前模式，不是先预测当前值再计算残差。固定源码的特征流程没有学习型StandardScaler/z-score步骤，不能将距离分数缩放说成输入标准化。[历史查询](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L184-L312)、[特征处理](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_features.cc#L26-L125)

| 固定源码中的新安装默认值 | 含义及不能误读的地方 |
|---|---|
| 6小时历史、最低15分钟有效数据 | 可配置的数据准备门槛，不是GPU通用训练要求 |
| 每3小时训练、每指标最多18模型 | 训练节奏和有限版本上限，不保证队列中每项严格准时执行 |
| 期望抽样1440个训练向量 | 概率抽样目标，不是严格硬上限 |
| 差分1、最大平滑3、lag 5 | 默认逻辑特征向量长度6；实际平滑受采样间隔影响 |
| 评分阈值0.99 | 距离范围缩放后的阈值，不是99分位数或99%置信度 |

上述以固定提交的配置和算法实现为准；部分README流程图仍写4小时或“99th percentile”，不可混用。[配置与迁移代码](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_config.cc#L34-L220)

其dlib调用为`pick_initial_centers`和`find_clusters_using_kmeans`。评分先取到**全部两个中心的平均欧氏距离**，再用训练距离min/max缩放，最后限制分数上界；这与常见的最近中心距离不同。它不输出原指标的预测中线/正常上下界，不能把聚类中心直接画成我们的动态参考带。[固定版训练与评分](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc#L37-L130)

值得借鉴后台队列、常量指标筛选、generation隔离、候选发布和有限版本持久化。需要修改的则是质量语义：Netdata会对中间无效历史做前向填充，实时缺失会重置窗口；当前退化模型可返回NaN弃权，而零模型、全部弃权、预热或抑制等分支可返回false。**这个false表示“不标异常”，不能被我们映射成有效正常、进而解除已有事件**。其常量指标聚合统计也不是硬件健康证明。[评分分支与聚合](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L1133-L1377)

多模型共识让任一有效正常模型否决异常，减少某些误报也可能降低召回；长期故障混入重训后还可能被吸收为正常。这是需要比较的策略，不宜照搬18模型全同意规则。我们的候选应保留冻结、故障窗口排除、独立验证和人工启用，缺失/弃权保持unknown。单指标的多个滞后特征仍是单指标检测，不因此成为多指标联合检测。

## 先复用scikit-learn，dlib暂不成为必要依赖

**dlib核心采用Boost Software License 1.0，并非BSD**；Netdata所用普通K-means关键接口是C++接口。官方Python文档只覆盖部分功能，本轮未找到该普通K-means函数的对应官方Python绑定，不能假定`pip install dlib`就能直接复用Netdata流程。[dlib许可](https://dlib.net/license.html)、[C++接口](https://dlib.net/dlib/svm/kkmeans_abstract.h.html)、[Python接口](https://dlib.net/python/)

项目已有scikit-learn 1.6.1；其`KMeans.transform`可返回到各中心的距离，我们可显式取平均，自行实现相似评分及退化检查。初始化、停止条件等不同，因此应命名为“借鉴Netdata的时间模式检测”，不承诺逐位兼容。只有必须复现C++行为，或实测证明资源/时延收益足够时，再增加dlib原生绑定或独立C++服务。[项目依赖](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/demo/requirements.txt)、[KMeans接口](https://scikit-learn.org/1.6/modules/generated/sklearn.cluster.KMeans.html)

借鉴公开算法设计与直接复制实现应分开：固定Netdata ML源文件标注GPL-3.0-or-later，不能用dlib的宽松许可替代对Netdata代码复制、链接和分发方式的审查。本报告未开展具体交付方案的法律评估。[Netdata源码许可标识](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc#L1)

## 用两条受控实验决定下一阶段

建议同时验证“冻结预训练预测＋残差校准”和“时间特征K-means仅评分”，保留当前Ridge及上一值/训练中位数为对照。前者服务动态曲线能力；后者声明`reference_kind=none`，服务行为异常补充。两条路径使用同一批首批5项指标快照、相同时间分区和标签范围，先离线，再影子运行，最后显式登记/启用；不把最终测试段用于反复调参。

验收同时记录MAE、实际区间覆盖、有效评分覆盖、标注正常时段每GPU每日事件误报数、已标异常检出、确认后延迟和资源消耗。测试覆盖正常高负载、合法空闲零、负载切换、常量、尖峰、持续偏移、慢漂移及缺测/陈旧/重复；涉及累计衍生量时另测reset。未标注数据只报告告警比例，模拟检出不外推真实GPU准确率。当前尚未下载模型、编译dlib或跑这些比较，也没有生产容量证据。

产品上可继续保留“选择模型”和“历史学习”两条入口，但应分别说明：选择预训练方案后，系统准备共享权重并自动完成任务绑定/历史校准；选择轻量检测方案后，系统按预设配置自动拟合自身历史。**免手工训练配置、免权重微调、免历史校准是三件不同的事**。把这些状态分别记录和展示，才能让用户理解模型来源，也能避免把通用权重误呈现成已经为本设备验证过的成品异常模型。
