# GPU生产指标主清单的候选覆盖复核

## 问题一：第14篇是否完整覆盖现有92项候选？

### Takeaway
尚未完整。按稳定metric_id和字段别名逐项核对，92项中82项为DCGM候选；第14篇覆盖37项当前契约、16项已建议的数值字段、3项泛化资产元数据，仍有26个原始字段未成条目。另10项为采集/资产/平台/业务/外部输入，其去向必须明确。[92项原始候选台账](../../../common/monitoring/catalog/metric-inventory.yaml)；[第14篇](../../docs/14-GPU监控指标与告警规则说明表.md)。

### Cited Findings
- 精确分布：`{"documented_metadata_planned": 3, "metadata_partial": 1, "missing_raw_field": 26, "documented_planned": 16, "current_contract": 37, "current_feature": 5, "current_blocked_feature": 1, "explicit_exclusion": 1, "external_gap": 2}`。映射依据当前字段契约、规则输入和第14篇每行首列，不能按全文中出现一次字段名就认定覆盖。[当前catalog](../../monitoring/os-sre/catalog.json)；[逐项JSON](inventory-crosswalk.json)。
- 三个资产字段driver/name/UUID在泛化资产段有说明，其中UUID身份已部分应用；这不等于三个字段都已采为独立Prom时序或具备资产视图。[第14篇第1节](../../docs/14-GPU监控指标与告警规则说明表.md#1-资产身份与配置)。
- 缺项主要是InfoROM、热余量/slowdown/shutdown、FM错误/掩码、P-state、PCIe最大能力、功率限制时长、ECC配置和历史可纠正细分、5个remap可用bank桶、交换机端口fatal/nonfatal与恢复动作等。[候选台账](../../../common/monitoring/catalog/metric-inventory.yaml)。

### Inferences
- 应为每个metric_id给出规范去向（必选/条件必选/可选/外部/排除）和独立实现状态，不将“未实现”当作排除理由。当前37不应改变成生产计划全部数量。
- 原92是历史候选台账而非GPU全部字段宇宙；没有证明只覆盖92就对任何型号和用途完整。完整性应限于明确基线及扩展审核过程。

### Gaps
- 候选台账各字段actual_collection、official_h100_field_support尚未知，不得把字段存在升级为目标设备支持。[候选状态](../../../common/monitoring/catalog/metric-inventory.yaml)。
- 交换机端口fatal/nonfatal原台账类型为unknown，禁止未经语义核实就当counter。[候选条目](../../../common/monitoring/catalog/metric-inventory.yaml)。

## 问题二：全部92项应怎样定义生产去向？

### Takeaway
下表给出92项的逐项设计建议；这是主清单规范提案，不是运行能力验收。必选项仍须经具体栈证据确认；条件项必须写出启用条件；不支持/未采集要展示缺口。[逐项完整JSON](inventory-crosswalk.json)。

### Cited Findings
生产要求建议统计：必选29、条件必选43、可选17、外部2、排除1；这是项目设计而非NVIDIA官方统一采集清单。[逐项JSON](inventory-crosswalk.json)。

| 稳定metric_id | 字段/输入 | 当前第14篇去向 | 生产要求建议 | 动作/边界 |
|---|---|---|---|---|
| `nvidia.driver_version` | `DCGM_FI_SYSTEM_DRIVER_VERSION` | documented_metadata_planned | 必选 | 资产概览第1节的配置/版本元数据，未列精确collector字段；需显式固定driver版本标签语义。 |
| `nvidia.gpu_name` | `DCGM_FI_DEV_GPU_NAME` | documented_metadata_planned | 必选 | 资产概览第1节设备身份元数据，未列精确GPU_NAME字段；不得把GPU名字当型号支持验证。 |
| `nvidia.gpu_uuid` | `DCGM_FI_DEV_GPU_UUID` | metadata_partial | 必选 | UUID已用于现有规则身份；独立资产概览和NVML/Exporter元数据接入覆盖尚未完备。 |
| `nvidia.inforom_valid` | `DCGM_FI_DEV_INFOROM_VALID` | missing_raw_field | 可选 | 管理固件有效性诊断缺口；失败、读不出、不支持必须区分，不能先设无效值=故障。 管理固件有效性诊断缺口；失败、读不出、不支持必须区分，不能先设无效值=故障。 |
| `nvidia.sm_clock` | `DCGM_FI_DEV_SM_CLOCK` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.mem_clock` | `DCGM_FI_DEV_MEM_CLOCK` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.clock_reasons` | `DCGM_FI_DEV_CLOCKS_EVENT_REASONS` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.memory_temp` | `DCGM_FI_DEV_MEMORY_TEMP_CELSIUS` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.gpu_temp` | `DCGM_FI_DEV_GPU_TEMP_CELSIUS` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.memory_max_temp` | `DCGM_FI_DEV_MEMORY_MAX_OP_TEMP_CELSIUS` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.gpu_max_temp` | `DCGM_FI_DEV_GPU_MAX_OP_TEMP_CELSIUS` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.gpu_temp_margin` | `DCGM_FI_DEV_GPU_TEMP_MARGIN_CELSIUS` | missing_raw_field | 条件必选 | 温度余量用于在硬件降速门槛附近监控，当前最大运行温度规则不能覆盖全部slowdown边界。 温度余量用于在硬件降速门槛附近监控，当前最大运行温度规则不能覆盖全部slowdown边界。 |
| `nvidia.board_power` | `DCGM_FI_DEV_BOARD_POWER_WATTS` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.board_power_raw` | `DCGM_FI_DEV_BOARD_POWER_RAW_WATTS` | missing_raw_field | 可选 | 与平均/采样功率口径区别大、并非必需重复采集；作为具体版本支持下的诊断增强。 与平均/采样功率口径区别大、并非必需重复采集；作为具体版本支持下的诊断增强。 |
| `nvidia.slowdown_temp` | `DCGM_FI_DEV_GPU_TEMP_SLOWDOWN_CELSIUS` | missing_raw_field | 条件必选 | 热降速边界与最大运行温度/关机门槛不同，需文档明确语义和适用硬件。 热降速边界与最大运行温度/关机门槛不同，需文档明确语义和适用硬件。 |
| `nvidia.shutdown_temp` | `DCGM_FI_DEV_GPU_TEMP_SHUTDOWN_CELSIUS` | missing_raw_field | 可选 | 用于风险展示的设备门槛，不把达到停机门槛当作唯一热告警时机。 用于风险展示的设备门槛，不把达到停机门槛当作唯一热告警时机。 |
| `nvidia.requested_power_limit` | `DCGM_FI_DEV_BOARD_POWER_LIMIT_REQUESTED_WATTS` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.enforced_power_limit` | `DCGM_FI_DEV_BOARD_POWER_LIMIT_ENFORCED_WATTS` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.fm_status` | `DCGM_FI_DEV_FABRIC_MANAGER_STATUS` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.fm_error` | `DCGM_FI_DEV_FABRIC_MANAGER_ERROR` | missing_raw_field | 条件必选 | Fabric Manager具体错误码是状态异常后的补充解释；不是累计次数。 Fabric Manager具体错误码是状态异常后的补充解释；不是累计次数。 |
| `nvidia.fabric_health_mask` | `DCGM_FI_DEV_FABRIC_HEALTH_MASK` | missing_raw_field | 条件必选 | Fabric健康位掩码提供明细；不能把数值大小当严重度，也不能与summary枚举混用。 Fabric健康位掩码提供明细；不能把数值大小当严重度，也不能与summary枚举混用。 |
| `nvidia.fabric_health_summary` | `DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.pstate` | `DCGM_FI_DEV_GPU_PSTATE` | missing_raw_field | 可选 | 性能状态枚举是时钟/节能背景，P0并非必定最佳且高P值并不自动等于故障。 性能状态枚举是时钟/节能背景，P0并非必定最佳且高P值并不自动等于故障。 |
| `nvidia.pcie_replay` | `DCGM_FI_DEV_PCIE_REPLAY_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.gpu_util` | `DCGM_FI_DEV_GPU_UTIL` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.mem_copy_util` | `DCGM_FI_DEV_MEM_COPY_UTIL` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.xid_last` | `DCGM_FI_DEV_XID_ERROR` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.pcie_max_gen` | `DCGM_FI_DEV_PCIE_MAX_LINK_GEN` | missing_raw_field | 条件必选 | 设备可支持的最大PCIe代际用于能力展示，但不等价于OS插槽/拓扑的预期协商代际。 设备可支持的最大PCIe代际用于能力展示，但不等价于OS插槽/拓扑的预期协商代际。 |
| `nvidia.pcie_max_width` | `DCGM_FI_DEV_PCIE_MAX_LINK_WIDTH` | missing_raw_field | 条件必选 | 设备可支持的最大lane数用于能力展示，静态资产目标仍要考虑主板/拓扑限制。 设备可支持的最大lane数用于能力展示，静态资产目标仍要考虑主板/拓扑限制。 |
| `nvidia.pcie_gen` | `DCGM_FI_DEV_PCIE_LINK_GEN` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.pcie_width` | `DCGM_FI_DEV_PCIE_LINK_WIDTH` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.power_violation_ns` | `DCGM_FI_DEV_POWER_VIOLATION` | missing_raw_field | 可选 | 功率限制累计时长提供状态持续性证据，Power Cap位并不等于供电故障。 功率限制累计时长提供状态持续性证据，Power Cap位并不等于供电故障。 |
| `nvidia.thermal_violation_ns` | `DCGM_FI_DEV_THERMAL_VIOLATION` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.fb_free` | `DCGM_FI_DEV_FB_FREE` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.fb_used` | `DCGM_FI_DEV_FB_USED` | documented_planned | 必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.ecc_mode` | `DCGM_FI_DEV_ECC_MODE` | missing_raw_field | 条件必选 | ECC配置背景缺口；不支持或缺失不能解释成ECC关闭。 ECC配置背景缺口；不支持或缺失不能解释成ECC关闭。 |
| `nvidia.ecc_pending` | `DCGM_FI_DEV_ECC_PENDING` | missing_raw_field | 条件必选 | 待生效ECC配置，须与当前模式分开；配置不生效可能需要维护，不直接判卡坏。 待生效ECC配置，须与当前模式分开；配置不生效可能需要维护，不直接判卡坏。 |
| `nvidia.ecc_sbe_volatile` | `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.ecc_dbe_volatile_total` | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.ecc_sbe_aggregate` | `DCGM_FI_DEV_ECC_SBE_AGG_TOTAL` | missing_raw_field | 可选 | 完整内存可靠性视图应交代历史可纠正错误；默认只诊断，不以历史累计非零呼叫。 完整内存可靠性视图应交代历史可纠正错误；默认只诊断，不以历史累计非零呼叫。 |
| `nvidia.ecc_dbe_aggregate` | `DCGM_FI_DEV_ECC_DBE_AGG_TOTAL` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.dram_sbe_volatile` | `DCGM_FI_DEV_ECC_SBE_VOL_DEV` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.dram_dbe_volatile` | `DCGM_FI_DEV_ECC_DBE_VOL_DEV` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.dram_sbe_aggregate` | `DCGM_FI_DEV_ECC_SBE_AGG_DEV` | missing_raw_field | 可选 | DRAM历史可纠正错误分布为诊断补充；不能当近期错误速率。 DRAM历史可纠正错误分布为诊断补充；不能当近期错误速率。 |
| `nvidia.dram_dbe_aggregate` | `DCGM_FI_DEV_ECC_DBE_AGG_DEV` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.sram_sbe_volatile` | `DCGM_FI_DEV_ECC_SBE_VOL_SRM` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.sram_dbe_volatile` | `DCGM_FI_DEV_ECC_DBE_VOL_SRM` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.sram_sbe_aggregate` | `DCGM_FI_DEV_ECC_SBE_AGG_SRM` | missing_raw_field | 可选 | SRAM历史可纠正错误分布为诊断补充；与uncorrectable错误及SRAM超阈值标志区分。 SRAM历史可纠正错误分布为诊断补充；与uncorrectable错误及SRAM超阈值标志区分。 |
| `nvidia.sram_dbe_aggregate` | `DCGM_FI_DEV_ECC_DBE_AGG_SRM` | current_contract | 可选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.sram_exceeded` | `DCGM_FI_DEV_SRAM_EXCEEDED` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.remap_bank_max` | `DCGM_FI_DEV_BANK_REMAP_AVAIL_MAX` | missing_raw_field | 条件必选 | 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 |
| `nvidia.remap_bank_high` | `DCGM_FI_DEV_BANK_REMAP_AVAIL_HIGH` | missing_raw_field | 条件必选 | 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 |
| `nvidia.remap_bank_partial` | `DCGM_FI_DEV_BANK_REMAP_AVAIL_PARTIAL` | missing_raw_field | 条件必选 | 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 |
| `nvidia.remap_bank_low` | `DCGM_FI_DEV_BANK_REMAP_AVAIL_LOW` | missing_raw_field | 条件必选 | 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 |
| `nvidia.remap_bank_none` | `DCGM_FI_DEV_BANK_REMAP_AVAIL_NONE` | missing_raw_field | 条件必选 | 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 完整行重映射资源视图中的bank可用性桶；反映剩余冗余资源分布，不是当前错误次数，告警阈值不能拍定。 |
| `nvidia.remapped_uncorrectable` | `DCGM_FI_DEV_ROW_REMAP_UNCORRECTABLE_TOTAL` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.remapped_correctable` | `DCGM_FI_DEV_ROW_REMAP_CORRECTABLE_TOTAL` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.remap_failed` | `DCGM_FI_DEV_ROW_REMAP_FAILED` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.remap_pending` | `DCGM_FI_DEV_ROW_REMAP_PENDING` | current_contract | 必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.nvlink_crc` | `DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.nvlink_recovery` | `DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.nvlink_replay` | `DCGM_FI_DEV_NVLINK_REPLAY_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.switch_link_fatal` | `DCGM_FI_DEV_NVSWITCH_LINK_FATAL_ERRORS` | missing_raw_field | 条件必选 | 已有候选记录明确字段类型未知；需确认是状态/错误码/掩码/计数，未核实前禁止rate/increase和统一数值阈值。 已有候选记录明确字段类型未知；需确认是状态/错误码/掩码/计数，未核实前禁止rate/increase和统一数值阈值。 |
| `nvidia.switch_link_nonfatal` | `DCGM_FI_DEV_NVSWITCH_LINK_NON_FATAL_ERRORS` | missing_raw_field | 条件必选 | 已有候选记录明确字段类型未知；不能仅凭ERRORS名称当counter。 已有候选记录明确字段类型未知；不能仅凭ERRORS名称当counter。 |
| `nvidia.switch_link_replay` | `DCGM_FI_DEV_NVSWITCH_LINK_REPLAY_ERROR_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.switch_link_recovery` | `DCGM_FI_DEV_NVSWITCH_LINK_RECOVERY_ERROR_TOTAL` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.sxid_fatal` | `DCGM_FI_DEV_SXID_FATAL_ERROR` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.sxid_nonfatal` | `DCGM_FI_DEV_SXID_NON_FATAL_ERROR` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.switch_temp` | `DCGM_FI_DEV_NVSWITCH_TEMP_CELSIUS` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.switch_slowdown_temp` | `DCGM_FI_DEV_NVSWITCH_TEMP_SLOWDOWN_CELSIUS` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.switch_link_state` | `DCGM_FI_DEV_NVSWITCH_LINK_STATUS` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.gr_engine_ratio` | `DCGM_FI_PROF_GR_ENGINE_UTIL_RATIO` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.sm_active_ratio` | `DCGM_FI_PROF_SM_UTIL_RATIO` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.sm_occupancy_ratio` | `DCGM_FI_PROF_SM_OCCUPANCY_RATIO` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.tensor_active_ratio` | `DCGM_FI_PROF_TENSOR_UTIL_RATIO` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.dram_active_ratio` | `DCGM_FI_PROF_DRAM_UTIL_RATIO` | documented_planned | 条件必选 | 第14篇已作为补充建议列出，但当前OS SRE未纳入字段契约/采集接入/规则。 |
| `nvidia.pcie_tx_rate` | `DCGM_FI_PROF_PCIE_TX_BYTES` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.pcie_rx_rate` | `DCGM_FI_PROF_PCIE_RX_BYTES` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.nvlink_link_state` | `DCGM_FI_DEV_NVLINK_LINK_STATUS` | current_contract | 条件必选 | 现有37字段契约之一；应保留具体规则或仅诊断角色，不代表已验证真实硬件适用性。 |
| `nvidia.recovery_action` | `DCGM_FI_DEV_GPU_RECOVERY_ACTION` | missing_raw_field | 条件必选 | 驱动报告的建议恢复动作可补XID处理，但新字段1523的存在不保证目标旧栈支持，不自动执行动作。 驱动报告的建议恢复动作可补XID处理，但新字段1523的存在不保证目标旧栈支持，不自动执行动作。 |
| `nvidia.power_throttle_seconds` | `DCGM_FI_DEV_GPU_POWER_THROTTLE_SECONDS_TOTAL` | missing_raw_field | 可选 | 字段1617是旧240ns字段的版本化替代候选；只选支持的一种并显式换算，不双计。 字段1617是旧240ns字段的版本化替代候选；只选支持的一种并显式换算，不双计。 |
| `nvidia.thermal_throttle_seconds` | `DCGM_FI_DEV_GPU_THERMAL_THROTTLE_SECONDS_TOTAL` | missing_raw_field | 可选 | 字段1618是旧241ns字段的版本化替代候选；不得将秒和ns仅通过别名互换。 字段1618是旧241ns字段的版本化替代候选；不得将秒和ns仅通过别名互换。 |
| `prometheus.target_up` | `scrape_status` | current_feature | 必选 | Prometheus自动up是当前采集可用性规则输入，不属于37个DCGM字段。 |
| `inventory.expected_devices` | `configuration` | current_feature | 必选 | 现有OS静态预期GPU/交换机清单和entity_missing规则；不能从历史观测自动推导永久资产。 |
| `inventory.hardware_stack` | `configuration` | documented_metadata_planned | 必选 | 已有声明契约选择与版本说明，不等于运行中的型号/驱动/DCGM/Exporter版本自动盘点。 |
| `inventory.expected_links` | `configuration` | current_feature | 条件必选 | 预期启用端口及PCIe/Fabric资产清单已有；是否覆盖全资产需另外核对。 |
| `prometheus.field_quality` | `derived_query` | current_feature | 必选 | 现有缺失/陈旧/非法/重复/身份规则覆盖当前37字段；新增字段须扩展契约，不能声称自动覆盖。 |
| `platform.evaluation_status` | `platform_api_or_metrics` | current_feature | 必选 | 夜莺规则评估与数据查询计数器已有规则；不代替所有评估路径的执行SLA。 |
| `platform.notification_status` | `platform_api_or_metrics` | current_blocked_feature | 必选 | 通知失败规则已有记录但因实际发送路径无可信counter覆盖而禁用；必选监控目标不等于已满足。 |
| `training.job_context` | `external_context` | explicit_exclusion | 排除 | 当前OS SRE拿不到业务作业/调度上下文，明确不纳入GPU规则基线；不以其缺失阻塞其他观测。 |
| `host.power_context` | `external_context` | external_gap | 外部 | 电源/风扇/环境温度/PSU/供电事件依赖BMC/Redfish/IPMI或主机采集，不假造DCGM字段。 |
| `diagnostics.results` | `external_diagnostic` | external_gap | 外部 | DCGM主动诊断结果是独立运维/维护输入，不等于被动时序指标；需记录运行时间/测试/结果/影响，不能默认带载运行。 |

### Inferences
- 基础物理GPU身份、资产版本、基本温度、利用率/容量/功率/时钟、错误事件及监控质量应形成首发必选目标；NVLink/NVSwitch/Fabric按真实拓扑和预期启用，Profiling按能力和权限启用。
- ECC历史分布及P-state、原始功率等增强可视化可列可选；可选不等于不重要，而是不能成为所有平台强制可采项。
- 本期继续不做跨规则关联和通知收敛，不能通过删掉重叠指标冒充完整。

### Gaps
- 单个状态/阈值/枚举是否值得通知、默认严重度、有效恢复条件还需生产策略审定；不能从字段数量推导告警条数。
- NVLink1508的多态定义须绑定驱动/NVML版本。父任务语义复核指出NVML620新增状态3；不能未经核实套在R595基线上。SLEEP=2可能正常，既有>0解除应由具体健康定义审定，不能一概宣称正确或错误。

## 问题三：92项之外还应显式审核什么？

### Takeaway
至少需要复核下面已知字段/口径与外部边界；92项之外不是默认排除。特别是字段254的alias名字包含PERCENT，但固定头文件规范是0..1比例、分母扣除reserved，与第14篇USED/TOTAL派生比例不同。[固定头文件](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L918)。

### Cited Findings
| 补充对象 | 建议去向及语义 | 固定来源 |
|---|---|---|
| `DCGM_FI_DEV_FB_TOTAL`（250） | 必选；已在14建议项；设备报告framebuffer总量MiB，不保证等于板卡标称或进程可分配总量。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L897) |
| `DCGM_FI_DEV_FB_RESERVED`（253） | 必选；已在14建议项；系统/驱动预留MiB，定义容量比例时须交代扣除口径。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L915) |
| `DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION`（156） | 可选；已在14建议项；mJ累计counter；新版J字段不能仅改名，存在reset。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L656) |
| `DCGM_FI_PROF_NVLINK_TX_BYTES`（1011） | 条件必选；已在14建议项；bytes/s gauge，Profiling支持/权限/粒度须确认，不因BYTES名称就rate。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L2682) |
| `DCGM_FI_PROF_NVLINK_RX_BYTES`（1012） | 条件必选；已在14建议项；bytes/s gauge，同上，不与aggregate throughput重复相加。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L2690) |
| `DCGM_FI_DEV_NVLINK_THROUGHPUT_TOTAL`（449） | 可选；已在14建议项的采集别名NVLINK_BANDWIDTH_TOTAL；固定CSVgauge MB/s，不能混其他版本counter。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L1491) |
| `DCGM_FI_DEV_MEMORY_UNREPAIRABLE`（1507） | 条件必选；新增缺口；官方1=yes/0=no布尔，别名MEMORY_UNREPAIRABLE_FLAG；目标栈支持未证实，非不支持即健康。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L3503) |
| `DCGM_FI_DEV_FB_USED_RATIO`（254） | 可选；新增替代/对照口径；固定头文件0..1且Used/(Total-Reserved)，别名FB_USED_PERCENT。与项目USED/TOTAL派生比例不是同一分母，名字PERCENT不能证明单位是0..100。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L920) |
| `DCGM_FI_DEV_PAGE_RETIRED_SBE_TOTAL`（390） | 条件/旧架构；旧架构页退休兼容项；H100主路径以row-remap为准，先明确型号支持。若选用为monotoniccount，而不是现有坏页总数/错误码。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L1278) |
| `DCGM_FI_DEV_PAGE_RETIRED_DBE_TOTAL`（391） | 条件/旧架构；同上，double-bit引起的退休页累计数；不与H100row-remap资源一一等价。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L1284) |
| `DCGM_FI_DEV_PAGE_RETIRED_PENDING`（392） | 条件/旧架构；同上，bool待退休，不是count；H100不强制套用旧架构语义。 | [字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h#L1289) |

### Inferences
- 完整XID/SXID事件记录：必选采集目标；现有最近码不是完整流；日志/DCGM事件接口待实现，不能依赖数值变化计事件。
- PCIe AER与主机电源/风扇/PSU/环境：外部/条件；由主机日志或BMC采集，H100被动散热无GPU风扇读数不能当0转速故障。
- MIG/vGPU租户资源：当前物理H100基线外；MIG模式元数据需识别并显式不支持，不能把物理FB总量当每实例容量。
- 应用性能tokens/s、step time、队列与调度状态：明确排除当前OS SRE基线，不能无业务上下文发明告警。
- 主动DCGM诊断：外部维护工作流，不自动等价生产在线采集；不在本次文档复核新增执行动作。

### Gaps
- 本轮不声称穷尽任何未来GPU/DCGM版本全部字段。每次增加型号、架构、MIG或新特性，必须按同一主清单变更流程补适用性与字段去向。
- 固定头文件名称/alias/单位与目标版本可能不同，尤其能耗mJ/J、显存MiB/bytes、频率MHz/Hz、percent/ratio、计时ns/seconds，不可只通过metric_aliases改名。既有候选已列版本风险。[固定字段定义](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)；[第14篇](../../docs/14-GPU监控指标与告警规则说明表.md)。
