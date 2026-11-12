# GPU机器学习监控模块

当前版本 **0.5.1 / 监控与模型平台解耦**。监控页面 **http://localhost:19460**，本地参考模型服务health为 **http://localhost:19461/health**。

## 职责

- 本模块：DCGM数据、GPU场景、特征、仿真、任务编排、GPU Web/API及夜莺对象绑定。
- `../adapters/nvidia_gpu_ml/`：NVIDIA条件检测、残差漂移与历史模型实现。
- [公共平台](../../../platform/README.md)：共享查询传输、夜莺HTTP传输和监控存储。
- [模型服务](../../../model-services/README.md)：模型协议、HTTP适配器、通用算法及独立训练/部署/评分。

新训练不在监控进程执行，新权重不写入监控模型目录。训练、校准/集成版本和API评分由独立服务完成。旧本地模型仍可检测、回放和回滚；修改旧制品需要先在目标平台重训，不自动上传pickle。

## 启动与使用

```bash
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh simulation-up
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh status
# 仅启动参考模型服务
GPU_ML_SIMULATION=true bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh platform-up
# 平台独立备份
bash modules/devices/nvidia-gpu/ml/scripts/gpu-ml.sh platform-backup
```

页面角色直登保持，训练入口不变；平台状态可在“平台与审计”查看。发布先部署成功再切换指针，失败不自动改模型。平台超时/错误标未知，不补正常值；外部任务重启后同步，不盲目重复提交。

当前仍只有DCGM，保留四类场景：条件热关系、功耗/时钟关系、热残差长期漂移、时钟残差长期漂移。场景默认仅证据，production和加速laboratory隔离；不增加作业、吞吐或环境信息，不认定硬件老化或预测寿命。

## 公司平台替换

实现ModelBackend原生SDK适配器，或提供内部协议兼容HTTP桥接。GPU_ML_MODEL_PLATFORM_URL配置兼容桥接地址时，启动脚本不再启动本地参考平台；GPU_ML_MODEL_BACKEND_ID标识独立后端命名空间，凭据来自私有文件。不能把任意公司模型URL直接填入后期待兼容。

真实公司API尚未提供，本轮仅完成边界、参考实现及替换端口桩测试，没有对接真实公司平台。当前单一后端配置，不做跨后端引用自动迁移；已有API模型应计划重训/迁移与切换，不能把旧model_ref直接发给新平台。旧本地模型不受这个URL切换影响。

## 文档

- [当前技术方案](docs/02-技术方案.md)
- [训练与平台解耦方案](docs/12-模型训练与平台解耦方案.md)
- [内部接口与企业适配](docs/13-模型平台接口契约.md)
- [v5实施与验收](docs/14-v5实施与验收.md)
- [DCGM场景](docs/10-DCGM场景清单与数据契约.md)
- [独立平台说明](../../../model-services/reference-platform/README.md)

监控备份不包含远程权重，平台需单独备份。真实GPU长期效果、公司真实接口、生产容量/HA及浏览器视觉仍未完成。
