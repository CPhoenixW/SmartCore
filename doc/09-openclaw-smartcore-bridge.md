# OpenClaw 与 SmartCore

SmartCore 拥有数据、权限、提醒、飞书卡片和审计；OpenClaw 只负责自然语言理解与
多步编排。

```text
Feishu -> SmartCore 验签/去重 -> Adapter -> OpenClaw
OpenClaw -> SmartCore Agent API -> 数据或反馈 -> Feishu
```

## 边界

- Adapter 由 SmartCore Compose 管理；Gateway 是服务器 host user service。
- OpenClaw 只能使用 Agent token 调用 `/agent/*`，不能读取 SQLite、卷、备份或 `.env`。
- 转发事件携带稳定事件 ID、用户/聊天上下文、时间和短期 scope，不携带服务密钥。
- SmartCore scheduler 独立运行；OpenClaw 不参与每分钟提醒扫描。
- 转发失败必须记录并快速应答飞书，避免 webhook 重试风暴。

工具发现入口为 `GET /agent/tools`。具体工具名、输入和结果格式以该接口、
`openclaw/skills/smartcore/SKILL.md` 和 [Action 结果协议](./action-result-protocol.md)
为准，文档不重复硬编码列表。

SmartCore 内部模型调用统一经过 `app/server/llm/gateway.py`；OpenClaw 的模型与密钥
在其自身运行环境配置，不能从 SmartCore 事件透传。
