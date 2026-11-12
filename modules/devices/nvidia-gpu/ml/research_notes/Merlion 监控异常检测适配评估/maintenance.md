# Salesforce Merlion 维护 版本与部署条件

核验日期：2026-11-12；仅静态读取官方源码、文档、PyPI及GitHub API，未安装依赖、未更改现有系统。

## 当前是否仍受上游维护

### Takeaway
官方已明确归档，不应把它作为仍由Salesforce持续维护的产品选型。采用它可以，但需要团队承担fork、依赖升级、安全修复和兼容性回归。

### Cited Findings
- GitHub主页面直接显示归档日期2026-03-11，仓库read-only；这是官方归档事实，不是根据长期未发版推断停止维护。[官方仓库](https://github.com/salesforce/Merlion)
- 归档声明明确表示不再actively maintained，也不接受contributions或PR。[CONTRIBUTING-ARCHIVED.md](https://github.com/salesforce/Merlion/blob/main/CONTRIBUTING-ARCHIVED.md)
- 直接读取官方API得到archived=true、pushed_at=2026-03-11T12:52:32Z；updated_at=2026-11-10T07:11:33Z不能解读为有新代码。[GitHub repository API](https://api.github.com/repos/salesforce/Merlion)
- API最近3条提交：39507642dc3d7b8d04232e34e9f36b372cf4912d，2026-03-11T12:52:31Z，message为Add files via upload；上一条085ef8a69e5dcdfb9dcaa394cc21e087cccbb8f0在2024-06-20修复NAB loader；再上一条032ae63d4f1b2609553515d6cecb3e3c569e64c5在2024-06-20添加sklearn LOF。[官方commits API](https://api.github.com/repos/salesforce/Merlion/commits?per_page=3)
- BSD-3-Clause允许按条件再分发修改版本，需保留声明，不能使用Salesforce名称作未经授权背书。[LICENSE](https://github.com/salesforce/Merlion/blob/main/LICENSE)

### Inferences
- 不建议将“Salesforce出品”解释为今天仍有维护保障。若用户希望完整长期生产底座，归档状态是关键否决/降级因素；作为隔离的可替换算法worker或离线基准候选仍有价值。
- 本轮未筛选社区fork，不能宣称有已验证的活跃继任版本。

### Gaps
- 未做完整漏洞审计、供应链审计或支持承诺核实；归档后官方不再维护的结论由其明确声明支持。

## 最新版本及与当前环境的兼容性

### Takeaway
必须区分PyPI包版本、GitHub latest release和main setup.py。PyPI当前最新是2.0.4，发布时间2024-06-20；其numpy<2.0要求与现有系统numpy2.2.3直接冲突，不应原地pip安装替换。

### Cited Findings
- 直接读取PyPI JSON得到info.version=2.0.4，wheel上传2024-06-20T22:50:47.071861Z、sdist为2024-06-20T22:50:49.109102Z，requires_python>=3.7.0。[PyPI JSON元数据](https://pypi.org/pypi/salesforce-merlion/json)、[PyPI项目](https://pypi.org/project/salesforce-merlion/)
- GitHub latest release API返回v2.0.2，published_at=2023-02-15T17:00:00Z；这不等于最新PyPI包。[官方release API](https://api.github.com/repos/salesforce/Merlion/releases/latest)、[v2.0.2发布页](https://github.com/salesforce/Merlion/releases/tag/v2.0.2)
- main/setup.py仍声明version=2.0.2，numpy>=1.21,<2.0，scikit-learn>=0.22，pandas>=1.1.0，scipy>=1.6.0，statsmodels>=0.12.2；基础安装还依赖prophet>=1.1、lightgbm、py4j等。PyPI2.0.4 JSON的核心约束一致。[setup.py](https://github.com/salesforce/Merlion/blob/main/setup.py)、[PyPI JSON](https://pypi.org/pypi/salesforce-merlion/json)
- dashboard、spark、deep-learning为可选依赖组；部分算法还有OpenMP/JDK要求，不是所有算法都需要Java。[官方安装说明](https://github.com/salesforce/Merlion#installation)

### Inferences
- 当前系统numpy2.2.3与官方依赖声明明确不兼容；scikit-learn1.6.1虽满足>=0.22，但宽泛声明不证明运行测试通过；FastAPI0.115.12不在其依赖声明中，不能凭本次资料断定冲突或兼容。
- 推荐单独容器/虚拟环境锁定依赖，通过清晰JSON/Arrow等数据接口接入，避免降级现有服务依赖。Python>=3.7只是元数据下限，不等于Python最新版本或所有依赖组合已验证。

### Gaps
- 未执行安装、import或真实算法测试，因此不能给出可运行锁文件、内存、延迟、吞吐数据。也不能把main、文档v2.0.2与PyPI2.0.4默认为逐字相同源码。

## Dashboard Spark和保存加载是否构成完整生产系统

### Takeaway
有实际可用的实验界面、模型持久化、并行训练/推理工具；但这些不等于一套已经接入Prometheus、具备在线调度和HA的完整监控ML平台。

### Cited Findings
- 官方Dashboard是Dash app，默认8050，以CSV上传/选择特征、训练测试、阈值调参为核心；数据放~/merlion/data，模型~/merlion/models，提供模型下载。[Dashboard文档v2.0.2](https://opensource.salesforce.com/Merlion/v2.0.2/merlion.dashboard.html)
- 基类save/load保存config.json和model.pkl，默认使用dill；也有to_bytes/from_bytes。它是制品序列化接口，而不是完整registry。[模型基类源码](https://github.com/salesforce/Merlion/blob/main/merlion/models/base.py)
- PySpark API可将多个时序分组并行训练和推理，提供spark-submit、Docker和spark-on-k8s配置；文档样例从CSV数据集读取，需用户自行配置集群。[Spark文档v2.0.2](https://opensource.salesforce.com/Merlion/v2.0.2/merlion.spark.html)
- Spark anomaly UDF输出index_cols、time_col和anom_score；这个接口证明按时序并行计算，不是自动把监控告警送到夜莺的接口。[Spark API](https://opensource.salesforce.com/Merlion/v2.0.2/merlion.spark.html#merlion.spark.pandas_udf.anomaly)

### Inferences
- 仍需保留/建设：Prometheus时间和标签适配、源质量、增量水位/缺口处理、在线worker与调度、模型注册/审核/影子/回滚、权限和审计、结果时序存储、夜莺接入及容量/故障验证。
- 保存加载使用dill意味着只加载可信自生成且摘要校验制品；不能向用户开放任意pickle/dill上传作为“自定义模型”。
- 可以用其算法统一接口替换目前自研检测器实现的一部分，不适合把Dashboard直接当生产监控Web，或把Spark示例当现成高可用在线服务。

### Gaps
- 在所核验官方资料中未找到开箱即用Prometheus/Nightingale connector、模型生命周期审批registry或完整HA在线服务承诺；这是本次检查范围内“未找到”，不是对整个代码库经过穷尽搜索后证明绝对不存在。
