# Netdata 历史训练、dlib 与动态基线借鉴评估

## 1. 历史训练和实时判断实际上怎样工作？

### Takeaway
Netdata 的这条 ML 路线是每个指标各自学习历史变化形态的无监督异常检测，不是下载通用预训练权重，也不输出预测值、正常上下界或动态基线曲线。可以借鉴其数据准备、异步训练和模型管理，不能把它直接当成我们的曲线模型。

### Cited Findings
本文源码统一固定为调研日 2026-11-17 官方仓库 HEAD `5ddadd98e40e597a205cba6e2835693becefabce`，避免 master 与网页缓存的版本差异。下列链接均为该提交。

- 每个 RRD dimension 单独取历史：以最近已存储时间为终点，起点取“终点减训练窗口”和首个可用时间的较大值；按该 chart 实际采样间隔计算样本数，从 tier 0 查询点并取 `sum/count`。要求足够的实际有效点及特征窗口长度；复制中的 chart 不训练。中间无效值以前一有效值填充，开头 NaN 则裁掉。——[历史查询与有效性检查](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L184-L312)
- 特征依次为差分、滑动平均、滞后向量。默认 diff=1、最大平滑长度=3、lag=5，逻辑向量长度为 6；低于 5 个 lag 时物理六维数组剩余位置置零。chart 采样间隔大于全局采样间隔时，实际平滑长度改为 1。训练随机抽样，推理不抽样。这里未见 StandardScaler/z-score 等学习型标准化；不能宣称它使用了这类归一化。——[特征代码](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_features.cc#L26-L125)、[平滑配置处理](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L184-L193)
- 推理把最新值放入环形窗口，然后用包括当前值的窗口构造同类特征，评分当前模式；没有先预测下一点再比较残差的步骤。训练模型只存中心、距离范围、时间等信息，不保存未来预测序列或置信区间。——[实时推理](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L1133-L1271)、[模型结构与序列化](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc)
- 核心算法是 `dlib::pick_initial_centers(2, ...)` 后 `dlib::find_clusters_using_kmeans(...)`，固定两个中心。训练和评分使用到两个中心的**平均欧氏距离**，不是通常的最近中心距离。对训练样本记录该平均距离的 min/max，在线分数为 `min(100, 100 * abs((d - min)/(max - min)))`。因此 sklearn 的 predict/inertia 不是等价替代；若自行实现相似方法，需明确平均中心距离和距离范围评分。——[K-means 训练和评分](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc#L37-L130)

固定提交的新安装默认值如下，均为可配置值，不是我们的设计建议：

| 参数 | 固定源码默认值 | 解释 |
|---|---:|---|
| training window | 6 小时 | 按时间长度读历史 |
| minimum training window | 15 分钟 | 实际有效样本的最低时长要求 |
| train every | 3 小时 | 训练队列的节奏目标，不保证每个指标严格同时执行 |
| number of models per dimension | 18 | 活跃模型数量上限；约覆盖 54 小时训练时刻 |
| maximum training vectors | 1440 | 按比例随机抽样的期望目标，不是严格硬上限 |
| diff / max smooth / lag | 1 / 3 / 5 | 特征处理配置 |
| maximum k-means iterations | 1000 | 聚类迭代上限 |
| dimension anomaly score threshold | 0.99 | 距离范围分数阈值，对应分数 >=99 |
| delete models older than | 7 天 | 数据库全局清理保留期，不等于在线 ensemble 必有 7 天模型 |
| host anomaly threshold / aggregation | 1.0 / average、5 分钟 | 聚合检测相关默认值 |

——[配置默认值、范围和旧配置迁移](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_config.cc#L34-L220)

- 官方资料存在跨版本或示意图冲突：仓库 README 的流程图写“Last 4 hours”和“99th percentile”；当前配置文档与上述源码采用 6 小时及训练距离范围阈值。**0.99 不是 99 分位数、99% 概率或 99% 置信度。** 配置文档仍混有旧的 maximum samples/minimum samples/sampling ratio 示例；源码会根据全局采样间隔迁移旧设置，因此不能机械把旧 21600 点恒等为所有部署的 6 小时。——[官方 README](https://github.com/netdata/netdata/blob/master/src/ml/README.md)、[官方配置文档](https://learn.netdata.cloud/docs/netdata-ai/anomaly-detection/ml-configuration)、[固定源码迁移与默认](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_config.cc#L34-L220)

### Inferences
- 我们可以提供“历史自训练异常检测”作为独立模型类型，但基线中线/上下界仍应由预测或统计基线模型产生。把两个 K-means 中心画成 GPU 指标的正常值/区间，没有这里的算法依据。
- 历史数据足以无监督拟合，但需要指标身份、采样间隔、质量规则、适当时长和正常运行覆盖；无标签不代表不需要数据治理或效果验证。建议使用按时间划分的留出验证，不能从“训练完成”推导“已验证有效”。
- 对我们而言缺失填充须受最大间隔约束，并显式输出质量状态；照搬无限前向填充会把断采伪装成稳定。

### Gaps
- 未找到针对我们首批 GPU 指标的准确率、召回率、最低样本量或容量基准；官方通用效果宣传不能当成本项目验收结论。

## 2. 多模型、异常状态和训练生命周期能否直接照搬？

### Takeaway
适合借鉴异步训练、有限模型版本、持久化及重置隔离；不能照搬“缺失、无模型、全部弃权返回正常”的二值语义。我们的 unknown 必须保留 active 告警，不能成为恢复依据。

### Cited Findings
- 当前固定源码对 `max == min`、相对距离跨度极小，以及旧版 `(0, DBL_MIN)` 占位模型返回 NaN，表示弃权。某些网页缓存的旧版仅返回 0，不能混用解释。——[当前退化处理](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc#L93-L130)
- 推理跳过 NaN 模型；任何有效模型分数低于阈值就立即返回 false，只有至少一个有效模型、且全部有效模型均超过阈值才返回 true。零模型、全部弃权、缺失 exists=false、窗口未填满、锁未取得、禁用或 silenced 等路径均可返回 false。缺失还会清空推理窗口。**这里 false 是“不标异常”的布尔结果，不能在我们的接口中等同 fresh healthy。**——[推理完整分支](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L1133-L1271)
- 常量指标会跳过训练；成功训练和部分失败路径将 metric type 设为 constant，后续新值发生变化又设为 variable。这是调度优化状态，不是永久健康证明。chart 聚合统计中 constant 分支无条件计为 trained/normal，即使没有模型；variable/untrained 不计为 normal/anomalous。推理函数自身没有仅因 constant 而立即跳过评分的分支，应区分模型评分与聚合统计。——[训练及状态迁移](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L859-L1129)、[正常/异常统计](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L1320-L1377)
- 每个指标保留有限模型，达到上限后轮转；存在训练窗口重叠时替换末尾模型的优化。SQLite 保存模型中心、min/max 和时间，以 metric UUID 和 after 等索引；载入时按约 `模型数 × 训练间隔` 的时间范围与数量限制获取模型。数据库有按维度清理及 7 天全局批次清理，推理循环本身未见逐模型实时过期判断，不能宣称“超过 7 天即绝不参与评分”。——[载入与持久化](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L328-L583)、[模型安装和轮转](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L940-L1017)
- 训练读取与计算在后台进行，发布模型时核对 host 状态、generation、下游模型所有权等条件，避免 stop/reset 后迟到的旧任务发布结果。工作队列按预算节奏调度，处理时间可能推迟训练；子节点模型流入父节点后可避免重复本地训练。——[训练状态与发布检查](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L859-L1129)、[队列](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_queue.cc)、[工作线程节奏](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L1750-L1900)
- 默认抑制参数是 900 次窗口和其中 450 次异常，满足条件后进入 silenced。它是实现内部样本计数，不能在采样间隔变化后直接称“15 分钟/7.5 分钟”。单指标布尔异常再进入 chart/host 聚合；检测 bit、聚合异常比例与告警规则是不同层次。——[抑制计数](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml.cc#L1240-L1271)、[配置](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_config.cc)、[聚合图表](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ad_charts.cc)

### Inferences
- 全模型共识让任一“正常”模型拥有否决权，通常趋向减少误报，同时可能降低召回、延后发现。若故障长期混入再训练，新模型可能把故障模式作为正常而否决旧模型；不能只展示“降低误报”的单面优势。
- 我们建议显式区分 healthy/anomalous/unknown，unknown 原因至少包括 missing、warmup、untrained、degenerate、expired、inference_error。只有有效、足够新且数据质量合格的 normal 证据才可推动恢复。该规则是我们的设计建议，并非 Netdata 原行为。
- 借鉴生成号隔离、候选模型验证后原子发布、有限版本回滚和训练时间记录；对慢性故障应支持冻结学习、排除故障窗口、候选对比。更新不能无条件学习所有最近数据。

### Gaps
- 没有用真实 GPU 故障实验测量共识投票相对单模型的召回损失；也没有证据证明按其默认值配置就适合我们的采样周期和负载阶段。

## 3. dlib 与许可证方面怎样借鉴？

### Takeaway
dlib 是通用 C++ 算法库，Netdata 的特征、训练调度和评分逻辑是应用层实现；使用 dlib 不会自动获得 Netdata 流程或动态基线。借鉴设计与直接复制 Netdata 代码的许可证边界不同。

### Cited Findings
- dlib 核心采用 Boost Software License 1.0，**不是 BSD**；其官方 ML 文档提供 `find_clusters_using_kmeans` 等接口。具体分发仍应核对所用版本及附带第三方代码。——[dlib 许可证](https://dlib.net/license.html)、[官方聚类 API](https://dlib.net/ml.html#find_clusters_using_kmeans)
- 固定提交的 Netdata ML 源文件明确标注 `SPDX-License-Identifier: GPL-3.0-or-later`，仓库 LICENSE 为 GPLv3 文本；不能把 dlib 的宽松许可证当成复制整个 Netdata ML 实现的许可。——[ML 文件 SPDX](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/src/ml/ml_kmeans.cc#L1)、[仓库 LICENSE](https://github.com/netdata/netdata/blob/5ddadd98e40e597a205cba6e2835693becefabce/LICENSE)

### Inferences
- 我们 Python 远程模型服务的首轮实验，可以根据公开算法原理自行实现差分/平滑/lag 和两个中心的评分，复用现有 Python 栈；不必为了 K-means 引入 dlib 的 C++ 构建链。若将来性能实测证明需要 C++，再评估 dlib 原生接入。
- 若采用“Netdata 类异常检测”应取独立模型标识，说明其输出为异常分数/状态，不冒称原版兼容或已调好的 GPU 模型。直接复制/链接 Netdata 源码、商业交付和分发方式需单独审查许可证义务；这里不是法律结论。

### Gaps
- 未完成本项目依赖许可清单审查及具体分发方案法律评估；未跑 dlib 与 Python 实现的数值一致性或 CPU/内存基准。
