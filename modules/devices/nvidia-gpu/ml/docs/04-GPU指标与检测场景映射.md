> v4范围更新：当前仅有DCGM，没有上层作业信息；以[场景清单](10-DCGM场景清单与数据契约.md)、[当前方案](02-技术方案.md)和[v4验收](11-v4实施与验收.md)为准。

> v3更新：当前以[流水线技术方案](02-技术方案.md)和[v3验收](09-v3流水线实施与验收.md)为准；旧三段切分、算法清单和历史验收不覆盖本轮。

> 2026-11-12更新：检测架构以[v2技术方案](02-技术方案.md)及[v2实施记录](08-v2实施与验证.md)为准。本文旧三模板描述与v1验收仅作历史，不代表v2准入。

# GPU指标与检测场景映射

版本：0.1  
日期：2026-11-11  
状态：基于既有台账的实现候选，不是现场采集准入结果  
关联：[需求](01-需求文档.md)、[技术方案](02-技术方案.md)、[项目计划](03-项目计划.md)

## 1. 来源与解释方式

本文件从现有[92项候选指标台账](../../common/monitoring/catalog/metric-inventory.yaml)选取与新模块有关的输入，不另造GPU指标定义。第一版范围和条件沿用[H100训练基线](../../common/monitoring/hardware/H100训练基线.md)，实际栈和采集仍待核实。42项综合模拟输入见[综合候选库](../../rules/monitoring/h100-training/catalog.yaml)，它不包含全部ML连续特征，也不证明现场具备同样数据。

下表字段来自旧台账的规范ID、候选类型/单位和参考CSV映射。参考字段不是实际数据源承诺；即使在参考CSV启用，也不能认定现有集群已采集。没有CSV映射的字段需根据现场版本单独绑定，禁止按名字猜测。

具体绑定须记录：source_id、cluster_id、metric_id、实际指标/查询、实体标签、采样、单位转换、sentinel和值域、源时间、软件条件、验证状态及证据。

## 2. 输入候选

### 首期连续遥测与条件输入

| 规范metric_id | 名称 | 台账类型 / 单位 | 参考CSV字段 |
|---|---|---|---|
| `nvidia.gpu_temp` | GPU温度 | gauge / celsius | `DCGM_FI_DEV_GPU_TEMP` |
| `nvidia.memory_temp` | HBM/显存温度 | gauge / celsius | `DCGM_FI_DEV_MEMORY_TEMP` |
| `nvidia.gpu_max_temp` | GPU最大运行温度门槛 | gauge / celsius | 无已登记CSV映射，现场核实 |
| `nvidia.memory_max_temp` | 显存最大运行温度门槛 | gauge / celsius | 无已登记CSV映射，现场核实 |
| `nvidia.gpu_temp_margin` | GPU热余量 | gauge / celsius | 无已登记CSV映射，现场核实 |
| `nvidia.board_power` | 板卡功耗 | gauge / watts | `DCGM_FI_DEV_POWER_USAGE` |
| `nvidia.requested_power_limit` | 请求的功率限制 | gauge / watts | `DCGM_FI_DEV_POWER_MGMT_LIMIT` |
| `nvidia.enforced_power_limit` | 实际执行的功率限制 | gauge / watts | `DCGM_FI_DEV_ENFORCED_POWER_LIMIT` |
| `nvidia.sm_clock` | SM时钟 | gauge / MHz | `DCGM_FI_DEV_SM_CLOCK` |
| `nvidia.mem_clock` | 显存时钟 | gauge / MHz | `DCGM_FI_DEV_MEM_CLOCK` |
| `nvidia.gpu_util` | GPU利用率 | gauge / percent | `DCGM_FI_DEV_GPU_UTIL` |
| `nvidia.mem_copy_util` | 显存控制器利用率 | gauge / percent | `DCGM_FI_DEV_MEM_COPY_UTIL` |
| `nvidia.fb_used` | 显存已用容量 | gauge / MiB | `DCGM_FI_DEV_FB_USED` |
| `nvidia.fb_free` | 显存剩余容量 | gauge / MiB | `DCGM_FI_DEV_FB_FREE` |

### 条件增强与后续输入

| 规范metric_id | 名称 | 台账类型 / 单位 | 参考CSV字段 |
|---|---|---|---|
| `nvidia.gr_engine_ratio` | 图形/计算引擎活动比率 | gauge / ratio | `DCGM_FI_PROF_GR_ENGINE_ACTIVE` |
| `nvidia.sm_active_ratio` | SM活动比率 | gauge / ratio | `DCGM_FI_PROF_SM_ACTIVE` |
| `nvidia.sm_occupancy_ratio` | SM occupancy比率 | gauge / ratio | `DCGM_FI_PROF_SM_OCCUPANCY` |
| `nvidia.tensor_active_ratio` | Tensor管线活动比率 | gauge / ratio | `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` |
| `nvidia.dram_active_ratio` | DRAM活动比率 | gauge / ratio | `DCGM_FI_PROF_DRAM_ACTIVE` |
| `nvidia.pcie_tx_rate` | Profiling PCIe发送速率 | gauge / bytes_per_second | `DCGM_FI_PROF_PCIE_TX_BYTES` |
| `nvidia.pcie_rx_rate` | Profiling PCIe接收速率 | gauge / bytes_per_second | `DCGM_FI_PROF_PCIE_RX_BYTES` |
| `nvidia.pcie_replay` | PCIe replay累计 | counter / events | `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` |
| `nvidia.nvlink_crc` | Hopper NVLink CRC累计 | counter / errors | `DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL` |
| `nvidia.nvlink_recovery` | Hopper NVLink recovery累计 | counter / events | `DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL` |
| `nvidia.nvlink_replay` | Hopper NVLink replay累计 | counter / events | `DCGM_FI_DEV_NVLINK_REPLAY_TOTAL` |
| `nvidia.thermal_violation_ns` | 热限制累计时长旧字段 | counter / nanoseconds | `DCGM_FI_DEV_THERMAL_VIOLATION` |
| `nvidia.thermal_throttle_seconds` | 热限制累计秒新字段 | counter / seconds | 无已登记CSV映射，现场核实 |

### 保留硬规则及事件上下文

| 规范metric_id | 名称 | 台账类型 / 单位 | 参考CSV字段 |
|---|---|---|---|
| `nvidia.ecc_dbe_volatile_total` | 不可纠正ECC易失总计数 | counter / errors | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` |
| `nvidia.sram_exceeded` | SRAM超阈值标志 | state / boolean | 无已登记CSV映射，现场核实 |
| `nvidia.remap_failed` | 行重映射失败 | state / boolean | `DCGM_FI_DEV_ROW_REMAP_FAILURE` |
| `nvidia.xid_last` | 最近XID代码 | gauge / error_code | `DCGM_FI_DEV_XID_ERRORS` |
| `nvidia.clock_reasons` | 时钟限制原因 | bitmask / bitmask | 无已登记CSV映射，现场核实 |
| `nvidia.pcie_gen` | PCIe当前链路代际 | gauge / generation | 无已登记CSV映射，现场核实 |
| `nvidia.pcie_width` | PCIe当前链路宽度 | gauge / lanes | 无已登记CSV映射，现场核实 |
| `nvidia.fm_status` | Fabric Manager状态 | enum / enum | 无已登记CSV映射，现场核实 |
| `nvidia.switch_link_state` | NVSwitch端口状态 | enum / enum | 无已登记CSV映射，现场核实 |

## 3. 检测场景与输入约束

| 场景 | 必需输入 | 可选增强 | 检测方法与上线条件 |
|---|---|---|---|
| GPU-ML-01 GPU温度偏离 | 唯一新鲜GPU温度、稳定UUID、足够可用历史 | 功耗、利用率、设备运行门槛、训练阶段 | 稳健/条件基线与残差森林；无负载时只称自身历史温度偏离；无门槛不计算热余量 |
| GPU-ML-01 HBM温度偏离 | 唯一新鲜HBM温度与历史 | HBM门槛、显存控制器活动/使用量、功耗 | 单独训练与校准；字段不支持时不借GPU温度代替HBM |
| GPU-ML-02 功耗时钟关系 | 有效功耗、SM时钟、GPU利用率，同实体同时间口径 | 功率上限、显存时钟、温度、限制原因 | 条件基线和联合/单指标森林；不同限功率/工况不能随意混训 |
| GPU-ML-03 活动模式变化 | GPU利用率和历史 | 显存控制器活动、显存容量、作业阶段 | 后向趋势、变化或残差；没有作业上下文时不标为训练失败 |
| GPU-ML-04 同组偏离 | 显式可比组、同一指标、有效同刻成员数量 | 作业分配与同步阶段、相同型号形态及限功率 | 同组稳健偏差；不足成员/不可比时不评分；不直接比较随机卡 |
| GPU-ML-05 稀疏计数趋势 | 计数单位、重置分段与有效时间窗口 | 链路流量、拓扑与负载 | 先统计活动与规则对照，再验证是否需要ML；不直接对长零序列套森林 |

GPU-ML-01包含GPU和HBM两个实例模板，可按支持范围分别启用。GPU-ML-04/05不是首个PoC必需项；缺输入不阻止其他独立任务，但覆盖页面必须显示缺口。

## 4. 规则、ML与上下文分工

- ECC新增、SRAM标志、行重映射失败：保留现有可靠性规则，不等待ML确认；历史ECC非零不能改写为近期新增。
- XID/SXid：按错误码/事件和既有处置目录处理，码值大小不具连续距离语义；原始last-code不能保证捕捉所有事件。
- 温度与热限制：硬门槛、状态位和累计时长分别解释；ML只补充相对工况或历史的偏离。
- 功率/时钟：高功耗和正常限功率不自动等于故障；结合配置和限制原因；位掩码不直接rate。
- PCIe/NVLink/NVSwitch：先核实预期拓扑、字段支持和单位；未使用端口不参与掉线判定，交换机实体不复用GPU UUID。
- 训练效率：`training.job_context`属于已有台账中的外部上下文候选，当前未证明可用；没有任务和阶段不能推断完整训练效率。

## 5. 单位与数据质量门禁

| 项目 | 处理要求 |
|---|---|
| GPU_UTIL / MEM_COPY_UTIL | 按实际0～100百分数契约核实；后者不是显存容量占比 |
| PROF_* ratio | 与百分数分别处理；不默认已采集或实际支持 |
| FB_USED / FB_FREE | 参考单位MiB，现场核实；容量占比需明确有效分母和保留口径 |
| GPU/HBM温度与门槛 | 正确对应传感器和运行门槛；shutdown门槛不能直接作预警门槛 |
| THERMAL_VIOLATION | 旧累计ns字段需换算；与新累计秒字段二选一，不相加 |
| PROF_PCIE_*_BYTES | 台账候选为bytes/s，现场确认；不能仅看名称决定Counter/rate |
| ECC与replay等Counter | 先处理重置和缺口；汇总与分域避免重复累加 |
| 无效与缺数 | NaN/Inf/sentinel、重复和过期先拦截；不补零或生成正常证据 |
| 设备身份 | cluster/源范围+UUID；GPU index只作展示；MIG实例不混同物理卡 |
| 支持状态 | available、missing、unverified、unsupported、not_applicable区分；未知拓扑不直接判不适用 |

## 6. GPU模拟与真实绑定策略

本模块模拟数据沿用真实GPU字段语义，包含UUID、单位和SIMULATED来源标记，但使用独立cluster/job与控制端，不修改旧综合模拟器的场景。

温度、功耗、时钟和利用率在正常样本中具备可解释的关联，再注入尖峰、漂移、关系断裂和活动变化；同时提供正常高负载、空闲、阶段切换、采集缺失和重置反例。场景标签只用于评估，不作为模型特征。

真实接入先只读发现与核对，生成绑定差异报告；缺特征时显式停用对应模板，不自动从模拟数据填充。固定样本验收只证明契约与链路，真实H100准入必须独立完成。

## 7. 变更维护

原台账保持为语义事实源；本文件新增或修改候选时需引用原metric_id、对应版本与原因。正式绑定、模型模板和测试在模块config/与tests/实施后建立校验，验证引用存在、必需输入齐全、单位一致、模拟/真实来源不混淆。

新增型号、MIG粒度、Profiling或拓扑能力都需要单独准入，不能通过复制H100模板并改名称获得支持。
