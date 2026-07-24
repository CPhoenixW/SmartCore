# 智能体操作与输出（历史）

该文档记录了早期 Action、待确认操作和 `/dashboard` 设计。当前系统已改为
`/work`、受限 Agent API、直接执行配合撤销/审计，以及统一结果协议。

现行依据：

- 工具发现：`GET /agent/tools`
- 结果协议：[action-result-protocol.md](./action-result-protocol.md)
- OpenClaw 边界：[09-openclaw-smartcore-bridge.md](./09-openclaw-smartcore-bridge.md)
- 提醒投递：Server scheduler 决策，副屏优先或飞书回退，并写入审计日志。

历史字段和路由不得用于新增实现。
