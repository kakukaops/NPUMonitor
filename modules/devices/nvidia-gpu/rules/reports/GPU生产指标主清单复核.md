# GPU生产指标主清单复核

日期：2026-11-13。规范入口为[第14篇生产主清单](../docs/14-GPU监控指标与告警规则说明表.md)，规范修订1.0；本文记录复核结论，不另立指标或告警规范。适用范围为当前H100物理卡基线，硬件形态、驱动/NVML/DCGM/Exporter及条件能力分别准入，不声称覆盖全部未来GPU。

## 完整性复核结果

上一版补齐了资源和性能观察维度，但仍不是完整的生产候选对账：公共92项候选中，有26个原始DCGM字段尚未形成明确条目。现已在8个监控领域补列，并为全部92项设置稳定ID、字段/别名、类型/单位、实体/身份、适用性、有效性、采用理由、规则与恢复边界和来源。

92项的生产要求分别为：必选29项、条件必选43项、可选17项、外部2项、排除1项。它们是项目基线取舍，不是NVIDIA统一强制清单。当前实现状态分别为：当前契约37项、当前功能5项、部分元数据1项、计划43项、阻塞3项、外部未接入2项、排除1项。两套维度不混用；“必选”不表示已经完成。

此外，主清单逐项登记11个公共候选之外的已知字段：设备报告总显存、预留显存、累计能耗、NVLink方向/聚合吞吐、不可修复内存标志、原生显存占用比例以及条件适用的3个页退休字段。总共103项逐项契约；外部输入表另说明完整错误事件、PCIe AER、BMC/机箱电源与温控、主动诊断、MIG和用途扩展的边界，不伪造通用DCGM字段。

原有46项规则、8项仅诊断ECC条目、可选网关健康和2项Watchdog主题均保留。新增字段没有自动进入采集器、37字段运行契约或夜莺告警；当前46规则/45启用/1禁用与模拟数据事实未变。

## 语义修正

- **NVLink状态**：明确连接存在与traffic-ready是不同目标；Sleep可能正常。R595与新NVML620的状态集合不能混用，不能将“正数”统一当作可通流量。现有0异常/>0解除及0≤值<3的实现被如实记录，版本化目标与恢复政策尚待审定，并非统一认定Sleep故障或认定R595缺少新状态必错。
- **显存比例**：固定字段254的canonical为`DCGM_FI_DEV_FB_USED_RATIO`，语义0–1、分母Total−Reserved；旧PERCENT别名不证明已乘100。自定义Used/Total比例保持不同名称和分母。
- **内存维护**：重映射计数是InfoROM记录条目，不是已应用到硬件的行数；剩余重映射资源、不可修复标志、InfoROM有效性和恢复动作另列。传统页退休字段按架构能力选用，不强制作为H100 row-remap替代。
- **温控及单位**：max-op、slowdown、shutdown和margin分别解释；CSV声明TYPE不是DCGM语义及实际单位的自动认证。ns/seconds、mJ/J、MiB/bytes、MHz/Hz、percent/ratio及各吞吐版本逐项固定。

依据可追溯至[固定DCGM字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)、[固定Exporter配置](https://github.com/NVIDIA/dcgm-exporter/blob/fafd151148052628061a80450b4ee037a5fa0c3c/etc/default-counters.csv)、[NVML状态定义](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlFieldValueEnums.html)及[NVML620变更](https://docs.nvidia.com/deploy/nvml-api/620/change-log.html)。详细审查记录保存在[本轮研究笔记](../research_notes/GPU生产指标主清单复核/semantics.md)。

## 规范治理与可复验检查

其他01—16篇文档及规则模块主要README均明确引用第14篇。历史设计/验收保留当时事实，不能作为覆盖新规范的依据；代码、catalog和证据仍说明当前实现，不因文档升级而追认新增能力。共享候选台账是资料来源，ML和NPU规范不在本次重写范围。

[派生覆盖索引](../docs/14-GPU监控指标与告警规则说明表.coverage.json)由主清单解析生成，包含文档、候选库与当前catalog摘要；不是独立语义来源。[校验脚本](../scripts/check_gpu_monitoring_master.py)核对候选稳定ID、字段ID、主清单锚点、来源、实施状态、当前字段与规则追踪及从属文档入口。7项反向检查覆盖遗漏、重复、锚点丢失、虚假已实现、来源缺失、漏规则和字段ID错配，已纳入CI配置。

```bash
python modules/devices/nvidia-gpu/rules/scripts/check_gpu_monitoring_master.py --self-test
python scripts/check_module_layout.py
python modules/devices/nvidia-gpu/rules/scripts/check_gpu_monitoring_master.py --require-production-alignment
```

前两项通过；最后一项按预期返回2：当前仍有15项必选实施缺口及G-NVLINK、G-UNITS、G-IMPLEMENTATION三个开放门槛。文档覆盖闭合不等于生产软件对齐；不能现在按全表批量启用。关闭差距需要契约审定、实现和模拟生命周期验证，不以取得真实GPU历史数据作为开发前提。完整XID事件流仍待实现，跨规则事件关联和通知收敛仍按用户要求暂缓。本次未修改运行代码、Prometheus或线上告警。
