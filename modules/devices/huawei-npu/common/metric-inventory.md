# A3指标候选速览（旧26项子集）

新分类与采集路径见[0.2版主表](../rules/docs/01-A3-NPU监控指标与告警规则说明表.md)。本表保留早期子集，不作为完整覆盖范围。

结构化规范见[catalog/metrics.yaml](catalog/metrics.yaml)。所有字段采集验证均未执行；unknown不是不支持。单位不明的字段不能参与阈值计算。

| 原始指标 | 含义 | 单位 | 来源ID |
| --- | --- | --- | --- |
| `up` | Exporter抓取状态 | boolean | metrics |
| `machine_npu_nums` | 当前枚举芯片数 | count | npu |
| `machine_card_nums` | 当前板卡数 | count | npu |
| `machine_healthy_npu_nums` | 健康芯片数 | count | npu |
| `machine_unhealthy_npu_nums` | 不健康芯片数 | count | npu |
| `machine_unknown_npu_nums` | 健康未知芯片数 | count | npu |
| `npu_chip_info_health_status` | Exporter芯片健康 | boolean | npu, constants |
| `npu_chip_info_network_status` | Exporter网络健康 | boolean | npu, constants |
| `npu_chip_info_temperature` | 芯片温度 | unknown | npu, constants |
| `npu_chip_info_power` | 芯片功率 | unknown | npu, constants |
| `npu_chip_info_voltage` | 芯片电压 | unknown | npu, constants |
| `npu_chip_info_aicore_current_freq` | AI Core当前频率 | MHz | npu, constants |
| `npu_chip_info_process_info_num` | 设备进程数量 | count | npu, constants |
| `npu_chip_info_hbm_used_memory` | HBM已用容量 | unknown | hbm |
| `npu_chip_info_hbm_total_memory` | HBM总容量 | unknown | hbm |
| `npu_chip_info_hbm_utilization` | HBM利用率 | unknown | hbm |
| `npu_chip_info_hbm_temperature` | HBM温度 | unknown | hbm |
| `npu_chip_info_hbm_bandwidth_utilization` | HBM带宽利用率 | unknown | hbm |
| `npu_chip_info_hbm_ecc_enable_flag` | HBM ECC开关 | enum | hbm |
| `npu_chip_info_hbm_ecc_single_bit_error_cnt` | HBM单比特错误数 | count | hbm |
| `npu_chip_info_hbm_ecc_double_bit_error_cnt` | HBM多比特错误数 | count | hbm |
| `npu_chip_info_hbm_ecc_total_single_bit_error_cnt` | HBM历史单比特错误数 | count | hbm |
| `npu_chip_info_hbm_ecc_total_double_bit_error_cnt` | HBM历史多比特错误数 | count | hbm |
| `npu_chip_info_hbm_ecc_single_bit_isolated_pages_cnt` | HBM单比特隔离页数 | pages | hbm |
| `npu_chip_info_hbm_ecc_double_bit_isolated_pages_cnt` | HBM多比特隔离页数 | pages | hbm |
| `npu_chip_info_error_code` | 错误码第一槽位 | event_code | npu, codes |

来源ID对应[catalog/sources.yaml](catalog/sources.yaml)。`raw_type`均等待固定发行版实际HELP/TYPE核对。
