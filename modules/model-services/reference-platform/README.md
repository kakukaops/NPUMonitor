# 独立参考模型平台

负责训练任务、制品、部署和评分，独立进程与数据卷，不访问Prometheus、夜莺或监控数据库。数值实现来自相邻runtime共享库，并由MODEL_DEVICE_PLUGINS显式安装设备扩展，旧模块路径保留兼容层。

仓库根目录执行：

```bash
GPU_ML_SIMULATION=true bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh platform-up
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh platform-logs
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh platform-backup
```

platform-up只启动模型服务；实验profile仅用于明确模拟数据，正式数据不用SIMULATION。/health在localhost:19461，其他API需要独立内部令牌文件（不在页面显示）。输入训练数据由调用者导出，独立平台无需采集系统在线。

独立数据卷model-platform-data，备份API返回平台卷中archive_name及摘要，可用docker compose cp复制。离线恢复到新的空目录：

```bash
python -m gpu_ml_platform.cli restore /path/to/trusted-backup.tar.gz /empty/target
```

需要安装同版本共享运行库与API依赖，或在平台镜像里运行该命令。不覆盖活动卷。监控备份不含这些远程权重。

这只是可替换参考实现，不是公司的平台，也不宣称生产HA、企业租户管理或资源编排能力。见[边界方案](../../devices/nvidia-gpu/ml/docs/12-模型训练与平台解耦方案.md)与[契约](../../devices/nvidia-gpu/ml/docs/13-模型平台接口契约.md)。
