# 现有服务集成差距与 dlib 取舍

研究日期：2026-11-17。仅调研，不修改代码、不启动或更换服务。仓库路径以下均相对 NPUMonitor 根目录；行号对应本次读取版本。

## 通用预训练时序模型能否直接登记到现有远程模型服务？

### Takeaway
可以复用 HTTP 边界，但不能把一个通用 checkpoint 当成当前目录里的成品 GPU 异常模型。需要在独立推理服务中增加适配层，将共享预训练权重、GPU 任务绑定、因果预测、残差校准和阈值封装成不可变版本；当前历史训练实现也不支持直接加载任意基础模型。

### Cited Findings
- 当前远程登记严格匹配 entity、source_type、完整 feature_schema、指标 ID/单位；要求冻结、无状态，history_samples 允许 0..12000、cadence_seconds 允许 2..86400，参考类型支持 none/causal_forecast/joint_reconstruction/conditional_baseline。目录会过滤不兼容条目，并非通用模型下载列表。[services.py:82](../../backend/gpu_ml/model_backends/services.py#L82)
- 登记会拉取最近窗口，调用试评分，评分后再次检查新鲜度；不下载权重、不创建本地训练快照。试评分成功仅验证连接/协议，不证明检测准确率。[services.py:115](../../backend/gpu_ml/model_backends/services.py#L115)、[接入文档:9](../../docs/17-远程模型接入与登记.md#L9)、[接入文档:39](../../docs/17-远程模型接入与登记.md#L39)
- 新登记服务用于多个推理来源；历史训练仍通过单一默认训练后端，外部模型的重新校准/集成目前需在其所属平台进行。[接入文档:13](../../docs/17-远程模型接入与登记.md#L13)
- 当前参考服务仅接受 fit/postprocess/ensemble，fit 调用 build_pipeline；模型缓存按已有制品引用加载。流水线构建受模板 algorithms 和 DETECTORS 白名单限制，当前检测器为 temporal_mad、joint_pca、joint_iforest、level_mad，制品加载器也检查具体类/版本。[runtime.py:39,70,96,112](/home/mqq/github/zj/NPUMonitor/modules/model-services/reference-platform/gpu_ml_platform/runtime.py:39)、[pipeline.py:74,172,179](/home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/pipeline.py:74)、[detectors.py](/home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/detectors.py)
- 响应必须保留原始 values，评分时间来自请求输入，valid 必须覆盖最新输入时间；不能直接返回未来时间戳的 forecast 作为当前点的合法评分。[合同:30](/home/mqq/github/zj/NPUMonitor/modules/model-services/contracts/model_contracts/__init__.py:30)

### Inferences
- 推荐新增独立 foundation-model HTTP 服务，监控主服务保持轻量：共享缓存基础权重，按批处理多个 GPU 窗口；每个任务只保存轻量适配清单，不为每个指标重复下载/加载权重。不要把 torch/CUDA 依赖放入监控主进程。
- 建议适配清单至少记录：checkpoint ID、不可变 revision/摘要、许可证、运行精度/设备；entity、source_type、schema、单位、采样周期；有界 history_samples、缺测策略、预处理版本；预测目标/步长；残差分数定义、校准数据摘要/时间段、阈值、评估报告。清单作为 model_ref 版本绑定；通用权重可共享，任务校准不能混用。
- “零样本”应明确为不更新预训练权重；仍需输入历史上下文。若产品要输出异常事件，还需单独校准残差/区间及阈值，不能把原生预测分位数直接等同于已验证 GPU 告警置信度。
- 因果适配应以 t 之前的数据预测观测 x[t]，再比较 x[t]；不能把目标值喂进上下文后，使用拟合/重建值声称提前预测。多变量预测能力也不自动等于多指标联合异常、根因解释能力。
- 最小产品路径是先离线/影子评估，合格后由远程服务暴露现有标准目录/描述/预测接口，沿用现有登记；不要放宽 entity/schema 校验以让任意基础模型出现在“选择模型”里。

### Gaps
- 本轮未实现基础模型适配器；尚无真实 GPU 数据上的精度、资源、吞吐/延迟证据。checkpoint 最大上下文等应以具体版本的模型研究笔记为准，不是本系统已有能力。

## 现有历史训练和在线时效约束要怎样调整理解？

### Takeaway
已有训练流水线是有时间分区、残差校准的冻结模型流程，但样本门槛和当前准入报告不足以证明生产误报/漏报。基础模型可以声明比现有 Ridge 更长的上下文；必须同时验证在线吞吐和源时间新鲜度。

### Cited Findings
- 当前严格流水线至少 240 个源样本，按时间 60/20/10/10 划分训练、校准、选择、测试；校准最低 12 个评分点，selection/test 各要求至少 6 个实际评分点。现有 lag 参数检查为 4..60，仅属于当前 detector 配置，不是 HTTP 的窗口上限。[pipeline.py:48,74,98,115](/home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/pipeline.py:48)
- 参考服务外层训练允许 180..12000 条，但进入严格流水线仍受 240 门槛；发布状态用 held_out_point_alert_rate<=0.1 判断 validated。这个指标是留出数据告警比例，不等于已标注正常数据上的误报率，也不证明故障召回。[runtime.py:112,149,159](/home/mqq/github/zj/NPUMonitor/modules/model-services/reference-platform/gpu_ml_platform/runtime.py:112)、[pipeline.py:135](/home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/pipeline.py:135)
- 默认轮询 2 秒，源时间新鲜度 15 秒；推理任务目前在同一循环顺序执行，评分前后检查新鲜度。默认 HTTP 超时 12 秒，允许响应最多 16 MiB。远程 history_samples 最大 12000，不应错误写成只能传 60 点。[settings.py:14](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/settings.py:14)、[engine.py:210](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/engine.py:210)、[http.py:13,26](/home/mqq/github/zj/NPUMonitor/modules/model-services/adapters/model_adapters/http.py:13)、[services.py:94](../../backend/gpu_ml/model_backends/services.py#L94)

### Inferences
- 基础服务应声明自身有界上下文，并根据有效评分点而非源样本数检查训练/校准/评估可用性。长上下文不能直接套用现有 240 点门槛；需保留各段足够 warmup 后的独立评分。
- 必须记录暖启动/冷启动、队列等待、网络、p95/p99 端到端时延、源时间年龄，以及多 GPU 并发吞吐。长上下文每 2 秒重复传输和逐任务调用可能成为瓶颈；优先权重缓存、批量推理、有界队列和并发隔离。
- 若评估发现需要较慢分析周期，应显式修改任务采样/展示约定，并保留原始曲线；不能靠静默放宽新鲜度或把超时映射正常来掩盖问题。
- 将当前 10% 告警比例自检替换/补充为清晰校准报告和有标签验收门槛；数据无标签时如实写“告警比例”，不可假定全部正常。

### Gaps
- 尚未测量当前多任务轮询的最大负载；本轮没有更改调度、超时或验收规则。

## 是否应因为 Netdata 使用 dlib，就给 Python 服务引入 dlib？

### Takeaway
建议先复用已有 scikit-learn 实现“借鉴 Netdata 的时间特征聚类”实验候选，暂不新增 dlib。Netdata 使用的是 dlib C++ 普通 KMeans 训练接口；不能认为 pip dlib 已完整提供同名 Python API，也不能认为换库会自动改善检测效果。

### Cited Findings
- dlib 官方 C++ 普通聚类接口为 pick_initial_centers 和 find_clusters_using_kmeans，后者接收已有中心并更新中心；同一头文件中的 kkmeans 类是核 KMeans，应区分。[dlib C++ API](https://dlib.net/dlib/svm/kkmeans_abstract.h.html)
- dlib 官方说明其主要为 C++ 库，只有部分工具有 Python API。本轮在官方 Python 文档未发现 find_clusters_using_kmeans；其中的 chinese_whispers、bottom_up_clustering 并非这个普通 KMeans 接口。不能据此绝对断言所有第三方版本均无绑定，但不可按直接可用设计。[dlib Python API](https://dlib.net/python/)
- 官方编译文档当前要求 CMake>=3.17、C++17；Python 包包含本地扩展构建，新增绑定涉及 C++/构建维护。[编译说明](https://dlib.net/compile.html)、[官方 setup.py](https://github.com/davisking/dlib/blob/master/setup.py)
- dlib 核心许可证是 Boost Software License 1.0，不能写成 BSD。许可证允许使用/修改/分发，但仍应保留适用版权/许可文本；依赖和单独模型权重许可证须分开检查。[dlib license](https://dlib.net/license.html)
- 项目已经依赖 scikit-learn==1.6.1。该版本 KMeans 提供 n_clusters、init、n_init、max_iter、tol、random_state；transform 返回样本到每个中心的距离，可构造所需距离分数。[项目依赖](../../demo/requirements.txt)、[sklearn 1.6.1 KMeans](https://scikit-learn.org/1.6/modules/generated/sklearn.cluster.KMeans.html)
- 固定 Netdata 版本 5ddadd98e40e597a205cba6e2835693becefabce 用 dlib 训练 2 个中心，评分取到全部中心的平均欧氏距离，再用训练距离 min/max 缩放，不是最近中心距离/百分位。退化或极窄 spread 返回 NaN 弃权；不能照抄旧网页缓存里的退化返回 0。[固定版 ml_kmeans.cc](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc)

### Inferences
- sklearn 候选可显式计算 KMeans.transform(X).mean(axis=1)，但 sklearn 与 dlib 初始化、停止条件等不同，不能宣称逐位复现 Netdata。若改成最近中心距离，应另行命名/评估分数，避免称完全等价。
- dlib 的合理引入条件是：必须复现 Netdata C++ 行为，或基准证明有实质性能/资源收益；届时应固定版本，补专门绑定或独立 C++ 服务，承担镜像构建/平台兼容维护。没有这样的需求时，增加第二套普通 KMeans 实现收益不足。
- 借鉴的是指标适用性筛选、时间特征、异步调度、冻结版本/候选更新和可选多窗口共识；不是用聚类替换预测曲线。单指标多个滞后特征依然是单指标时间模式检测，不等于多 GPU 指标联合检测。聚类候选 reference_kind 应为 none，除非另外实现可解释且有验证的预测器。
- 对退化/全弃权，必须适配现有 unknown/quality 语义，不能把未评分当正常。多模型一致才报异常可能降低部分误报，也可能遗漏渐变故障，应作为实验策略；定期重训也应产生候选版本，走影子评估/显式启用，而非绕开当前冻结模型约束。
- 不应不加验证地把每窗口标准化复制到预测路径：可能削弱绝对水平偏移信号；需独立评估水平漂移与形状异常。

### Gaps
- 未在本机安装/编译 dlib 或证明其 Python 绑定集合；没有 dlib/sklearn 针对本项目的速度或检测质量对比，不能声称任一库更快或更准。

## 下一步怎样做受控技术验证？

### Takeaway
建议保留当前 Ridge 基准，平行验证一个小型预训练零样本预测模型和一个时间特征 KMeans 候选；用同批历史、同样时间切分及独立校准作决策，不急于增加生产算法和依赖。

### Cited Findings
- 当前已支持影子模型单独评分，主模型独立；当前 Ridge 具有因果滞后预测，PCA/IsolationForest 则是现时多变量评分，语义不同。[engine.py:236](/home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/engine.py:236)、[detectors.py:30](/home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/detectors.py:30)

### Inferences
1. 先固定首批指标、采样周期、设备与时间范围；同一历史分成拟合、校准、选择、最终测试，所有预处理只拟合训练段。不能用最终测试调阈值，也不能把注入标签当输入特征。预训练权重不训练也不表示可以省略校准/最终评估。
2. 同批比较 persistence/训练中位数、当前 Ridge、一个冻结预训练模型、时间特征 KMeans。单指标与多指标任务分开评估；多指标至少覆盖单独异常和关系破坏两种测试。
3. 数据应含高负载、空闲、负载切换、长期常数、零值、缺测/陈旧/重置，以及有已知标签的尖峰、漂移、持续异常。模拟结果只证明机制与演示路径，不能外推真实故障准确率。
4. 报告预测 MAE、经验区间覆盖率、有效评分覆盖率、标注正常时段的每 GPU 每日事件误报数、标注异常召回和含确认/网络延迟的检测时间；同时报 CPU/GPU 内存、并发吞吐和端到端时延。无标签数据仅报告告警比例，不使用“误报率/准确率”。
5. 先离线，再影子回放/在线影子，再显式登记/启用；只有测得收益才引入新的训练入口或 dlib。界面应显示“基础权重来源”“是否更新权重”“GPU 校准时间段”“评分/参考类型”和实际执行位置，避免把通用开源权重误呈现成已经针对本设备训练好的成品模型。

### Gaps
- 真实 GPU 历史和故障标签可用性、生产误报预算、并发设备规模尚待业务确认；这些限制不妨碍先做模拟数据受控实验，但会阻止宣称生产效果已验收。
