# GPU 规则监控模块

**规范主清单：**[第14篇GPU监控指标与告警规则说明表](docs/14-GPU监控指标与告警规则说明表.md)是GPU规则领域的唯一规范入口。本文说明或代码生成结果不替代主清单；当前实现范围和生产差距分别核对。

当前检测职责见[双通道监控方案](docs/16-XID事件与指标状态双通道监控方案.md)：XID错误事件与指标状态独立检测；跨规则事件关联及通知收敛明确暂缓。

当前现场接入使用[OS SRE规则0.2.0](monitoring/os-sre/README.md)，不依赖业务集群、任务/作业ID或作业运行状态。当前规则指针位于[rules/current-profile.json](rules/current-profile.json)。原H100冻结草案、模拟实现及旧验收代码保留为历史；17000夜莺中的63项旧确定性规则已清理，当前主清单模拟58项规则位于“GPU监控规则（OS SRE）”组（ID 7），稳定核心46项由显式模拟扩展补充。机器学习规则属于独立模块并保留。

修改说明见[无业务属性规则方案](docs/11-OS-SRE无业务属性规则方案.md)。

| 目录 | 内容 |
|---|---|
| `docs/` | 原需求、技术架构、开发计划、规则库、模拟及恢复专项文档 |
| `rules/` | 实验规则目录和运行绑定 |
| `monitoring/` | 规则卡、覆盖、诊断、规则台账、综合候选库及验收 |
| `lab/` | GPU模拟器、夜莺适配、持久状态适配、通知接收器和演示页面 |
| `scripts/` | 构建、渲染、检查和运行脚本 |
| `tests/` | Python行为和HTTP契约测试 |
| `reports/`、`research_notes/` | GPU规则调研、模拟演示及依据 |

监控指标按8个对象域分类，分类依据与资源/性能缺口核查见[GPU监控分类与覆盖核查](reports/GPU监控分类与覆盖核查.md)。新增建议尚未接入OS SRE运行契约，不改变当前46项规则。

指标与告警的统一说明见 [GPU监控指标与告警规则说明表](docs/14-GPU监控指标与告警规则说明表.md)，按表列出指标、判据、双方含义与双方来源，包含仅诊断指标和未启用能力。

规则来源详见[46项规则逐条来源表](monitoring/os-sre/provenance.md)，含官方定位、项目判据、参数和证据边界。

**生产状态：未就绪。** 剩余阻塞、验收标准和实施顺序见[生产就绪审计与任务清单](docs/12-生产就绪审计与任务清单.md)。

## 共享依赖

GPU指标语义、硬件范围、驱动参考、字段来源和指标台账的唯一实体文件在[公共模块](../common/README.md)。本模块 `monitoring/` 内保留10个相对符号链接作为旧生成器的读取视图，不复制共用资产。修改共享定义需同时验证规则与ML引用。

`deploy/` 编排、`.local/` 凭据和临时运行数据继续位于仓库根目录；命名卷和Compose项目名保持原值。容器内 `/app`、`/rules` 等路径不变，宿主机挂载已指向新模块。

## 常用命令

从仓库根目录执行：

```bash
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh status
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh verify
python modules/devices/nvidia-gpu/rules/scripts/build_os_sre.py --check
python modules/devices/nvidia-gpu/rules/scripts/test_os_sre.py
python modules/devices/nvidia-gpu/rules/scripts/check_monitoring.py
python modules/devices/nvidia-gpu/rules/scripts/check_h100_training.py
python modules/devices/nvidia-gpu/rules/scripts/render_h100_inventory.py --check
bash modules/devices/nvidia-gpu/rules/scripts/test_monitoring.sh
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh test
```

根目录 `scripts/lab.sh`、`scripts/test_monitoring.sh` 保留为薄兼容入口，实际实现只在本模块。状态检查与测试命令不同：综合故障演练、通知及重启测试会改变实验场景，应按原说明顺序执行。

## 文档入口与边界

- [规则系统需求](docs/01-需求文档.md)
- [规则系统架构](docs/02-技术架构文档.md)
- [规则系统计划](docs/03-开发计划文档.md)
- [综合规则验收](docs/10-H100综合规则与模拟验收.md)
- [缺数保持与恢复实测](docs/09-硬件告警保持与解除策略.md)
- [H100综合候选库](monitoring/h100-training/README.md)
- [ML模块](../ml/README.md)

历史模拟综合库为42项输入、45条规则、25个视图，真实H100仍为not_run；目录迁移不是新一轮生产准入。

## OS SRE 生产运行服务

新增 [runtime](runtime/README.md)：读取现有 Prometheus，提供持久化设备状态、恢复确认、夜莺同步与独立组件通知。生产部署与隔离验收入口分离，详见 [安装与操作手册](docs/13-生产规则运行与验收.md)。当前交付标记为 1.0.0-rc1，验收范围见运行服务证据，不将 RC 等同于正式生产发行。

当前运行与故障场景见[主清单模拟指标与规则运行说明](docs/17-主清单模拟指标与规则运行说明.md)。


正式契约入口：`runtime/config.production.example.json`选择`h100-dcgm-master-v1`，覆盖88项数值字段及58条规则定义；配置/预检方法见[第18篇正式契约与实现对齐](docs/18-正式指标契约与实现对齐.md)。第14篇仍为规范源，旧核心配置与当前模拟部署保留兼容，不代表正式发行已经完成。
