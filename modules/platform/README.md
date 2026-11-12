# 监控公共平台

当前已抽取的实体实现：

| 路径 | 职责 |
|---|---|
| `integrations/accelerator_integrations/prometheus.py` | 有界查询、认证、超时、并发、错误与统计 |
| `integrations/accelerator_integrations/nightingale.py` | 夜莺HTTP认证与请求；不定义GPU业务组/规则 |
| `ml-monitoring/backend/accelerator_monitoring/store.py` | SQLite元数据、结果、审计和源时间状态 |

这些包不导入 `gpu_ml` 或 `nvidia_gpu_ml`。指标名、身份映射、场景、规则与夜莺对象归属留在设备适配器。监控入口仍使用设备模块，不运行第二个公共控制面。

GPU Web/API与任务编排含设备专属逻辑，暂保留在[设备模块](../devices/nvidia-gpu/README.md)。未来接入NPU时基于真实契约提取共用页面/编排，不把已有GPU服务直接当作NPU可用系统。平台契约将在真实第二种设备接入时固化，当前没有未使用的公共接口空壳。

模型协议和算法属于[模型服务](../model-services/README.md)。目录及依赖边界由根 `scripts/check_module_layout.py` 检查。
