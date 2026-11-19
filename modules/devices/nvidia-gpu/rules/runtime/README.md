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

当前主清单模拟 profile 提供 **88 个数值字段**。夜莺 17000 的「GPU监控规则（OS SRE）」组（ID 7）启用 **42 条原生 PromQL 规则**，直连原始数据源 ID 9。迁移时就地更新规则并移除 16 条旧链路规则定义，更新前快照在本地 .local/gpu-os-sre-master/native-migration-*.json。状态服务 19476 和独立 Watchdog 继续运行，链路规则不再由本组发送。模拟源为 19477，Prometheus 为 19093。

详细使用、场景、覆盖边界及清理记录见[主清单模拟运行说明](../docs/17-主清单模拟指标与规则运行说明.md)。`current-up/current-status/current-cli/current-simulate`均操作新项目；独立ML模块保持。生产默认核心37字段/46规则与本地显式开启的 `h100-master-simulation-v1` 区分，不能将模拟能力当成生产认证。

## Prometheus 原生告警

[原生规则包](production/gpu-native-alerts.prom.yaml)包含 42 条 GPU、NVSwitch 和互联规则，使用生产目录的指标、判据、严重度和确认时长。将它加入目标 Prometheus 的 `rule_files`，由 Prometheus/Alertmanager 评估和发送通知。5 条 XID、2 条 SXID 规则直接比较源指标，命中样本的错误码显示在通知摘要及 `xid_code` / `sxid_code` 注解中。其余规则根据对应的原始指标计算判据，并过滤健康观测。通知摘要保留设备身份；输入指标名可在 `input_metrics` 中查看。

默认包按 `dcgm.*` 匹配抓取任务。部署前核实 Exporter 的指标名称、单位、枚举及实体标签。掉链、PCIe 降级等带资产门槛的规则需要现场填入预期设备、端口或协商阈值；默认空清单不会触发依赖这些输入的规则。复制 [OS SRE 示例 profile](../monitoring/os-sre/profile.yaml) 填写现场参数后，在仓库根目录运行：

```bash
python modules/devices/nvidia-gpu/rules/scripts/build_production_contract.py \
  --prometheus-profile /path/to/site-profile.yaml \
  --prometheus-output /path/to/gpu-native-alerts.prom.yaml
promtool check rules /path/to/gpu-native-alerts.prom.yaml
```

原生版按 Prometheus 的表达式结果进入和退出告警。丢失有效样本、XID 切换到其他组或落入温度回差区间时，原生实例可能结束；此结束只说明当前触发表达式未命中。运维确认后解除、未知时无限期保持和事件恢复通知中的原始码仍由状态服务提供。接入时同一设备和规则应只由一个入口对外通知。

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

## 原生 PromQL 维护约定

先对照目标平台的官方规则，写出能单独解释的触发条件。错误码和枚举直接做数值匹配，每个源指标的身份、去重和新鲜度检查应尽量只展开一次。原生告警只交付命中分支，样本缺失和恢复确认由对应的执行模式处理。保留触发样本的实际错误码、状态值或余量，并区分普通比较和布尔观测，避免健康的零值进入原生告警结果。上线前用 Prometheus 对比旧规则与新规则的命中设备及确认时长，覆盖正常、故障、缺数和现场资产门槛。
