# H100 行重映射、温度、降频与互联复核

日期为 2026-11-11。范围为 H100 物理卡训练，驱动设计基线沿用 R595.112.07。本批提供 15 条默认禁用的复核查询，现场字段支持、软件版本、MIG 模式和具体硬件形态待核验。

## 输入字段与映射

| 输入 | DCGM 字段 ID | 合成查询名 | 固定 Exporter CSV |
| --- | --- | --- | --- |
| 行重映射 pending | 396 | DCGM_FI_DEV_ROW_REMAP_PENDING | 未列出 |
| GPU 温度 | 150 | DCGM_FI_DEV_GPU_TEMP | 启用 |
| GPU 最大运行温度 | 152 | DCGM_FI_DEV_GPU_MAX_OP_TEMP | 未列出 |
| 显存温度 | 140 | DCGM_FI_DEV_MEMORY_TEMP | 启用 |
| 显存最大运行温度 | 151 | DCGM_FI_DEV_MEM_MAX_OP_TEMP | 未列出 |
| 时钟原因位掩码 | 112 | DCGM_FI_DEV_CLOCKS_EVENT_REASONS | 未列出 |
| 累计热限制时长 | 241 | DCGM_FI_DEV_THERMAL_VIOLATION | 注释，单位 ns |
| PCIe replay 累计 | 202 | DCGM_FI_DEV_PCIE_REPLAY_COUNTER | 启用 |
| Hopper NVLink CRC 累计 | 497 | DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL | 注释 |
| Hopper NVLink recovery 累计 | 498 | DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL | 注释 |
| Hopper NVLink replay 累计 | 499 | DCGM_FI_DEV_NVLINK_REPLAY_TOTAL | 注释 |

表中使用合成查询所需的名字。现场接入须按字段 ID 对照真实采集输出，核对别名、类型和量纲。CSV 中启用项提供配置参考，实际字段存在性需要现场样本支持。逐项来源见[输入台账](../../common/monitoring/metric-inventory.md)。固定依据为 [DCGM header](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h) 和 [Exporter CSV](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)。

## 查询判据与处置

### 行重映射待生效

`memory.remap_pending` 在已登记 GPU 的有效布尔标志为 1 时返回维护复核条件。先收集 ECC、XID、重映射历史及调度状态，再由运维安排维护。持续时间、严重度、维护窗口和标志清除后的处置需要现场确认。资源余量及失败状态分别保留检测目标。

### GPU 与显存运行温度余量

`thermal.gpu_operating_margin` 和 `thermal.memory_operating_margin` 分别计算设备上报的最大运行温度减去当前温度，单位为摄氏度。正值表示尚有余量，零值表示到达该运行门槛，负值表示超过该门槛。

两端输入均须健康、新鲜、唯一，按 cluster_id 与 UUID 配对。温度允许有限负值，门槛须为有限正值。缺失门槛时记录输入缺口。GPU 和 HBM 独立检查，运行门槛、slowdown 门槛和 shutdown 门槛分别维护。预警余量、持续时间和回差仍待现场审定。出现余量不足时，核对设备上报门槛、负载、风扇与进风温度，并结合热限制原因调查。[NVIDIA 温度语义](https://docs.nvidia.com/deploy/nvidia-smi/index.html#temperature)

### 时钟原因与热限制时长

固定 header 中的原因位按下表解码，查询通过 `floor(mask / bit) % 2` 提取每一位。

| 查询尾名 | 位值 | 解释与复核 |
| --- | --- | --- |
| sw_thermal | 32 | 软件热限制，核对 GPU 与显存门槛 |
| hw_thermal | 64 | 硬件热限制，调查散热及负载 |
| sw_power_cap | 4 | 软件功率限制，核对配置预算与训练影响 |
| hw_power_brake | 128 | 外部 power-brake 信号，关联主机供电证据 |
| hw_slowdown | 8 | 通用硬件 slowdown，可能涉及热、功率或状态变化 |
| sync_boost | 16 | 同步 boost 组影响，检查同组设备原因 |

位掩码要求非负整数并处于双精度整数可精确表示的范围。`clock.unknown_bits` 单独暴露超出本次已知位集合的值。未知高位与已知热限制位共存时，已知位仍按数学定义解码。

`thermal.slowdown_seconds` 展示旧 ns 累计字段五分钟新增量除以 1e9 后的秒数。新秒制字段需要单独绑定，现场择一统计。持续性告警参数仍待审定。[固定原因位定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L100)

### PCIe 与 Hopper NVLink

`pcie.replay_increase` 展示五分钟 replay 新增量。NVLink CRC、recovery 和 replay 分别展示五分钟新增量。现场应核对驱动计数口径、重置方式、链路身份与训练拓扑，再决定持续时间和分级。排查时关联 PCIe AER、XID、对端设备及链路历史。

本批使用固定 CSV 的 Hopper 字段 497—499。预期端口掉链还需启用端口、对端和维护清单。PCIe 负载下降级还需预期代际、宽度和作业上下文。NVSwitch/SXid、Fabric Manager 及交换机端口属于独立实体，其采集和规则仍待实现。[互联覆盖目标](coverage.md)

## 输入质量和执行参数

合成绑定使用 fixture-cluster、dcgm、fixture-node:9400 和两张 GPU-FIXTURE 卡。源 up 正常、样本年龄 0—90 秒、输入唯一及设备身份匹配后才参与判断。温度拒绝 NaN、无穷及 FP64 blank，状态和计数拒绝非法枚举、负值及整数 sentinel。

累计量使用五分钟窗口，支持计数重置，校验当前值、窗口样本数和数值有效性。历史窗口逐点整数校验仍有缺口，现场准入时需要补足。查询结果为空时须结合质量和覆盖状态查看。

离线样本按 30 秒间隔求值。流式测试每 2 秒采集，各查询使用同一个求值时刻，以便比较 ns 换算和同源计数的外推结果。通知、for、回差和生产阈值继续待审定。结构化表达式见[查询目录](catalog/thermal-links-review-queries.yaml)。

## 实际验证

15 条查询通过 138 个离线用例。本批包含温度边界、分数值、有效负温度、错误设备配对、缺失门槛、重复序列、位掩码组合、未知位共存、ns 换算、计数重置和无效窗口。

独立 Docker Prometheus 通过 8 个流式场景，覆盖正常输入、组合异常、重复采集、无效门槛、未知位、未知位与热限制共存、旧时间戳及 HTTP 503。测试集群在脚本退出时自动清理。夜莺流式验证和真实 H100 验证仍待完成。[验收结果](tests/thermal-links-review-results.yaml)

```bash
python3 modules/devices/nvidia-gpu/rules/scripts/build_h100_thermal_links.py --check
python3 modules/devices/nvidia-gpu/rules/scripts/check_monitoring.py
bash modules/devices/nvidia-gpu/rules/scripts/test_monitoring.sh
bash modules/devices/nvidia-gpu/rules/scripts/test_thermal_links_live.sh
```

前两项预期输出 PASS，离线 promtool 预期五次 SUCCESS，流式脚本预期八个场景 PASS。该步骤可在无 GPU 机器验证。
