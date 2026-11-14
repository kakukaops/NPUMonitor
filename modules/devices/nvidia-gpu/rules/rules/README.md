# 首批 GPU 模拟规则目录

**规范主清单：**[第14篇GPU监控指标与告警规则说明表](../docs/14-GPU监控指标与告警规则说明表.md)是GPU规则领域的唯一规范入口。本文说明或代码生成结果不替代主清单；当前实现范围和生产差距分别核对。

当前现场版本请使用[OS SRE无业务属性规则](../monitoring/os-sre/README.md)。下文保留历史草案或模拟绑定，不作为现场接入模板。

版本：lab-0.1.1；适用底座：Nightingale 9.3.0。

本目录仅用于模拟环境集成验证，尚未作为生产规则发布。实际 GPU 型号、Exporter 指标可用性、特殊值、真实故障恢复均未验证。温度 85°C、测试持续时间均是测试参数。

| 稳定规则键 | 输入和含义 | 判断 / 持续时间 | 恢复与缺数边界 | 测试场景 |
| --- | --- | --- | --- | --- |
| gpu_lab_temperature | GPU温度 gauge，°C | >85 且 <1000，持续30秒 | 正常温度使表达式退出；缺数也可能使底座结束实例，不得解释为硬件恢复 | hot / transient / sustained / normal |
| gpu_lab_xid79 | 最近XID gauge，值为错误码 | ==79，持续10秒 | 模拟清零验证输入恢复；真实XID可能保持最近值，恢复策略待核实 | xid / normal |
| gpu_lab_ecc_dbe | volatile DBE counter，次数 | 1分钟内 increase>0，持续10秒 | 窗口过后表示近期无新增，不代表硬件修复；缺失和sentinel不在本规则验证范围 | ecc / counter_reset |
| gpu_lab_scrape_down | Prometheus生成的up，0/1 | ==0，持续15秒 | up=1表示采集恢复，不表示GPU健康；target被移出配置时无序列，另需检测 | scrape_error / normal |
| gpu_lab_missing | 过去10分钟温度序列与当前序列 | 历史存在、当前消失且up=1，持续15秒 | 有限历史温度序列缺失，不确认物理掉卡；超过10分钟会退出，非硬件恢复 | missing / empty / normal |
| gpu_lab_invalid_temp | 温度 gauge 中 NaN | 与自身做bool比较后筛选结果=1，持续10秒 | 正常数值返回后退出；未覆盖Inf、全部DCGM sentinel或陈旧数据 | invalid / normal |

GPU指标的selector限定 job=gpu-simulator、cluster_id=gpu-sim-lab、simulated=true；up仅限定专用模拟job。所有规则追加模拟和管理标记。每卡身份使用 UUID；GPU序号只作展示。

目录 JSON 是此批规则的审定测试输入，导入适配器绑定专用业务组、数据源和通知规则。API导入成功不等于执行测试成功；验证状态分别记为表达式已检查、规则已导入、触发/恢复已观察。当前已在真实测试Prometheus上确认六条表达式均能执行且正常基线不命中，六条规则已通过API导入并验证重复执行无重复对象；温度规则已观察到触发及同hash恢复通知，其余五条规则及短暂高温、计数器重置也已验证；NaN初次失败后已修正并定向重测通过。见[验收报告](../docs/07-首批模拟规则验收报告.md)。

参考依据：

- [NVIDIA Exporter 字段类型配置](https://github.com/NVIDIA/dcgm-exporter/blob/main/etc/default-counters.csv)：温度、XID和ECC输入语义；字段仍需按真实版本核实。
- [NVIDIA XID 说明](https://docs.nvidia.com/deploy/xid-errors/introduction.html)：XID是诊断线索，不统一等同硬件故障。
- [Nightingale v9.3.0 AlertRule](https://github.com/ccfos/nightingale/blob/v9.3.0/models/alert_rule.go)：API规则字段及恢复配置。
- [Nightingale v9.3.0 Callback](https://github.com/ccfos/nightingale/blob/v9.3.0/models/notify_channel.go)：通知媒介和原始事件JSON请求。

本目录独立编写表达式与中文说明，没有复制上游规则文件或阈值。正式目录仍须建立逐型号兼容矩阵并固定所采用的输入资料版本。

## lab-0.1.1 无效输入检测修正

实测发现 `temperature != temperature` 虽能在Prometheus中匹配NaN，但返回样本值仍为NaN，夜莺未生成预期告警。改为 `(temperature != bool temperature) == 1` 后，异常输入返回有限值1，正常输入不命中。该修正仅改变无效温度规则，不改变温度超限规则或生产阈值。

已有lab-0.1.0环境可执行 `bash modules/devices/nvidia-gpu/rules/scripts/lab.sh repair-invalid`。脚本仅在旧表达式完全匹配且管理标记一致时更新，并保留其他字段；表达式有本地修改时拒绝覆盖。再次运行是幂等检查。这是明确的一次性实验规则迁移，不代表已实现通用目录升级合并。
