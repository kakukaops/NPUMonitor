# 预训练时序模型的远程动态基线集成

## 一 哪些模型可选及代码与权重许可是否允许部署

### Takeaway

Chronos-Bolt、Chronos-2、Toto 2.0 和 TimesFM 2.5均有可下载的预训练权重，可作为无需逐指标更新权重的候选预测器；仍需环境内的输入契约、残差/区间校准和告警验证。TimesFM 3.0的代码许可不能替代其权重许可：下载、自托管权重受非商业、非生产限制，不作为当前商业自托管候选。

### Cited Findings

核查日期为2026-11-17；以下是当日官方分支、模型卡和源码观察，不是本项目已经安装或验收的模型。

| 候选 | 可核实能力与限制 | 代码与具体权重 | 官方来源 |
|---|---|---|---|
| Chronos-Bolt tiny/mini/small/base | 分别9M/21M/48M/205M；零样本单变量预测、直接多步分位数输出；批处理多条单变量序列不等于联合多变量建模 | 代码Apache-2.0；tiny和small模型卡明确Apache-2.0。其他版本实施前仍固定模型卡/文件revision | [Tiny模型卡](https://huggingface.co/amazon/chronos-bolt-tiny)、[Small模型卡](https://huggingface.co/amazon/chronos-bolt-small)、[仓库](https://github.com/amazon-science/chronos-forecasting) |
| Chronos-2 | 120M；支持单变量、原生多变量、过去/未来协变量；无需针对目标数据微调即可预测；也有可选full/LoRA微调入口 | 代码与amazon/chronos-2模型卡均Apache-2.0 | [模型卡](https://huggingface.co/amazon/chronos-2)、[pipeline源码](https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/src/chronos/chronos2/pipeline.py) |
| Toto 2.0 | 4M、22M、313M、1B、2.5B；零样本、多变量、分位数预测；当前README明确2.0尚未提供微调和外生变量支持，相关需求指向1.0 | 仓库Apache-2.0；Toto-2.0-4m和22m具体模型卡均Apache-2.0 | [README](https://github.com/DataDog/toto)、[4m模型卡](https://huggingface.co/Datadog/Toto-2.0-4m)、[22m模型卡](https://huggingface.co/Datadog/Toto-2.0-22m) |
| TimesFM 2.5 | 200M基础模型；提供点预测与分位数接口。2.5支持单变量批预测，另有XReg协变量增强，不能称为3.0那种原生多变量模型 | 仓库源码Apache-2.0；google/timesfm-2.5-200m-pytorch权重模型卡Apache-2.0 | [2.5模型卡](https://huggingface.co/google/timesfm-2.5-200m-pytorch)、[官方版本说明](https://github.com/google-research/timesfm) |
| TimesFM 3.0 | 官方称原生多变量和协变量预测；自托管权重不适合本期商业部署 | 仓库通用代码声明Apache-2.0，但具体3.0权重另受timesfm-non-commercial-license-v1.0限制；官方Google Cloud服务的商用许可另按云服务条款处理 | [3.0权重LICENSE](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE)、[官方许可区分](https://github.com/google-research/timesfm#license-notice-for-pretrained-weights) |

- Chronos官方对照表给出最大上下文：原Chronos 512、Bolt 2048、Chronos-2 8192；原Chronos和Bolt不原生支持多变量。Chronos-2的跨序列cross_learning是独立功能，其源码predict/predict_df默认False。[模型卡能力表](https://huggingface.co/amazon/chronos-2)、[Chronos-2源码](https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/src/chronos/chronos2/pipeline.py)
- 原Chronos以采样轨迹产生概率预测，Bolt直接生成分位数，因此在本项目单步低延迟候选中可先评估Bolt，不必先复现原Chronos采样路径。[官方家族说明](https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/README.md)
- Toto面向observability，预训练主要使用Datadog内部系统指标和公开数据；官方说明不含客户数据。这是监控领域相关性证据，并非本项目DCGM/GPU故障检出证据。[Toto官方README](https://github.com/DataDog/toto)
- 可追溯版本观察：Toto `toto-2` pyproject版本2.0.0、umbrella `toto-models`版本1.0.0；TimesFM pyproject版本3.0.2；Chronos提交页可见2026-06-15短SHA `f42f647`、Toto可见2026-05-20 `e1bd7f3`、TimesFM可见2026-09-09 `8cb0628`。这些是网页当时可见历史，不保证实时HEAD，也不能把模型名当不可变权重revision。[Toto2包定义](https://raw.githubusercontent.com/DataDog/toto/main/toto2/pyproject.toml)、[umbrella包](https://raw.githubusercontent.com/DataDog/toto/main/toto_models/pyproject.toml)、[TimesFM包定义](https://raw.githubusercontent.com/google-research/timesfm/master/pyproject.toml)、[Chronos提交页](https://github.com/amazon-science/chronos-forecasting/commits/main/)、[Toto提交页](https://github.com/DataDog/toto/commits/main/)、[TimesFM提交页](https://github.com/google-research/timesfm/commits/master/)

### Inferences

- “开源预训练模型”可以减少逐GPU拟合预测器的工作，但不会自动完成异常检测、告警持续确认和恢复；不要把零样本预测宣传成零数据、零配置、零校准的故障检测。
- 建议并列保留轻量自训练对照与预训练影子候选，而不是直接替换已工作的Ridge/MAD。对首批GPU温度、HBM温度、功耗、GPU利用率、显存控制器活动先做单变量，才容易分辨模型能力与输入工况影响。
- TimesFM 3.0可研究其官方托管服务接入，但这已不是“下载开源权重、自己托管”的同一部署路线；不能因其仓库有Apache标记就准许商业自托管。

### Gaps

- 未下载权重、未实际安装这些包、未做GPU/CPU资源实测；未证明任何候选在本项目首批5指标上优于当前模型。
- 未取得每个模型checkpoint的不可变完整SHA。本轮GitHub API commits端点工具访问失败；实施时必须把包版本、代码commit、HF checkpoint revision和权重摘要锁定，保存LICENSE/NOTICE，不依赖main。
- 官方通用/observability基准不包含本项目真实GPU数据、设备工况与告警预算的验证，不能转述成GPU故障准确率。

## 二 能否集成到现有远程模型服务及需要改什么

### Takeaway

可以集成，但应在独立预测服务中加载权重，并增加“预训练预测＋校准＋标准HTTP契约”适配层。现有监控端的多个服务连接、模型描述、试评分、部署引用和预测结果校验可复用；把HF模型名直接填进现有模型选择框不能完成集成。

### Cited Findings

- Chronos模型卡示例是Python的from_pretrained和predict调用；另提供SageMaker或AutoGluon-Cloud部署路径。这是权重加载与部署选项，不是任何模型名天然具备HTTP服务。[Chronos-2模型卡](https://huggingface.co/amazon/chronos-2)、[Bolt部署与CPU示例](https://huggingface.co/amazon/chronos-bolt-small)
- Toto官方示例从HF加载后执行model.to(device).eval()及forecast；4m模型卡明确当前没有通用Inference Provider托管。这不阻止自托管，但需要我们提供服务包装。[Toto-4m模型卡](https://huggingface.co/Datadog/Toto-2.0-4m)
- TimesFM 2.5模型卡示例提供Python forecast接口，并标注没有Inference Provider部署；不能把其HF页面URL当作可调用的预测端点。[TimesFM2.5模型卡](https://huggingface.co/google/timesfm-2.5-200m-pytorch)
- 当前本地ModelServices严格要求entity、source_type、完整feature_schema和逐字段metric_id/unit匹配，拒绝online_update/stateful；接受参考类型none/causal_forecast/joint_reconstruction/conditional_baseline及history_samples≤12000。登记还要求当前有效历史试评分，不会下载权重。[项目源码](</home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/backend/gpu_ml/model_backends/services.py>)
- 当前DetectionPipeline在fit中固定执行preprocessor.fit、detector.fit、独立calibrator.fit；检测器窗口参数仅temporal_mad可设4～60，不能把它直接当成基础模型256/512/2048上下文配置。参考Runtime按model_ref加载/缓存本地制品。[现流水线](</home/mqq/github/zj/NPUMonitor/modules/model-services/runtime/gpu_ml_runtime/pipeline.py>)、[参考运行时](</home/mqq/github/zj/NPUMonitor/modules/model-services/reference-platform/gpu_ml_platform/runtime.py>)

### Inferences

建议接口和生命周期改造如下，属于本项目工程设计，不是上游项目已替我们实现的功能：

1. **隔离服务**：新建预训练预测服务镜像/运行环境，实现现有info/catalog/describe/deployment/predict契约；监控控制面仍只使用HTTP。保留现有轻量参考服务，不把torch/transformers/JAX等全部塞进监控镜像。
2. **模型与部署拆开**：一个只读checkpoint可以服务多GPU/多指标。权重缓存键采用`checkpoint revision＋backend runtime＋device＋precision`，实体部署描述另外保存GPU、指标、单位、采样、上下文、校准版本。现有严格实体登记无需放开安全边界：为每实体建立轻量部署引用即可，底层共享权重。不要按每个model_ref重复在GPU显存加载同一套权重。
3. **增加准备/校准语义**：对预训练模型，准备步骤是下载/校验权重、登记上下文配置、在本环境历史上校准评分，不是重新训练模型权重。UI应分别显示“预训练权重不变”“已完成历史校准”“微调生成新权重”，不要把三者都叫训练。
4. **因果预测与对齐**：评分当前时刻t时只将`x[t-L]…x[t-1]`传给forecast，取horizon=1；实际`x[t]`仅在模型预测之后用于残差/异常评分。现监控协议请求包含当前点并不构成泄漏，关键是服务端必须拆分上下文和待评分目标。回放逐前缀执行，未来值及当前目标不能进入归一化拟合或预测输入。
5. **输出映射**：点预测/中位数映射expected，声明分位数范围映射bounds，分数由残差、区间外距离或其他固定且可校准的非负函数给出，再通过冻结校准器与ThresholdPolicy输出score/threshold/anomaly。q10～q90只是模型的预测分位数带，不能解释为80%故障概率或按GPU每天固定误报预算；必须在独立正常段测实际覆盖和事件率。若最低仅q10～q90，不凭插值就宣称拥有经验证的99.9%尾部区间。
6. **数据质量与范围**：维持不补零、不把合法空闲零判缺失、缺口/重复/陈旧未知等当前语义；上游支持缺失mask并不自动改变我方准入规则。摄氏温度、W、0～100活动率的归一化与反变换要可审计；检查分位数交叉、零宽区间和非有限输出。预测百分数越界时不要暗中裁剪后声称校准覆盖改善。
7. **多变量谨慎扩展**：Chronos-2/Toto支持多变量预测，但“联合预测各指标”并不自动得到联合异常阈值。首批5项单变量分别验收，第二步才设计跨指标相关残差和联合校准。Chronos-2批处理采用cross_learning=False作为起点，避免不同GPU或租户被默认联合学习；共享checkpoint不等于共享数据上下文。
8. **历史与性能预算**：上下文256/512等点数作为待比较配置，不沿用Ridge默认12点，也不盲目采用最大上下文。按当前2秒采样，512点约17分钟；更长上下文要求源保留、query预算与窗口预热满足。批量化与缓存须绑定真实源时间/实体/版本，重复轮询不能推进确认。
9. **版本与资源**：部署记录checkpoint名/revision/hash、包版本、precision/device、上下文、quantile选择、评分公式、校准器、输入单位与采样。OOM、超时、冷启动、版本不匹配和非有限输出都应返回未知，不回退零或“正常”，也不静默切换已加载权重。

### Gaps

- 现有模型服务尚未实现上述基础模型适配、共享权重池或零样本准备状态；本轮是可行性研究，不能把HTTP参考服务测试当成Chronos/Toto/TimesFM已接入。
- 上游不承诺通过我方info/models/deployments JSON协议；必须编写适配器，托管平台的认证/计费/JSON协议也不能通过只替换基础URL自动兼容。
- 通用预测模型的分位数在设备正常负载切换、冷启动和慢热漂移上的覆盖率/延迟需实测；某些模型会快速追随偏移，预测误差小不保证长期漂移检出。

## 三 运行环境资源与建议的验证顺序

### Takeaway

建议首轮比较Chronos-Bolt tiny（或small）与Toto 2.0 4m/22m，当前Ridge作为对照；Chronos-2和TimesFM2.5作为后续能力对照。这个顺序是降低实现/资源不确定性的工程建议，不是尚未执行的效果排名。

### Cited Findings

- 当前Chronos包要求Python≥3.10、torch≥2.2且<3、transformers≥4.41且<6、accelerate≥1.1且<2，以及numpy/einops/pandas；CPU设备可用，但具体吞吐仍依环境而定。[包定义](https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/pyproject.toml)、[CPU示例](https://huggingface.co/amazon/chronos-bolt-tiny)
- Toto2包要求Python≥3.12，当前pyproject声明torch≥2.14.0并依赖gluonts[torch]、dd-unit-scaling、safetensors等；README Requirements却写torch2.5+。这属于依赖声明与文档不一致，实施需选择确定发布版本并锁定可安装依赖，不能只照README混装。[Toto2包定义](https://raw.githubusercontent.com/DataDog/toto/main/toto2/pyproject.toml)、[README Requirements](https://github.com/DataDog/toto#requirements)
- Toto模型卡给出4m约16MB、22m约84MB的FP32权重，并将4m定位于edge/CPU；同表毫秒延迟的测试条件是A100、batch8、1024步预测，不能用作本项目CPU或2秒轮询的延迟保证。完整运行内存还包括框架、激活、缓存和批量输入。[4m模型卡](https://huggingface.co/Datadog/Toto-2.0-4m)
- TimesFM当前包定义Python≥3.10，可选torch、Flax/JAX、XReg环境；基础依赖numpy≥1.26.4、HF Hub和safetensors。2.5与3.0模型的调用入口不同，应固定与checkpoint匹配的版本。[包定义](https://raw.githubusercontent.com/google-research/timesfm/master/pyproject.toml)、[2.5调用示例](https://huggingface.co/google/timesfm-2.5-200m-pytorch)
- 项目当前数值镜像使用numpy2.2.3、scipy1.15.2、sklearn1.6.1和joblib1.4.2；没有预装上述基础模型框架。现有独立平台的Dockerfile也不包含基础模型权重。[本地依赖](</home/mqq/github/zj/NPUMonitor/modules/devices/nvidia-gpu/ml/demo/requirements.txt>)、[平台镜像](</home/mqq/github/zj/NPUMonitor/modules/model-services/reference-platform/Dockerfile>)

### Inferences

推荐两阶段PoC与准入：

- **P0可部署性**：分别制作固定依赖镜像，下载有明确许可的checkpoint到模型服务端；校验签名/摘要，禁止推理热路径联网拉权重；单进程共享已加载checkpoint。测冷启动、CPU/GPU内存、单/批预测p50/p95/p99和队列积压；不能只看参数量选择GPU。
- **P1同源离线比较**：首批5项每项同时间切分、同窗口候选、同标注范围，对比上一值、训练中位数、当前Ridge与2个预训练候选。预测评价用MAE/分位数覆盖与区间宽度；检测评价用正常标注范围事件误报、已标异常检出、确认后延迟、有效评分覆盖和人工处理成本。无标签不报真实召回率。
- **必须覆盖正常反例**：空闲零值、正常高负载、正常阶段/功率切换、不同波动幅度；异常包括尖峰、持续水平偏移、慢热漂移与活动下降；质量反例包括缺口、NaN/sentinel、重复和陈旧。检验基础模型是否快速追随持续异常、导致残差恢复但故障仍存在。
- **P2远程影子**：注册实体绑定部署描述，经真实HTTP、身份/时间/输出校验，在影子模式记录；进行超时/OOM/重启/平台丢身份等故障检查。只有达到现场误报和资源预算才人工切在线，硬温度门槛与错误规则独立。
- 首轮重点是用合理上下文获得稳定的一步预测，不为了展示而启用深度微调。Toto2暂不支持微调和EV时不要把该选项做进UI；Chronos2虽有fine-tune API，也不能在没有收益证据时默认开启。

### Gaps

- 本轮没有GPU领域受控对比实验，没有推理时延或内存实测；不能承诺“某模型更准”“无需GPU”或固定集群容量。
- 时间序列基础模型许可、依赖、模型卡和分支可能变化；未来实施需要再次核对固定release/checkpoint，不以本次main页面作为永久发布准入。
- 当前最大上下文与请求上限虽在数值上可能容纳8192点，不代表生产查询/端到端延迟预算已经通过；还要实测Prometheus每任务窗口查询与多实体批处理能力。
