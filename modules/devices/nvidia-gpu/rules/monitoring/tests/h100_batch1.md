# H100首批卡片与离线验收

日期：2026-11-09。状态：表达式合成测试通过，生产未准入。

## 本批交付

新增5份指标/输入卡、8份规则卡。连同原有ECC样例，目前共6份输入卡、9条默认禁用的draft规则。6份输入卡包含4个DCGM字段、Prometheus的up及设备预期配置；配置不是GPU监控指标。

| 规则 | 判据及边界 |
| --- | --- |
| [采集不可用](../rules/nvidia.collector_unavailable.md) | 已登记target的up缺失、失败或陈旧 |
| [设备观测消失](../rules/nvidia.expected_gpu_observation_missing.md) | 采集正常时，已登记GPU的四个观测字段均消失；不能据此断言物理掉卡 |
| [必需字段缺失](../rules/nvidia.required_field_missing.md) | 其他字段仍可见时缺少指定字段；整卡消失时抑制逐字段噪声 |
| [必需字段陈旧](../rules/nvidia.required_field_stale.md) | 可见原始样本超过90秒；stale标记后的消失由缺失规则处理 |
| [输入无效](../rules/nvidia.required_input_invalid.md) | 按字段类型识别NaN、Inf、blank和非法枚举/计数 |
| [重复采集](../rules/nvidia.duplicate_input_series.md) | 同集群、GPU、字段存在多个新鲜序列 |
| [SRAM超阈值](../rules/nvidia.sram_threshold_exceeded.md) | 有效、新鲜、唯一的官方布尔标志为1 |
| [行重映射失败](../rules/nvidia.row_remap_failed.md) | 有效、新鲜、唯一的失败标志为1；不以累计重映射数代替 |

输入说明见[温度](../../../common/monitoring/metrics/nvidia.gpu_temp.md)、[ECC计数](../../../common/monitoring/metrics/nvidia.ecc_dbe_volatile_total.md)、[SRAM标志](../../../common/monitoring/metrics/nvidia.sram_exceeded.md)、[重映射失败](../../../common/monitoring/metrics/nvidia.remap_failed.md)、[采集状态](../../../common/monitoring/metrics/prometheus.target_up.md)、[预期清单](../../../common/monitoring/metrics/inventory.expected_devices.md)。温度在本批用于观测与质量检查，尚未定义过温告警阈值。

## 绑定与适用性

[绑定文件](../catalog/batch1-binding.yaml)只包含fixture-cluster和两个GPU-FIXTURE UUID。表达式中的预期集合由静态向量表示，便于审阅；没有新增库存Exporter、生产发现逻辑或Prometheus recording rules。

四个观测字段为DCGM_FI_DEV_GPU_TEMP、DCGM_FI_DEV_ECC_DBE_VOL_TOTAL、DCGM_FI_DEV_SRAM_EXCEEDED、DCGM_FI_DEV_ROW_REMAP_FAILURE。字段395的header名称为ROW_REMAP_FAILED，所参考Exporter CSV名称为ROW_REMAP_FAILURE；字段346存在于header不能证明现场Exporter已采集。各卡分别记录来源和映射。

H100 PCIe/SXM/NVL逐形态支持均保留unknown，真实采集和硬件测试均为not_run。固定的驱动设计基线不代表现场已安装；MIG、标签、软件版本、库存及维护状态仍需核实。实验室SIMULATED-GPU没有改名为H100。

## 实际测试结果

使用Compose中的prom/prometheus:v3.2.1一次性容器执行promtool，两个测试文件均输出SUCCESS，退出码0。

| 测试集 | 用例 | 求值断言 | 结果 |
| --- | --- | --- | --- |
| 原有ECC | 18 | 31 | passed |
| 本批8条规则 | 49 | 392 | passed |
| 合计 | 67 | 423 | passed |

本批覆盖正常/异常布尔标志、NaN/正负Inf/blank/非法枚举、非法计数、有效负温度、采集失败与消失、字段/单卡/全卡缺失、陈旧样本、90秒边界、重复序列、跨集群与未登记GPU隔离、多个独立异常并存，以及异常后输入失效。每个用例同时断言8条规则的命中身份。未来时间戳有表达式防护，未单独完成未来样本注入测试。

测试发现并修复了先加工标签再取timestamp导致陈旧样本被视为新鲜的问题：现在先对原始序列取timestamp，再加工标签。整卡观测消失时逐字段缺失被抑制；重复字段阻止相应硬件判定，不阻止独立字段的异常。

[机器结果记录](h100_batch1-results.yaml)保存本批绑定和用例摘要。离线测试不执行夜莺for持续时间、告警状态机或通知。

## 你可以这样验证

在项目根目录执行：

```bash
bash modules/devices/nvidia-gpu/rules/scripts/test_monitoring.sh
python3 modules/devices/nvidia-gpu/rules/scripts/check_monitoring.py
python3 modules/devices/nvidia-gpu/rules/scripts/render_h100_inventory.py --check
```

第一条预期两次SUCCESS；只启动一次性只读测试容器，不重载现有服务。后两条在已有PyYAML的文档工具环境运行，预期PASS，分别检查卡片/表达式/测试引用一致性及台账生成一致性。

人工审阅建议依次检查：预期设备配置是不是配置输入；两条硬件规则是否只采用官方标志；各卡是否写清无效值、缺数、重复、适用性和处置步骤。正式目录仍禁用；后续已创建独立夜莺实验副本，见[流式验证指南](../../docs/08-H100草案流式模拟验证.md)。

## 下一道门禁

硬件告警触发后输入丢失，表达式可能退出；不能把夜莺的结束通知直接说成硬件恢复。配套质量告警尚不能替代结束原因状态管理，必须在接入时实现并测试。新规则默认保持disabled。

下一步先完成合成绑定到夜莺测试环境的安全适配、for/抑制/通知与结束语义联调，再推进剩余H100规则卡。真实型号准入、生产库存和维护绑定、查询/评估及通知自身健康仍未完成；本批不代表全部P0或H100覆盖完成。


## 后续运行引擎修正

2026-11-09流式联调发现离线测试引擎与运行引擎的指标名删除特性不同，相关表达式更新至0.1.1。现在逐字段取原始timestamp、写入常量metric_name后再合并；原67用例/423断言重新通过。详见[运行引擎回归与流式证据](../../docs/08-H100草案流式模拟验证.md)。以上离线passed不包含后续夜莺实验绑定的独立结果。
