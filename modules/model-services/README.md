# 独立模型服务

| 目录 | 职责 |
|---|---|
| `contracts/model_contracts/` | ModelBackend协议、源时间/评分校验、数据摘要 |
| `adapters/model_adapters/` | 参考HTTP适配器；公司平台在此实现对应适配器 |
| `runtime/gpu_ml_runtime/` | 通用预处理、检测器、校准、阈值、评估、安装注册表 |
| [reference-platform](reference-platform/README.md) | 独立异步训练、模型制品、部署、推理与备份 |

保留 `gpu_ml_runtime` 包名用于旧模型反序列化，不代表只支持GPU。通用流水线使用显式schema，可不加载任何设备扩展。`models.py`、`dcgm_scenarios.py`仅为旧NVIDIA制品保留导入兼容，实体实现位于设备包；新通用流水线不依赖这些兼容模块。

参考服务通过管理员配置 `MODEL_DEVICE_PLUGINS` 显式加载已安装扩展。目前GPU组合安装 `nvidia_gpu_ml.plugin`，但不安装监控引擎、Source或夜莺适配器。扩展提供NVIDIA schema与检测器，不负责读取Prometheus。公司平台实际API仍待接入。

独立参考平台入口：

```bash
docker compose -f deploy/model-platform/compose.yaml up -d --no-deps --wait model-platform
```

该配置沿用现有 `gpu-monitoring-ml` 项目及原模型卷；GPU组合通过extends引用同一服务定义，避免两份训练服务配置。初始化凭据仍使用设备启动脚本的prepare流程，单独入口要求现有凭据和基础网络已存在。
