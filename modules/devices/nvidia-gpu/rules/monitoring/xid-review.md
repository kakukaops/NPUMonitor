# H100 XID 逐码审查台账

登记日期：2026-11-09；目录证据为2026-11-06滚动快照，并非重新抓取的当前全集。

2026-11-11 完成固定快照的 78 码分级草案。项目处置列用于人工分流。当前默认禁用通知，现场适用性仍待核验。

源页面SHA256：`ee085d5e99de9f4524ac6233f787eb59ddc382b55bfbcb29a49dd34982d82be2`；[官方目录](https://docs.nvidia.com/deploy/xid-errors/latest/analyzing-xid-catalog.html)。机器可读台账见[xid-review.yaml](catalog/xid-review.yaml)。

当前最近XID字段是gauge，不能保证scrape间所有事件、顺序、subcode或恢复动作均保存。不能用increase计算码值发生次数。通用文档中的XID160在该快照对H100=NO，不放入本表；不代表未来版本永远不适用。

| XID | 官方即时动作 | 官方调查动作 | XID 154 联动 | 项目处置 | 复核说明 |
| --- | --- | --- | --- | --- | --- |
| 8 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 11 | RESTART_APP | CHECK_APP/CUDA | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 13 | RESTART_APP | WORKFLOW_XID_13 | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 14 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 25 | RESTART_APP | CHECK_APP/CUDA | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 31 | RESTART_APP | WORKFLOW_XID_31 | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 32 | RESTART_APP | CHECK_APP/CUDA | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 37 | IGNORE | CHECK_APP/CUDA | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 38 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 39 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 40 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 41 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 43 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 44 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 45 | WORKFLOW_XID_45 | Solo: RESTART_FM Not Solo: IGNORE (follow other Xid) | 空白 | correlate_events | 检查是否伴随其他事件，孤立出现和伴随出现分别处置。 |
| 46 | RESET_GPU | CONTACT_SUPPORT | 空白 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 48 | WORKFLOW_XID_48 | WORKFLOW_XID_48 | CUDA 12.7; GPU driver R565 | correlate_events | 关联 ECC 计数、内存统计域和恢复动作，避免与同一故障重复呼叫。 |
| 54 | CHECK_MECHANICALS | CONTACT_SUPPORT | 空白 | node_incident_review | 按目录动作复核。 |
| 60 | RESTART_APP | INVESTIGATE_SW | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 62 | RESET_GPU | CONTACT_SUPPORT | CUDA 12.7; GPU driver R565 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 63 | IGNORE | IGNORE | CUDA 12.7; GPU driver R565 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 64 | RESET_GPU | CONTACT_SUPPORT | CUDA 12.7; GPU driver R565 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 66 | IGNORE | INVESTIGATE_SW | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 67 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 68 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 69 | RESTART_APP | CHECK_APP/CUDA | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 70 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 71 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 72 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 74 | WORKFLOW_NVLINK_ERR | CONTACT_SUPPORT | CUDA 12.7; GPU driver R565 | correlate_events | 结合链路两端和拓扑判断根因。 |
| 75 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 76 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 77 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 78 | UPDATE_SWFW | UPDATE_SWFW | 空白 | deployment_scope_review | 目录标为 vGPU 启动错误，若出现在当前物理卡训练范围应核查部署身份。 |
| 79 | RESTART_BM | CONTACT_SUPPORT | CUDA 12.7; GPU driver R565 | node_incident_review | 检查 PCIe 与系统日志，协调隔离节点和后续处置。 |
| 80 | RESTART_APP | CHECK_APP/CUDA | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 82 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 83 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 84 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 85 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 86 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 88 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 89 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 92 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 94 | RESTART_APP | IGNORE (sympathetic) | CUDA 12.7; GPU driver R565 | correlate_events | 结合受影响作业和伴随事件，先确认是否为主事件。 |
| 95 | RESET_GPU | IGNORE (sympathetic) | CUDA 12.7; GPU driver R565 | correlate_events | 确认受影响范围和主事件后再安排 GPU 恢复。 |
| 96 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 97 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 98 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 99 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 100 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 101 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 102 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 103 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 104 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 105 | RESTART_APP | CONTACT_SUPPORT | 空白 | training_job_review | 核对受影响作业，按调度和作业策略处置。 |
| 106 | IGNORE | IGNORE | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 107 | IGNORE | IGNORE | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 108 | IGNORE | XID_137_FLOW | 空白 | context_only | 目录标为未使用，保留异常观测供核查。 |
| 109 | RESET_GPU | CONTACT_SUPPORT | CUDA 12.7; GPU driver R570 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 110 | RESET_GPU | INVESTIGATE_SW | CUDA 12.7; GPU driver R565 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 119 | RESET_GPU | INVESTIGATE_SW | 空白 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 120 | RESET_GPU | INVESTIGATE_SW | CUDA 12.7; GPU driver R565 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 136 | RESET_GPU | INVESTIGATE_LINK_SI | CUDA 12.7; GPU driver R565 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 137 | IGNORE | XID_137_FLOW | 空白 | context_only | 保存 NVLink 远端访问和应用诊断上下文。 |
| 140 | RESET_GPU | CONTACT_SUPPORT | 空白 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 141 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 143 | RESET_GPU | CONTACT_SUPPORT | CUDA 12.9; GPU driver R575 | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 151 | RESTART_VM | CONTACT_SUPPORT | 空白 | deployment_scope_review | 官方动作为重启 VM。物理卡训练场景需先核实适用处置。 |
| 154 | XID_154 | N/A Informational only regarding another Xid | 空白 | correlate_events | 恢复动作变更摘要需要关联主事件和日志中的动作文本。 |
| 156 | RESET_GPU | IGNORE | CUDA 12.7; GPU driver R565 | correlate_events | 即时和调查动作不同，需保留完整事件上下文再安排处置。 |
| 157 | IGNORE | CONTACT_SUPPORT | 空白 | context_only | 保留供调查和事件关联，默认无独立通知。 |
| 158 | RESET_GPU | CONTACT_SUPPORT | yes; support with Xid introduction | gpu_reset_review | 由运维核查排空条件、恢复动作和维护窗口。 |
| 167 | 空白 | 空白 | 空白 | insufficient_guidance | 目录即时处置为空，保留观测供人工核对。 |
| 168 | 空白 | 空白 | 空白 | insufficient_guidance | 目录提示与 ECC 关闭有关，先核对 ECC 模式。 |
| 169 | 空白 | 空白 | 空白 | insufficient_guidance | 目录即时处置为空，保留观测供人工核对。 |
| 171 | 空白 | 空白 | 空白 | correlate_events | 与 XID 48 关联的 DRAM 明细。 |
| 172 | 空白 | 空白 | 空白 | correlate_events | 与 XID 48 关联的 SRAM 明细。 |
