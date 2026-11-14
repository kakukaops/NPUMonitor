# OS SRE 规则运行服务 1.0.0-rc1

**规范主清单：**[第14篇GPU监控指标与告警规则说明表](../docs/14-GPU监控指标与告警规则说明表.md)是GPU规则领域的唯一规范入口。本文说明或代码生成结果不替代主清单；当前实现范围和生产差距分别核对。

这是 NVIDIA GPU 规则模块的独立执行组件。使用已有 Prometheus 的只读查询接口，使用夜莺的数据源、告警和通知机制。与机器学习模块、旧实验适配器分离。

## 执行边界

```text
现有 DCGM Exporter → 现有 Prometheus（只读）
                                  ↓ 契约预检、单次查询配对原样本时间
                         规则运行服务 + SQLite
                                  ↓ Prometheus 兼容的活动告警向量
                           夜莺 → 现有通知策略
独立 Watchdog → 独立通知出口（组件故障）
```

34 条硬件表达式输出 0/1 观测，运行服务负责持续确认、未知保持和恢复语义；质量/平台规则使用原生非空告警向量语义，值为 0 的非空向量也表示命中。夜莺执行确认后的活动向量，`for=0`，避免重复累计持续时间。同步器管理 46 条规则记录和 1 条运行服务健康规则；不满足契约的规则显示覆盖缺口，不代表设备正常。

身份仅由 job、instance、UUID、switch_id、link_id、metric_name 中所需字段构成。支持物理 GPU 契约 `dcgm-os-sre-physical-v1`；不依赖任务、租户、集群业务标签。MIG 序列不纳入该契约。字段、单位、枚举及判据见 [来源表](../monitoring/os-sre/provenance.md)。预检能检查 TYPE、字段、身份、重复、非法值与新鲜度，单位依赖所声明的采集契约，不能从数值自动证明单位正确。

## 当前用户平台入口（17000）

当前已切换到主清单模拟profile：**88个数值字段、58项规则（57启用/1禁用）**。夜莺仍使用17000、“GPU监控规则（OS SRE）”组ID 7。原始指标数据源ID 9、状态数据源ID 8；新运行服务19476、模拟源19477、Prometheus19093。旧46项和旧模拟数据源已退出。

详细使用、场景、覆盖边界及清理记录见[主清单模拟运行说明](../docs/17-主清单模拟指标与规则运行说明.md)。`current-up/current-status/current-cli/current-simulate`均操作新项目；独立ML模块保持。生产默认核心37字段/46规则与本地显式开启的 `h100-master-simulation-v1` 区分，不能将模拟能力当成生产认证。

## 历史独立验收环境（已归档）

该17001历史栈已按清理要求归档，下面命令及端口仅保留旧验收复现记录；reference-up有退役保护，当前使用第17篇的新栈。

在仓库根目录运行：

```bash
bash modules/devices/nvidia-gpu/rules/scripts/sre-rules.sh reference-up
bash modules/devices/nvidia-gpu/rules/scripts/sre-rules.sh test
python modules/devices/nvidia-gpu/rules/scripts/verify_sre_runtime.py --case basic
python modules/devices/nvidia-gpu/rules/scripts/verify_sre_runtime.py --case matrix
python modules/devices/nvidia-gpu/rules/scripts/verify_sre_runtime.py --case operations
python modules/devices/nvidia-gpu/rules/scripts/verify_sre_runtime.py --case capacity
```

需要 Docker Compose 和首次拉取镜像的网络。测试用例须顺序执行，因为它们共用隔离模拟源。该环境创建自己的 Prometheus、夜莺、Redis、状态卷、通知接收器和凭据，不导入现有夜莺、不读取旧系统令牌。工厂初始密码仅用于新建隔离夜莺的首次引导，随后立即轮换；生成的凭据保存在被 Git 忽略的 `.local/npumonitor-rules-contract/`，权限为目录 0700、敏感文件 0600。

| 服务 | 本机地址 |
|---|---|
| 隔离夜莺 | http://127.0.0.1:17001 |
| 隔离 Prometheus | http://127.0.0.1:19091 |
| 规则服务存活 | http://127.0.0.1:19470/health |
| 规则服务就绪 | http://127.0.0.1:19470/ready |

详细状态、预检、计划及变更接口均需认证。凭据不要粘贴到命令、日志或文档。测试数据来自模拟器，Prometheus 查询、状态转换、夜莺事件和通知发送由真实组件执行。证据写入 [evidence](evidence)，真实硬件验证仍为 `not_run`。

## 接入已有系统

部署入口是 [production/compose.yaml](../../../../../deploy/nvidia-gpu/rules/production/compose.yaml)，完整步骤见 [生产规则运行与验收](../docs/13-生产规则运行与验收.md)。生产镜像不包含模拟器、旧演示数据或 ML 依赖。管理夜莺的凭据仅挂载到一次性 controller；长期运行的规则服务无需夜莺管理令牌。

首发为单实例 SQLite WAL，不能将同一状态卷挂给多个运行服务。独立 Watchdog 能发现运行服务与夜莺故障；如果与被监控服务同宿主机，不能覆盖整机断电，需部署在独立故障域或增加外部探测。


## 正式主清单配置（契约1.2）

新增`config.production.example.json`，选择`contract_profile=h100-dcgm-master-v1`。旧`config.example.json`仍为37字段/46规则兼容配置；当前本地模拟由显式`master_profile`维持，不自动切换。正式契约覆盖88字段/58规则定义，但实际启用集合受可选能力、单位、版本、元数据、资产和通知输入约束。正式配置不读取模拟默认值或场景。详见[正式契约与实现对齐](../docs/18-正式指标契约与实现对齐.md)，以[第14篇](../docs/14-GPU监控指标与告警规则说明表.md)为规范。
