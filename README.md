# 异构加速器监控系统

GPU规则领域的指标、适用性与告警语义以[第14篇生产主清单](modules/devices/nvidia-gpu/rules/docs/14-GPU监控指标与告警规则说明表.md)为唯一规范入口；当前实现范围与未关闭的生产差距分开记录。

基于夜莺与Prometheus建设规则监控及机器学习监控。当前实现NVIDIA GPU/DCGM；Huawei Ascend NPU已有独立开发入口，采集和检测尚未实现。

## 模块入口

| 路径 | 职责 |
|---|---|
| [NVIDIA GPU](modules/devices/nvidia-gpu/README.md) | NVIDIA指标、规则、DCGM检测场景、模拟与验收 |
| [Huawei NPU](modules/devices/huawei-npu/README.md) | Ascend接入边界和后续开发计划 |
| [公共平台](modules/platform/README.md) | Prometheus/夜莺HTTP集成、监控状态存储 |
| [模型服务](modules/model-services/README.md) | 模型协议、平台适配器、通用算法、独立参考服务 |

项目根目录现为 `NPUMonitor/`，见[根目录迁移说明](docs/项目根目录迁移说明.md)。

规则现场接入请使用[OS SRE无业务属性规则](modules/devices/nvidia-gpu/rules/monitoring/os-sre/README.md)。

## 运行入口

从仓库根目录执行：

```bash
python scripts/check_module_layout.py
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh status
bash modules/devices/nvidia-gpu/rules/scripts/lab.sh verify
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh status
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh test
```

GPU ML页面保持 http://localhost:19460，夜莺保持 http://localhost:17000。旧的根scripts和原模块Shell入口保留薄包装。Python命令使用新实体路径；历史Python模型导入名保持兼容。

`deploy/shared/`为基础组件定义，`deploy/nvidia-gpu/`为GPU规则实验、复核和ML组合，`deploy/model-platform/`为独立模型平台入口。`.local/`仍保存私有凭据与临时结果，不提交、不搬迁；现有项目名和数据卷保持。

[目录规划](docs/异构加速器监控目录规划.md) · [本次迁移与验收](docs/异构加速器目录迁移与验收.md) · [历史路径登记](modules/layout-migration.json)
