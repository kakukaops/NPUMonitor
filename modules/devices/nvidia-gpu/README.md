# NVIDIA GPU监控

设备类型：GPU；厂商：NVIDIA；当前主要验证范围为H100候选规则及DCGM模拟检测。真实硬件准入状态见各模块验收记录。

- [公共指标、硬件与来源](common/README.md)：NVIDIA专属资产，不是跨厂商指标库。
- [规则监控](rules/README.md)：规则卡、PromQL、处置、状态保持、模拟和验收。
- [机器学习监控](ml/README.md)：DCGM场景、数据与特征配置、GPU Web/API及设备扩展。

ML设备扩展位于 `adapters/nvidia_gpu_ml/`：DCGM条件检测、残差漂移及历史GPU模型。通用算法通过注册表使用扩展；公共平台不导入DCGM场景。现有Web/API仍为GPU入口，待有NPU实际契约后再将设备无关的页面和任务编排逐项提取，避免把GPU专属实现直接改名为通用平台。
