# DEMO_MAINTENANCE

历史模拟输入；当前接入契约见[OS SRE指标](../../os-sre/metrics.yaml)。

metric_id `training.input.demo_maintenance`，版本0.1.0，状态candidate。

## 语义与单位

原始名 `DEMO_MAINTENANCE`，字段ID `None`，类别为工程配置/上下文。
类型 `boolean`，单位 `boolean`。

## 身份与适用性

按cluster_id及entity_id定位对象。GPU使用UUID，交换机使用switch_id，端口额外保留link_id。
H100 PCIe、SXM、NVL的现场字段支持均待核验。模拟数据的modelName为SIMULATED，实例清单见catalog.yaml。

## 有效性与缺数

有效范围为 [0, 2)。整数、计数及枚举还要求整数值。
样本需来自健康采集目标，原始年龄0—15秒，输入唯一。生产候选新鲜度90秒，须结合实际采样周期审定。
拒绝NaN、Inf和sentinel。缺失、重复、陈旧、非法值进入独立质量规则，已确认硬件异常继续保持。

## 采集与数值示例

模拟正常值 `0`。此值用于样本，设备门槛字段在实际部署读取设备。
演示每2秒采样。各查询单位换算在对应规则说明中标明。

## 关联规则

该输入用于清单、维护、历史或诊断视图。

## 来源与验证

[固定DCGM字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h) · [原始输入台账](../../../../common/monitoring/metric-inventory.md)
来源核对、合成测试、夜莺模拟验收与真实H100采集分别保留证据。当前真实硬件验证为not_run。
