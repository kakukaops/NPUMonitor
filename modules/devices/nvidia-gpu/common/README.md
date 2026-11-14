# NVIDIA GPU 监控公共资产

**正式指标规范源：**[第14篇GPU监控指标与告警规则说明表](../rules/docs/14-GPU监控指标与告警规则说明表.md)。模拟数据、规则和ML输入统一遵循；公共契约与ML输入契约为自动派生，旧台账不能覆盖此规范。


当前OS SRE规则的无业务属性输入契约见[OS SRE指标](../rules/monitoring/os-sre/metrics.yaml)；本目录6份早期正式draft卡保留原版本语义与冻结证据，不代表当前规则仍要求cluster_id。

这些资产仅供NVIDIA GPU规则与ML共用，不作为Huawei NPU字段定义。

本模块只归集已经确认由GPU规则监控和机器学习监控共同引用的知识与契约，不提前抽象模型运行时或重建通用告警框架。

| 路径 | 内容 |
|---|---|
| `monitoring/catalog/metric-inventory.yaml` | 92项候选指标、外部上下文及其语义，不代表均已采集 |
| `monitoring/catalog/metrics.yaml` | 既有正式draft指标/输入卡目录 |
| `monitoring/catalog/hardware.yaml`、`driver-baseline.yaml` | 硬件范围及研究参考，现场仍需验证 |
| `monitoring/catalog/sources.yaml`、`inventory-evidence.yaml` | 字段来源和台账构建依据 |
| `monitoring/metrics/` | 共用指标语义卡 |
| `monitoring/hardware/` | H100范围与训练基线 |
| `monitoring/metric-inventory.md` | 候选指标的人类可读台账 |
| `monitoring/templates/metric.md` | 指标卡模板 |
| `layout.py` | 迁移路径解析及旧文档生成器链接重定位工具 |

规则、表达式、处置、事件与规则验收仍属于[规则模块](../rules/README.md)；训练、模型与ML页面属于[ML模块](../ml/README.md)。

共用资产只有一个实体文件。本次为保持规则生成器的输入契约，在规则模块保留指向这里的10个相对符号链接。部署和打包必须保留仓库内的模块关系；不可仅复制规则模块并丢弃公共依赖。

迁移登记位于[layout-migration.json](../../../layout-migration.json)：旧路径映射到唯一实体文件，冻结的非Markdown规则/数据契约/验收资产保留原始SHA256。历史证据中的旧路径按记录解释，不改写历史载荷。

```bash
python scripts/check_module_layout.py
```

本次未将已有 `modules/devices/nvidia-gpu/rules/lab/n9e.py` 等代码直接抽成新公共SDK：先归属规则模块，后续ML真实复用时再按接口与测试抽取，避免提前制造未验证的跨模块依赖。
