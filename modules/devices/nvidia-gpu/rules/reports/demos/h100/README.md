# H100综合规则实际演示记录

2026-11-11，独立Chrome临时会话访问本机综合演示页，点击首屏“一键演示”按钮。页面读取真实Prometheus求值、夜莺事件和本地Webhook，没有GPU硬件。

| 阶段 | 实际结果 | 画面 |
| --- | --- | --- |
| 正常基线 | 活动事件0，输入有效 | [正常](baseline.png) |
| GPU高温 | 持续条件满足后，活动事件ID 217 | [触发](active.png) |
| 设备观测消失 | 高温仍是217，新增观测消失事件218，输入为不可判定 | [缺数保持](missing.png) |
| 有效恢复 | 活动事件0；恢复历史记录220，与217的hash和原触发时间一致 | [恢复](recovered.png) |

触发通知217和恢复通知220均通过主Webhook实际投递。浏览器JavaScript异常为0。点击诊断查询按钮，25个视图均完成实际Prometheus求值，并验证正常温度等视图包含模拟GPU数值。

[事件与通知证据](demo-result.json) · [25项诊断查询结果](diagnostic-views.txt) · [完整验收记录](../../../monitoring/h100-training/acceptance-results.yaml)

现在打开 http://localhost:19430 可重放。演示结束已恢复正常输入，Docker Compose服务继续运行。

复核脚本为`modules/devices/nvidia-gpu/rules/scripts/demo_h100_browser.mjs`，使用Node 20的`--experimental-websocket`连接只监听本机9227端口的独立临时Chrome实例。端到端验收不依赖Chrome，CLI入口见[验证文档](../../../docs/10-H100综合规则与模拟验收.md)。
