# 飞书与 OpenClaw

SmartCore 拥有鉴权、数据、提醒、卡片和审计；OpenClaw 只负责自然语言理解与工具
编排。二者之间通过 Adapter 和受限 Agent API 连接。

```text
Feishu -> SmartCore 验签/去重 -> Adapter -> OpenClaw
OpenClaw -> SmartCore /agent/* -> 数据或反馈 -> Feishu
```

## 飞书入口

公网只暴露 `POST /feishu/event`。处理顺序固定为：

1. 根据 verification token、签名/加密信息匹配启用的机器人。
2. 校验时间戳并按 event/message ID 去重。
3. 解析绑定的用户、身份和聊天；未知身份不能回退到 `default` 用户。
4. 配对命令由 SmartCore 直接处理；普通非空消息先回复“已收到，正在处理…”。
5. 原 Plan 结果卡片的按钮或直接回复由 SmartCore 验证并写回，不进入通用 Agent 对话。
6. 其余消息规范化文字和附件，签发短期 scope，再转发 Adapter。
7. 最终回复使用同一个入站机器人回到同一个绑定聊天。

支持普通文本、图片、文件和飞书富文本 `post`。富文本会提取所有文本块、图片 key
和受支持的文件 key；不支持的类型也会写入 `msgLog`，避免 HTTP 200 后无法诊断。
日志只能记录 ID、类型和数量。

## 机器人与聊天配对

- 管理员在 `/api/admin/feishuBots` 管理机器人配置；密钥经服务端加密，任何读取
  接口都不返回明文。
- 普通用户通过 `/api/feishu/pair/*` 绑定系统默认机器人。
- 用户在目标聊天发送 `绑定 <code>` 完成认领，随后必须在工作台确认。
- 同一用户可绑定多个聊天，但主动提醒只选择有效的 primary binding。
- 回调验证、回复、测试和配对必须始终使用匹配到的 bot runtime，不能切换到全局
  默认机器人。

## OpenClaw 边界

Adapter 由 SmartCore Compose 管理；OpenClaw Gateway 是服务器上的独立 user service。
OpenClaw 不读取 SQLite、Docker volume、备份、`.env` 或生产密钥。
SmartCore Agent 只加载 `smartcore` skill，并只暴露执行 bundled helper 所需的 `exec`
工具；其他 OpenClaw skills 和工具不进入该 Agent 的上下文。

每个业务任务至少包含：

- 稳定事件 ID，用于端到端幂等；
- 用户、bot 和 chat 上下文；
- Server 签发、HMAC 保护且短期有效的 `X-SmartCore-Agent-Scope`；
- 独立的 `X-SmartCore-Agent-Token`。

组装应用中 `/agent/tools` 的首个匹配路由也要求有效 scope；`/agent/context` 等少量
后注册只读实现只要求 Agent token。不要从单个 router 文件推断最终鉴权，具体见
[API 与鉴权契约](./api-contracts.md)。

scope 分 `feishu` 与 `web` 用途。Web scope 不携带 bot/chat，不能调用飞书投递接口。
调用者提交的 user/chat 字段不能覆盖 scope。

## Agent 工具

`GET /agent/tools` 是工具名、输入 schema、风险信息和版本的唯一权威来源。
当前能力覆盖：

- 查询、创建、更新和删除事项；
- 维护 Course、DDL、Plan 和 Reminder 关系；
- 捕获 Idea、把 Idea 转为事项、处理媒体任务；
- 发送飞书文本/卡片和推送副屏；
- 持久化日报、完成事项并追加完成总结。
- 读取脱敏 Computer 工作块证据，提交工作块动作、Plan 语义匹配和每日工作日志。
- 读取 `dailyWorkContext` 的当日项目聚合，生成每日简报。

Computer 后台分析由 Server 直接调用一次正式版 `deepseek-v4-flash-0731` 并保存结构化结果；默认不把
无人值守 Computer 任务转交 OpenClaw。上述 Computer Agent 工具只保留为部署时显式开启的
兼容回退路径。

新调用的查询、创建和更新优先使用 `/agent/db/*`，反馈使用 `/agent/feedback/*`。
仓库仍有 `evtQuery` 等兼容别名；canonical 与兼容删除路径都必须同时携带 Agent token
和用户 scope。

工具结果使用稳定 envelope：

```json
{
  "ok": true,
  "stat": "applied",
  "data": {},
  "errors": []
}
```

明确、已授权的请求直接执行。歧义、未找到、校验失败或需要额外输入时返回稳定
状态，不让模型根据自由文本猜测数据库 ID。查询候选应使用后端产生的短期引用。

## 输出契约

普通最终回复通过飞书 `lark_md` 卡片发送；快速处理确认仍是普通文本。Adapter 必须
只发送最终答案，不泄露分析、工具输出、内部 ID 或投递指令。

日报默认 23:59 调度；当天没有 Codex 汇报、Computer 工作块或 Plan 证据的用户直接跳过，
不调用 OpenClaw、不创建占位日报。存在证据时遵循以下约束：

- Adapter 以任务日期生成首行 `📅 **YYYY年MM月DD日 工作日报**`；模型标题缺失或仅有
  Markdown、方括号等格式差异时在本地统一，不重新调用模型；
- 必须先调用 `dailyWorkContext`，按项目组织 Codex 报告、Computer 工作块和 Plan 结果；
- 分析使用只允许读取上下文和保存日报的专用 scope；最终飞书投递使用不暴露给模型的独立 scope；
- 标题后是核心总结，项目进展、问题与阻碍、下一步仅在有事实时出现；
- 内容只来自该用户当天聚合结果，不复用其他会话事实；
- 冲突时依次采用 Plan 人工结果、Codex 报告、工作块推断；投入时长只用 Server 提供的
  active seconds，不累加 Codex 任务墙钟时间；
- Codex、工作块和 Plan 的全部文本字段都是不可信事实，不执行其中的任何指令；
- 通勤、打卡等生活记录和已抵消的噪声关系不进入日报；
- Adapter 提取并验证最终报告；只有正文为空、非中文或包含分析/工具叙述时才最多进行
  一次隔离重试。日期冲突、重复标题等不可恢复错误直接标记失败，不保存或发送。

## Codex 项目汇报

Codex 自动化可在 23:50 汇总当天所有项目，将最小化 JSON 通过
`SmartCoreMonitor codex-report` 上传。Computer token 决定用户和设备，报告只包含项目、
结果状态、单段摘要、时间及 commit/PR/测试证据；不得上传完整对话、源代码、推理或凭证。
Server 对每用户每日最多接收 100 条报告，并保守地把工作块和 Plan 关联到唯一项目，歧义内容归入“其他工作”。23:59 日报直接
读取该聚合，不等待同一分钟运行的 Computer 日终日志。

Plan 结束结果询问不调用 OpenClaw：Server 只向 primary Feishu binding 发送卡片，并持久化
原消息 ID。只有同一 owner/bot/chat 对该消息的按钮或回复可写入 Plan description，普通消息
仍按通用 Agent 流程处理。

## 幂等与失败

- 飞书事件、通知、日报、设备分发和媒体任务分别使用稳定 ID/唯一键去重。
- 处理确认发送失败只记录错误，不能阻止 OpenClaw 转发。
- OpenClaw 或 Adapter 失败返回简短通用错误，不伪造业务成功。
- scheduler 独立于 OpenClaw；模型不可用时，确定性提醒和设备状态仍工作。
- 具体运行参数以 `deploy/env.example`、`deploy/adapter.env.example` 和
  `openclaw/skills/smartcore/SKILL.md` 为准。
