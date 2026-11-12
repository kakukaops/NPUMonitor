# 夜莺时序异常检测 Demo

打开 **http://localhost:19450**。页面直接由本地 Python 服务提供，不依赖 CDN。

## 启动与验证

依赖现有 `deploy/nvidia-gpu/lab/compose.yaml` 中已运行的 Prometheus。所有科学计算依赖均安装在容器中，不改变宿主机 Python。首次构建需要访问 PyPI。

```bash
bash modules/devices/nvidia-gpu/ml/scripts/anomaly-demo.sh up
bash modules/devices/nvidia-gpu/ml/scripts/anomaly-demo.sh test
bash modules/devices/nvidia-gpu/ml/scripts/anomaly-demo.sh verify
```

`up` 只构建和启动新增服务，验证 Prometheus 配置后发送 SIGHUP 热加载；不重启夜莺、不删除卷、不改现有告警规则。若 Prometheus 尚未运行，先启动现有实验环境。访问端口仅绑定宿主机 127.0.0.1；远程访问使用已有 SSH 转发方式。

首次启动约 10 秒出现曲线。checkout 默认以四分钟为一轮自动注入，前 30 秒正常，之后轮流出现延迟尖峰、QPS 骤降、CPU 漂移、关系异常。手动注入持续 45 秒后恢复；“恢复正常”停止该服务轮播。其余两个服务默认正常。服务重启会恢复默认模式，历史曲线保留在 Prometheus 的现有保留期内（当前 3 天），页面查询最近 30 分钟。

`verify` 会依次实际注入四种异常、等待模型触发、验证恢复，并检查 Prometheus 已采集模型输出，最后恢复 checkout 自动轮播。约需两至三分钟，会临时改变 checkout 模拟场景；不操作真实业务指标。

## 数据链路

```text
/app /metrics 模拟器 → 现有 prometheus:9090（2 秒抓取）
                      → Python query_range（2 秒刷新）
                      → Ridge 基线 + IsolationForest
                      → /api/state → Web canvas
                      → /metrics 检测输出 → 同一个 Prometheus
```

页面观测曲线、已知注入标记都从 Prometheus 读取，不在前端补造历史。首次启动没有历史，曲线随运行逐步积累。模型预测、参考带、异常分数由这些已存储样本计算。独立 sample_time 指标用于识别查询 lookback 带来的重复旧样本；缺失不会补零，超过 6 秒的间断重置特征窗口，最后样本超过 10 秒视为数据不可用。参考带是健康残差 ±3σ 的可视化参考，不等同于森林告警阈值，也没有生产覆盖率保证。

## 模型与训练来源

- 开源实现：scikit-learn 1.6.1，联合 IsolationForest + 3 个单指标 IsolationForest，每个 160 棵树、max_samples=256、固定随机种子。
- 每个服务独立训练：健康模拟数据 3,600 个点，随后独立时间窗口的 1,200 个健康点校准。
- Ridge 用已知模拟周期 120 秒 / 360 秒的正余弦特征学习基线。
- 联合森林特征：标准化周期残差、残差差分、后向三点均值、跨指标残差关系；三个单指标森林分别使用当前绝对标准化残差。
- 各森林原始分数先除以其健康校准分数的 99% 分位数，再取最大比值；用组合分数在校准集的 99.5% 分位数确定最终阈值。单指标森林避免单一维度异常被联合特征稀释。组合分数不是故障概率。
- 推理不使用 truth / 场景名称。每个点只使用当前和过去观测，3/5 异常形成持续事件。
- 训练源明确是**独立健康模拟数据**，不是从 Prometheus 导出的真实业务历史；用于冷启动演示。不在此版本提供自动重训练。
- 模型和训练数据可复现，容器启动时重新训练，不加载外部 pickle。历史结果在相同模型版本下通过 Prometheus 输入重新计算；更换模型版本时须区分回放与当时在线结果。

关系异常特意使用超出健康残差噪声、但仍可能处于原始指标整体正常范围的偏移。它展示联合模型能力，不是已验证的真实故障模式。demo 的正常回放误报及四类注入测试不能推导真实线上准确率。

## Prometheus 与夜莺查询

新增 job：`ml-anomaly-demo`，不修改其他 job；新增序列均使用 `ml_demo_` 前缀。

```promql
ml_demo_value{service="checkout",signal="latency_ms"}
ml_demo_anomaly_score{service="checkout"}
ml_demo_anomaly_threshold{service="checkout"}
ml_demo_alert_active{service="checkout"}
time() - ml_demo_last_success_timestamp_seconds{service="checkout"}
```

这些指标可在夜莺已有 Prometheus 数据源中直接查询。若后续人工配置夜莺告警，需同时检查新鲜度，例如：

```promql
(ml_demo_alert_active{job="ml-anomaly-demo"} == 1)
and on(job,instance,service)
(time() - ml_demo_last_success_timestamp_seconds{job="ml-anomaly-demo"} < 10)
```

本 demo 不自动创建规则或发送通知。Web 的事件表是当前 30 分钟回放窗口内的合并检测事件，不是夜莺告警事件记录。

## 文件与接口

- `app.py`：模拟指标、Prometheus 读取、状态机、HTTP API。
- `model.py`：训练、校准与因果特征。
- `index.html`：无外部依赖的中文响应式页面。
- `test_model.py`：独立正常回放误报、四类注入、未来数据泄漏、缺失数据测试。
- `verify.py`：真实 Prometheus 端到端验收。
- `GET /health`：进程健康；不代表 Prometheus 已有新数据。
- `GET /ready`：Prometheus 数据新鲜且检测 Worker 已成功刷新，否则返回 503。
- `GET /api/state`：任务状态、训练来源、曲线与异常事件。
- `POST /api/scenario`：`{"service":"checkout","scenario":"spike"}`。

查看日志：`bash modules/devices/nvidia-gpu/ml/scripts/anomaly-demo.sh logs`。停止 demo：`bash modules/devices/nvidia-gpu/ml/scripts/anomaly-demo.sh stop`，此时其 Prometheus target 会显示 down，其他服务保持运行。

资料：[IsolationForest](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.IsolationForest.html)、[Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)。
