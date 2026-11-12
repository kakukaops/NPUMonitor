# H100 ECC 统计域与 XID 逐码分级

2026-11-11。适用范围为 H100 物理卡训练，驱动参考基线沿用 R595.112.07。现场型号、MIG 模式和采集栈待核验。

## ECC 字段和查询

| 统计域 | SBE 易失 / 持久 | DBE 易失 / 持久 | 本批查询 |
| --- | --- | --- | --- |
| 汇总 | 310 / 312 | 311 / 313 | SBE 近期趋势、DBE 非零历史。311 沿用已有新增告警草案 |
| 设备内存 | 318 / 328 | 319 / 329 | SBE 近期趋势、DBE 近期明细和非零历史 |
| SRAM | 342 / 344 | 343 / 345 | SBE 近期趋势、DBE 近期明细和非零历史 |

编号来自固定 DCGM header。设备内存字段使用 `_DEV`，SRAM 字段使用 `_SRM`。参考 Exporter CSV 中四个汇总计数条目均为注释，八个分域条目均未列出。合成查询使用 header 名称作为样本名，现场接入需要实测指标名、单位和统计域。来源与逐字段映射见[指标台账](../../common/monitoring/metric-inventory.md)。

- DBE 持久计数大于零时展示历史值。长期保持非零仍属于历史。首次发现事件和基线变更需要额外记录。
- 近期视图使用各自易失计数的五分钟 `increase`。计数器下降按重置处理，外推值允许小数。SBE 趋势供观察，当前无统一硬件故障阈值。
- 汇总、设备内存和 SRAM 分列。现场需选定单一主告警来源。分域计数用于定位，避免把汇总与明细相加或重复通知。
- 查询要求已登记 GPU、健康采集目标、90 秒内的样本和唯一输入。当前计数须为非负整数，拒绝 sentinel、NaN 和无穷值。近期视图还验证窗口的样本数、最小值、最大值和求和。窗口历史样本的逐点整数验证仍待完成。
- 所有视图使用合成集群和 UUID。真实 H100 字段支持与采集配置仍待确认。查询定义见[草案目录](catalog/ecc-xid-review-queries.yaml)。

## XID 处置

重新取得的 NVIDIA 目录与 2026-11-06 快照 SHA256 一致。逐码草案覆盖该快照中 78 项 H100=YES，分别保存厂商即时动作、调查动作及 XID 154 联动列。项目分流包含作业复核 36 项、GPU 重置复核 11 项、节点事件复核 2 项、事件关联 9 项、调查上下文 15 项、部署范围复核 2 项、证据不足 3 项。厂商即时动作空白的五项中，171 和 172 按 XID 48 的内存域明细关联，其余三项保留证据不足。[逐码台账](xid-review.md) · [NVIDIA 官方目录](https://docs.nvidia.com/deploy/xid-errors/latest/analyzing-xid-catalog.html)

`DCGM_FI_DEV_XID_ERROR` 为字段 230 的 header 名，参考 Exporter 使用别名 `DCGM_FI_DEV_XID_ERRORS`，类型为 gauge。节点事件和 GPU 重置复核视图只匹配已审定代码，并检验目标、设备身份、新鲜度和输入唯一性。码值出现时间、同码重复发生次数、伴随事件及恢复动作仍需有序日志或现场遥测。XID 45、48、74、94、95、154 等需要关联上下文。分流标签用于人工处置，当前默认禁用通知。

## 验证

本批 8 条 ECC 诊断查询和 2 条 XID 复核查询通过 90 个固定样本。覆盖历史非零、近期增量、重置、陈旧、缺数、无效值、重复序列，以及高影响代码和上下文代码的分流。所有四批累计 169 个用例、537 项断言通过。[本批测试结果](tests/ecc-xid-review-results.yaml)

```bash
python3 modules/devices/nvidia-gpu/rules/scripts/build_h100_ecc_xid.py --check
python3 modules/devices/nvidia-gpu/rules/scripts/render_h100_inventory.py --check
bash modules/devices/nvidia-gpu/rules/scripts/test_monitoring.sh
```

前两项预期输出 PASS，Docker promtool 预期四次 SUCCESS。此次证据覆盖合成查询，夜莺流式验证和真实 H100 验证待完成。
