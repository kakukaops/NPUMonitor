# GPU 规则监控模块

本模块归集已有 GPU 规则监控的实现、专项文档、模拟验证与冻结验收材料。目录归类不改变规则表达式、运行参数、数据库绑定、通知目标或生产准入状态。

| 目录 | 内容 |
|---|---|
| `docs/` | 原需求、技术架构、开发计划、规则库、模拟及恢复专项文档 |
| `rules/` | 实验规则目录和运行绑定 |
| `monitoring/` | 规则卡、覆盖、诊断、规则台账、综合候选库及验收 |
| `lab/` | GPU模拟器、夜莺适配、持久状态适配、通知接收器和演示页面 |
| `scripts/` | 构建、渲染、检查和运行脚本 |
| `tests/` | Python行为和HTTP契约测试 |
| `reports/`、`research_notes/` | GPU规则调研、模拟演示及依据 |

## 共享依赖

GPU指标语义、硬件范围、驱动参考、字段来源和指标台账的唯一实体文件在[公共模块](../common/README.md)。本模块 `monitoring/` 内保留10个相对符号链接作为旧生成器的读取视图，不复制共用资产。修改共享定义需同时验证规则与ML引用。

`deploy/` 编排、`.local/` 凭据和临时运行数据继续位于仓库根目录；命名卷和Compose项目名保持原值。容器内 `/app`、`/rules` 等路径不变，宿主机挂载已指向新模块。

## 常用命令

从仓库根目录执行：

```bash
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh status
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh verify
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

已有综合库为42项输入、45条规则、25个视图，真实H100仍为not_run；目录迁移不是新一轮生产准入。
