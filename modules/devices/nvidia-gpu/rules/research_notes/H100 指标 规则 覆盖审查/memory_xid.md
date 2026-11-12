# H100内存可靠性与XID覆盖审查

## 内存可靠性应该覆盖什么，现有草案缺什么？

### Takeaway

当前正式目录只有volatile DBE总计数及“近期新增”草案，不能算作完整H100内存可靠性覆盖。需要分别审查DRAM/SRAM、易失/累计、纠正/不可纠正、行重映射故障及资源状态；目前仍没有逐H100形态、软件栈和实际Exporter输入的验证。

### Cited Findings

- NVIDIA内存错误管理支持矩阵明确列出GH100支持error containment、row remapping、dynamic page offlining；这是架构功能证据，不能单独推出H100 PCIe/SXM/NVL每个DCGM字段均可用。RAS Repair – GPU Memory一行只在GB10x列标记，不应转写为H100能力。页面滚动更新，2026-11-04更新，2026-11-06核对。— [Supported GPUs](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/supported-gpus.html)
- 候选字段的精确清单：ECC模式300/301；volatile SBE/DBE总计数310/311；aggregate SBE/DBE总计数312/313；device-memory明细318/319和328/329；SRAM明细342–345；SRAM超阈值布尔346。最新页346名称为`DCGM_FI_DEV_SRAM_EXCEEDED`。这些是字段定义，不是某个H100现场支持证明。— [DCGM Field Identifiers，ECC及SRAM段](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html)
- 行重映射候选：资源桶385–389；uncorrectable/correctable重映射总数393/394；failed395；pending396。最新页分别为`DCGM_FI_DEV_BANK_REMAP_AVAIL_{MAX,HIGH,PARTIAL,LOW,NONE}`、`DCGM_FI_DEV_ROW_REMAP_UNCORRECTABLE_TOTAL`、`DCGM_FI_DEV_ROW_REMAP_CORRECTABLE_TOTAL`、`DCGM_FI_DEV_ROW_REMAP_FAILED`、`DCGM_FI_DEV_ROW_REMAP_PENDING`。— [DCGM Field Identifiers，385–396段](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html)
- 固定Exporter CSV提交`fafd151148052628061a80450b4ee037a5fa0c3c`中，四个ECC总计数字段均被注释，类型标counter；启用的重映射字段仍使用`DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS`、`DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS`和`DCGM_FI_DEV_ROW_REMAP_FAILURE`等旧命名。默认示例文件有字段不代表现场已采集，更不能把latest宏名直接当作Exporter指标名。— [固定Exporter CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- 官方用户可见统计区分InfoROM记录的remapped rows、pending、failure以及bucketized counts；统计数不是“当前硬件中已经完成重映射的行数”。— [User Visible Statistics](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/user-visible-statistics.html)
- 官方SRAM RMA判据涉及bank级unique UCE以及parity/SECDED区别，并明确以Field Diagnostic判定是否满足RMA。它没有给出“volatile DBE总计数大于某值就更换H100”的等价规则，不能把bank级判据套到总计数。— [SRAM Uncorrectable Errors](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/sram-uncorrectable-errors.html)

### Inferences

以下是审查建议和当前仓库比对结论，不是声称官方提供了这些完整PromQL：

| 优先级 | 需要补足的目标 | 输入候选 | 当前缺口 |
| --- | --- | --- | --- |
| P0 | ECC模式/字段能力与有效性 | 字段300/301、字段可用状态、真实样本 | 现有样例只把ECC启用列为前提，没有建立可验证能力链 |
| P1 | 不可纠正错误新增与既往状态 | 311/313及可用位置明细 | 仅311新增草案；首次发现已有非零、aggregate及位置解释未覆盖 |
| P1 | SRAM明确超阈值状态 | 字段346，按版本映射 | 尚无指标卡/规则卡；不能由311推断 |
| P1 | 行重映射失败 | 字段395及实际Exporter映射 | 尚无正式卡；模拟器虽输出failure，实验六规则也没有对应告警 |
| P1 | 行重映射pending/待维护 | 字段396，设备维护上下文 | 尚无指标卡和维护状态规则；pending不等于全部作业必须立刻中断 |
| P1/P2 | 重映射资源退化与历史活动 | 393/394和385–389 | 尚无资源桶及计数语义卡，不应只看累计总数 |
| P2 | 高纠正错误活动 | 310/312或对应DRAM/SRAM明细 | 尚无H100判据，先记录诊断信号，不能虚构统一SBE阈值 |

应先确定“需要识别的内存状态”，再为每一状态记录可用字段、版本及处置；不需要把所有位置计数字段都重复做成独立呼叫告警。

### Gaps

- 没有真实H100型号形态、驱动/DCGM/Exporter版本、MIG状态和`/metrics`样本，无法证明上述每个候选在目标环境可用。必须保持unknown，不能将字段目录当支持白名单。
- DCGM“latest”和3.1文档、固定Exporter CSV存在名称/版本差异；需要锁定目标release建立字段ID→宏名→Exporter名映射。当前记录精确ID和观察到的名字，不宣称完成跨版本别名验证。
- SRAM阈值标志如何在目标H100软件栈导出、是否支持更细分DRAM/SRAM及unique错误统计未核实；在此之前不应自行重建官方RMA算法。

## XID应该怎样枚举，哪些内容已有明确H100证据？

### Takeaway

官方新版XID目录提供明确的“Applies to H100”列，应按该列逐码建立分类台账，而不是仅收集几个常见码。2026-11-06下载的滚动页面中有172个XID代码行、78行明确H100=YES；这是待审查代码分母，不是78条都应呼叫告警。

### Cited Findings

- 当前官方目录针对Ampere及更新GPU，并逐码给出H100适用性、即时处置、调查处置、XID154关联及触发条件。78/172是按HTML Table 1实际枚举的本次计算结果；方法、代码清单及源页面SHA256保存在同目录`h100_xid_enumeration.json`。页面标记2026-11-04更新，属于rolling snapshot，无已确认固定release。— [XID Catalog](https://docs.nvidia.com/deploy/xid-errors/latest/analyzing-xid-catalog.html)
- 在本次目录中H100=YES的关键内存/恢复代码包括48、63/64、92、94/95、154、156/157、171/172。其中63偏记录事件，64为重映射失败；94/95区分contained/uncontained；154提供恢复动作变化；171/172补充DRAM/SRAM区别。目录中的160对H100=NO。— [XID Catalog，H100列及相应代码行](https://docs.nvidia.com/deploy/xid-errors/latest/analyzing-xid-catalog.html)
- 固定Exporter配置中的`DCGM_FI_DEV_XID_ERRORS`是最近XID值的gauge，不是事件次数；不能对这个码值使用increase来统计发生次数。新版配置另外列出`DCGM_EXP_XID_ERRORS_COUNT`、`DCGM_EXP_XID_ERRORS_TOTAL`等注释字段，但不证明现场版本具有或启用了它们。— [固定Exporter CSV，Errors and violations](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)
- 旧GPU Debug Guidelines表仍在94/95描述中出现“A100 only”，而新版目录明确H100=YES；应优先逐码采用新版H100适用列，同时保留驱动版本条件与处置差异，不能直接迁移旧表的A100动作。— [旧排障表](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html)；对照[新版目录](https://docs.nvidia.com/deploy/xid-errors/latest/analyzing-xid-catalog.html)

### Inferences

- 当前正式目录没有H100 XID规则卡，六条实验规则仅测试79码等值状态；不能把它记为“覆盖全部H100 XID”。
- 应对78个H100=YES代码逐项给出disposition：紧急告警/维护或警告/关联上下文/信息忽略/当前采集无法判断；每项都有官方原文定位及排除理由。不能用“78个代码→78条独立critical规则”的办法衡量全面性。
- 稀疏轮询最近码值可能遗漏两次scrape之间的事件，并丢失相邻XID、subcode、进程和错误位置上下文。只读现有Prometheus的边界下，应显式标注“事件完整性不可保证”，而不是声称改PromQL即可补齐。
- 171/172和154可成为补充语义入口，但是否在目标驱动出现、是否被现有Exporter保存必须核实；不能从最新目录逆推旧版本具有同样事件。

### Gaps

- 尚未逐一为78个代码审定优先级和告警动作。本次给出可复核分母与重点缺口，不宣称已经完成完整处置台账。
- XID当前值本身不足以关联“48后跟63/64”“某次错误导致154动作”等有序事件，需要日志/事件流，或经验证具有足够语义的额外遥测；现有采集没有证明提供这些输入。
- 全量目录页面引用了下载表，但本次没有读取XLSX或断言其内部revision；只使用HTML页面及快照哈希。

## 只读现有Prometheus能覆盖到哪里，全面性应怎样验收？

### Takeaway

必须把可观测范围与希望覆盖的故障范围分开。官方NVML字段或诊断工具存在，不等于已有DCGM Exporter和Prometheus已经提供该输入；没有输入的目标保留在缺口账本，不能删除后再宣称覆盖100%。

### Cited Findings

- 官方恢复说明列出None、Reset、Reboot、Drain P2P、Drain and Reset等动作语义，pending及failure也单独说明；该页面还注明相关client flags当前经SMBPBI暴露。不能依据这篇说明直接假设已有Prometheus具有这些状态。— [Error Recovery and Response Flags](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/latest/error-recovery-and-response-flags.html)
- NVML字段目录存在`NVML_FI_DEV_GET_GPU_RECOVERY_ACTION`，旧`NVML_FI_DEV_RESET_STATUS`及`NVML_FI_DEV_DRAIN_AND_RESET_STATUS`标为deprecated。NVML API存在仍需再核实DCGM/Exporter/现场路径。— [NVML Field Value Enums](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlFieldValueEnums.html)
- 官方排障流程涉及日志、Fabric Manager日志、DCGM Diagnostics及Field Diagnostics；Field Diagnostics用于判定GPU健康和RMA，不是仅靠被动阈值替代的行为。— [GPU Node Triage](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html)
- DCGM release notes持续新增/修改健康监测、字段及诊断能力。latest定义不能直接套到未提供版本的现场栈。— [DCGM Release Notes](https://docs.nvidia.com/datacenter/dcgm/latest/release-notes/changelog.html)

### Inferences

内存/XID领域建议采用四段可追溯链：**官方故障/状态条目→H100明确适用性→现场可用输入→规则与测试证据**。逐项至少记录：源版本、适用型号形态/模式、获取路径、字段及单位/类型、当前采集有无、异常/恢复/无效输入测试、事件上下文限制和处置。

发布时不能只有规则数量，应检查：

1. 所有H100适用的官方内存状态和XID目录行都有归档结论（包含明确不告警与无法采集的项）；未知不能混入不适用。
2. 所有选择启用的规则都能追溯到有效输入与具体测试；样例的18用例只能证明那一个表达式。
3. 现场采集对缺失、NaN/Inf、sentinel、重置、设备身份、重复序列与采样间隙有明确契约，避免“无输入=健康”。
4. 硬件诊断/RMA、日志有序上下文以及无法从Prometheus观察的事件，明确作为剩余风险披露。

这只能保障“对既定来源版本和已确认观测边界逐项审查”，不能保证所有未知GPU故障均可检测，也不能在没有现场H100时声称硬件验收完成。

### Gaps

- 第一本全面性账本尚未建完；当前应先承认覆盖不足，再把上述逐项台账、版本锁定和现场输入核验列入第一版退出条件。
- 现场数据完全缺失，无法给出可信的H100生产有效覆盖百分比；以规则数量、字段总数或78个代码直接计算“故障覆盖率”会误导。
