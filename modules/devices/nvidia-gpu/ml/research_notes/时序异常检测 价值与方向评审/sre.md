# SRE生产告警与GPU异常检测的价值边界

核验日期2026-11-12。仅阅读官方SRE文档、厂家/框架文档和作者原始论文；未改动在线系统。下列“推论”是对本项目的工程建议，不是上游已验证的GPU方案。

## 1. SRE需要的是统计异常还是可行动问题

### Takeaway
用户关于外部因素缺失的担忧有扎实实践依据；但“没有bug特征所以不能发现CPU异常”将发现症状与识别原因混淆。生产告警还需要判断影响与处置，而不能把罕见值直接视为事故。

### Cited Findings
- Google SRE《Monitoring Distributed Systems》区分“什么坏了”（症状）与“为什么”（原因），列举慢响应可源自CPU过载或网络问题；强调pager关键路径简单稳健、主要面向症状/即将发生的真实问题，并把原因启发式用于排障。该章确有对学习阈值/自动因果“魔法系统”的明确谨慎态度，但这是该章的设计主张，不代表所有Google业务从未用ML。— [Google SRE原文](https://sre.google/sre-book/monitoring-distributed-systems/)
- Google SRE Workbook将告警策略的评价放在“重要事件”的precision、recall、detection time、reset time；按错误预算消耗速度区分页与工单，而非按指标数值是否罕见决定严重度。低流量时即使错误比例很高，也可能因事件数少而误导。— [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- Azure Anomaly Detector限制说明明确指出，服务仅输入时间戳与数值，不知数据周围上下文；客户在触发自动动作前应使用真实数据评价适用性、精确率/召回等，不能假定模型100%准确。— [Microsoft官方限制](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/anomaly-detector/characteristics-and-limitations)

### Inferences
- “异常形状”“不符合当前运行条件”“影响服务/作业”“根因”应是四个不同输出层级。CPU bug可留下异常形状，模型无需看到bug源码就能标出该形状；但若正常新增流量与bug产生相同观测，单看CPU无法区分，静态CPU阈值也无法区分。
- 业务请求SLO不能机械套在批处理GPU训练上；应先定义训练服务承诺和有效产出指标（作业完成、step耗时/吞吐、卡时浪费等），再决定什么值得立即打扰值班者。
- 面向症状不等于所有告警必须等SLO已经恶化：明确、可信、可行动的迫近风险也可独立告警，Google原文同时提到imminent real problems。不能把“有业务影响才page”机械实现为必须观察到吞吐下降才允许任何重要风险告警。
- 不应宣称“模型不会根因所以无用”，也不应把统计检测器包装成根因或风险判定器。定位线索对排障可能有用，但其收益也需验证。

### Gaps
- 未发现我们现场故障集、SLO、告警预算、值班处置成本的实证；不能给出“ML一定优于规则”或某个默认误报率/窗口即生产合格的结论。

## 2. GPU监控最需要补什么上下文

### Takeaway
优先从硬件曲线异常转向作业产出、阶段和可比较实体；GPU利用率并不是有效训练工作量，也不能直接指认故障卡。

### Cited Findings
- NVIDIA说明DCGM profiling指标是区间平均，适合比较应用阶段/副本；并非kernel trace，不能指明源码行、kernel或指令。建议先用DCGM找到低利用/不均衡设备，必要时用Nsight做应用级归因。高SM活动本身不证明计算有效，应结合吞吐理解。— [NVIDIA DCGM Profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)
- Meta SPDL官方例子说明，一个rank明显更慢会让其他rank在NCCL all_reduce等待；原因可能是硬件，也可能是dataloader慢，慢rank还可能随epoch改变。— [Meta SPDL Straggler](https://facebookresearch.github.io/spdl/latest/optimization_guide/straggler.html)
- NVIDIA DCGM支持按OS进程或调用者定义的调度作业汇总活动，但需预先采集/保留所需字段；该功能不是持久计费/作业数据库，需要持久化或跨节点关联时应导出结果。— [Process and Job Statistics](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/process-and-job-statistics.html)

### Inferences
- 增加关联键：GPU UUID→node/pod/process→job/run→rank及parallelism role；记录模型/数据配置、batch大小、功率限制、软件版本、训练/评估/检查点/数据准备阶段。上下文可来自调度器、训练埋点、部署事件；这些不是单靠Prometheus指标自动推导出的事实。
- 优先评价step time、tokens/s或samples/s等有用产出，再联合计算、通信、dataloader等待和资源曲线形成证据；tokens/s、samples/s须按实际工作负载选择，不能混用不同模型、序列长度和batch。
- 对比同一作业、可比rank角色/阶段/硬件配置的同伴，而非把所有同型号GPU混成一个正常群体；pipeline/tensor/data parallel角色本来可能不同。证据优先表示“该rank/作业行为偏离，需排查”，不能直接表示“这张GPU坏了”。
- 同伴基线能找相对慢卡，但若所有节点共同受到存储/网络问题影响，相对差异可很小；必须同时保留绝对产出目标和作业自身历史，不可只做peer-outlier。
- 归一化功耗/吞吐有助比较，但可能在故障时将两个共同变化量相除而掩盖问题。应保留原始量及单独证据、明确模型输入可能是原因也可能是后果，避免把故障导致的负载下降解释成“负载低所以正常”。

### Gaps
- 现场是否可采训练阶段、每rank step时间、吞吐及调度映射尚未知。补充上下文仍可能遗漏重要因素，不会因此获得因果识别保证。

## 3. 混合方案怎样验证增量价值而非叠加告警

### Takeaway
规则与ML可在检测证据层并存，但不能简单OR成一堆page，也不能统一AND作为所有重要告警的否决门。保留ML应取决于真实新增检出、提前量或人工成本收益。

### Cited Findings
- Microsoft KDD2019原始论文描述其时序检测服务在业务KPI上使用；报告Outlook反垃圾团队覆盖更多地域、相较原有规则收到更少误报，同时明确单条异常不足以诊断，需要关联多条时序并由人调查。其部署流程包括离线实验、在线试验及人工标注；这些是作者特定场景经验，不是我们GPU上的效果证明。— [原始论文HTML，第2.2/2.3/3节](https://arxiv.org/html/1906.03821v1)
- 告警的价值评价应考虑重要事件检出、延迟和解除时间，而不只指标点级准确度；是否page与需要多快响应有关。— [Google SRE Workbook](https://sre.google/workbook/alerting-on-slos/)

### Inferences
- 混合系统可分为：(a)已有明确意义、独立可靠的告警路径；(b)ML新增行为证据、异常排名和调查线索，初期只影子/工单；(c)告警处理层按影响、置信证据、持续性、已知变更、owner和runbook决定page。不是所有异常都需要任何通知。
- `rule OR ML`在相同对象上扩大触发集合，通常增加召回也增加噪声；`rule AND ML`只保留交集，可能让ML/缺数/训练污染压掉重要告警。两者可用于经过验证的具体策略，但不能全局套用。该判断是集合关系与风险分析，不是引用某家产品设计。
- 定义基线实验：冻结当前规则/简单阈值/滚动稳健统计；同源、同时间、同延迟与告警预算下比较ML。按独立事故/作业异常计数，禁止用一个长事故的数千异常点冒充数千成功检出。
- 报告规则已检出的重叠事件、仅ML检出的事件、仅规则检出的事件、各自漏报、确认时间、假page/设备天或作业天、人工复核分钟、训练/查询维护成本。给出真实现场可接受预算后再判断上线。
- 用部署/负载切换/检查点/空闲作为明确正常反例；使用真实事故、可控故障注入、跨天跨作业留出验证。合成尖峰只能证明链路和某类形状检出，不能证明事故发现价值。
- ML若只重复已知阈值告警，或新增噪声/维护成本大于收益，应缩减到探索/可视化层，甚至删除该检测器；不因已经实现而保留。

### Gaps
- 没有足够证据量化我们项目当前ML的净收益；也没有足够资料把微软2019报告外推到GPU物理故障判定或当前所有在线服务。
