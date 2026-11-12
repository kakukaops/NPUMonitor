# H100：不可纠正双比特 ECC 错误易失累计数

metric_id：`nvidia.ecc_dbe_volatile_total`  
version：0.3.0；schema_version：0.2.0；lifecycle：draft  
维护者：GPU监控规则库维护者；核对日期：2026-11-06  
结构化定义：[metrics.yaml](../catalog/metrics.yaml)

应用基线：H100训练、无虚拟化；Linux参考驱动595.112.07（R595 Production Branch），DCGM兼容门槛4.3.x及以上。实际安装版本与采集仍未核实，详见[训练基线](../hardware/H100训练基线.md)。

## 1. 定义和检测边界

该字段汇总设备的 double-bit volatile ECC 错误计数。NVML旧命名中的double-bit映射到uncorrected类别；它是累计值，不是瞬时错误开关，也不是利用率。字段语义与分类分别来自[nvidia.dcgm.fields](https://docs.nvidia.com/datacenter/dcgm/3.0/dcgm-api/dcgm-api-field-ids.html)及[nvidia.nvml.ecc](https://docs.nvidia.com/deploy/archive/R550/nvml-api/group__nvmlDeviceEnumvs.html)。

同一设备有效累计值增加，可作为近期出现该类错误的检测输入。但单凭这个总数不能定位具体存储位置、判断所有GPU故障、确认GPU永久损坏，或确定哪些作业已受影响。不要将这个汇总数与各位置明细再次相加。

## 2. 原始字段与采集映射

| 项目 | 内容 | 依据与状态 |
| --- | --- | --- |
| DCGM字段 | DCGM_FI_DEV_ECC_DBE_VOL_TOTAL，字段ID 311 | nvidia.dcgm.fields；语义已核对，目标版本待核对 |
| Prometheus名 | DCGM_FI_DEV_ECC_DBE_VOL_TOTAL | nvidia.exporter.counters；真实现场待核对 |
| 类型 | counter | 固定Exporter配置将其声明为counter；仍要检查现场# TYPE与采集配置 |
| 原始/规范单位 | 错误计数 errors，无需换算 | 字段计数语义；不是字节数或错误比率 |
| 累计范围 | volatile计数，驱动加载会重置 | NVML R550 nvmlEccCounterType_t；不能当作跨驱动生命周期永久累计 |
| 其他清零 | 如环境允许的显式清零，具体支持与行为待核对 | 不能假设计数下降等于硬件恢复 |
| 默认采集 | 引用的固定CSV中该行被注释 | 不代表所有Exporter版本都相同；本项目不要求用户重新部署采集 |
| 别名/重命名 | 未确认，不声明可直接替换的别名 | 待取得现场版本和原始样本 |

NVML明确说明驱动加载会影响volatile计数，Linux上的驱动生命周期也不一定等同系统启动周期。[固定R550说明](https://docs.nvidia.com/deploy/archive/R550/nvml-api/group__nvmlDeviceEnumvs.html)

## 3. 标签、身份与粒度

| 标签 | 要求 | 提供者/用途 | 限制 |
| --- | --- | --- | --- |
| cluster_id | 必需 | 部署或采集标签，区分集群 | 不是DCGM原生字段保证；需配置并检查唯一性 |
| UUID | 必需 | Exporter设备标签，稳定物理卡身份 | 需确认现场确实存在；换卡应产生新身份 |
| Hostname、gpu、modelName | 可选 | 展示与排障 | gpu序号不作为稳定身份 |
| job、instance | 保留 | 定位采集源、排查重复采集 | 采集实例重建可能改变序列身份 |

样例设备键为cluster_id+UUID。当前不批准MIG实例级解释；必须核实物理卡总数是否在多个实例上重复暴露，再决定粒度。重复采集同一设备时先解决去重和映射，不能通过sum或max随意合并来隐藏问题。

## 4. H100型号兼容矩阵

第一版只研究H100，型号配置入口见[H100范围](../hardware/H100.md)。以下是目标清单，不是已支持清单。

| profile_id | GPU型号/形态 | 软件版本条件 | 官方字段支持 | 采集验证 | H100现场验证 | 阻塞项 |
| --- | --- | --- | --- | --- | --- | --- |
| nvidia.h100.pcie | H100 PCIe | 驱动/DCGM/Exporter未知 | unknown | not_run | not_run | 逐字段语义、真实样本、无效值映射 |
| nvidia.h100.sxm | H100 SXM | 驱动/DCGM/Exporter未知 | unknown | not_run | not_run | 逐字段语义、真实样本、无效值映射 |
| nvidia.h100.nvl | H100 NVL | 驱动/DCGM/Exporter未知 | unknown | not_run | not_run | 逐字段语义、真实样本、无效值映射 |

H100属于Hopper的产品身份已有官方依据，但引用通用DCGM字段和NVML计数语义不能证明本字段在上述所有配置可用。需要核实H100的DRAM/SRAM统计范围，不能把本汇总字段自动解释为某一种存储位置的独立错误数。

当前仅考虑物理卡；MIG实例级字段与重复暴露尚未准入。字段缺数时不能直接宣称H100不支持或设备健康。H200及其他型号不在本版兼容矩阵，也不继承本样例的结论。

## 5. 数值、特殊值与缺数

有效输入应为非负、有限的累计计数。负值、NaN和正负无穷均无效。DCGM定义INT64 blank下界为`0x7ffffffffffffff0`（十进制9223372036854775792），并定义一组更高的无效状态值；这些不是ECC错误次数。[固定源码 nvidia.dcgm.blank](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_structs.h)

Prometheus数值是浮点表示，相邻INT64 sentinel可能无法逐个区分。样例只屏蔽该无效区间，不通过浮点数反推出具体错误原因。字段在目标Exporter中是否被省略、变成特殊数值或使用其他表示，仍待实测；当前INT64过滤不能声称覆盖所有Exporter映射。

缺失可能来自未采集、字段不支持、设备消失或链路故障。陈旧与查询失败也单独记录；都不等于零次错误或GPU健康。值为0只表示本计数周期尚未记录该类错误，不等于GPU没有其他故障。

## 6. 更新周期与采集限制

设备内部更新、Exporter刷新和Prometheus scrape是三个不同周期，现场值未知。本规则样例采用30秒采样假设和90秒新鲜度门槛，是工程提案，不是NVIDIA标准。

采集权限、Exporter配置、实际序列基数和查询成本待核实。确认是否已暴露字段即可；本项目的既定边界是不重装采集、不修改已有Prometheus规则。若字段没有采集，应显示覆盖缺口。

## 7. 样本、验证与关联规则

以下为合成样本，用于说明格式，不是实际硬件采集结果：

```text
# HELP DCGM_FI_DEV_ECC_DBE_VOL_TOTAL Synthetic volatile uncorrected ECC counter.
# TYPE DCGM_FI_DEV_ECC_DBE_VOL_TOTAL counter
DCGM_FI_DEV_ECC_DBE_VOL_TOTAL{cluster_id="fixture-cluster",UUID="GPU-FIXTURE-0000",job="fixture-dcgm",instance="fixture-node:9400"} 1
```

关联规则：[GPU近期新增不可纠正ECC错误](../../../rules/monitoring/rules/nvidia.ecc_dbe_new_errors.md)。

来源核对为partial：计数含义、重置及配置类型已核对，目标硬件/版本未核对。新规则表达式样本结果见[tests](../../../rules/monitoring/tests/README.md)；本指标的真实硬件与MIG采集验证均未运行。此前实验规则通过记录仅作为思路参考，不代替这里的新规则验收。

## 8. 待验证项、来源和变更

| 缺口 | 怎样补证据 | 发布影响 |
| --- | --- | --- |
| H100具体形态和版本兼容 | 获取PCIe/SXM/NVL、驱动/DCGM/Exporter版本与# TYPE原样本 | 不允许自动启用 |
| sentinel实际映射 | 核对对应Exporter源码及不支持/无效字段样本 | 不允许宣称完整数据质量覆盖 |
| MIG和重复采集 | 比较物理卡/实例序列与采集来源 | 不允许跨实例直接汇总 |
| 周期、权限和成本 | 获取采样/刷新设置，记录序列数与查询耗时 | 参数必须重新审定 |

完整来源版本、章节和核对日期见[sources.yaml](../catalog/sources.yaml)。引用Exporter CSV使用固定提交，未复制上游规则或配置文件；这里只引用事实并独立编写说明。

| 日期 | 版本 | 变更 | 影响 |
| --- | --- | --- | --- |
| 2026-11-06 | 0.1.0 | 首份格式审阅样例 | draft，不改变运行环境 |
| 2026-11-06 | 0.2.0 | 第一版收敛H100，增加逐形态兼容字段 | 不改变表达式，不代表H100硬件已验证 |
| 2026-11-06 | 0.3.0 | 固定训练/无虚拟化场景与R595设计参考 | 表达式未改，新增版本兼容约束，未验证真实硬件 |
