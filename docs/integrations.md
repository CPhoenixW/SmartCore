# PWA 与 DSH

SmartCore 负责鉴权、数据、提醒、审计和 PWA 工作台；DSH 只负责会话、模型调用与受限 MCP
工具编排。二者之间通过 DSH bridge 和 Agent scope 连接，PWA 是唯一交互入口。

```text
PWA -> SmartCore browser session -> DSH bridge -> DSH -> SmartCore /agent/*
DSH -> SmartCore /agent/* -> 数据；Server -> PWA/Screen -> 用户
```

助手对话、Idea、事项、日报和媒体处理都直接走浏览器 session。旧数据库中的 Feishu 表和
迁移定义只为启动旧库和读取历史记录而保留；没有 Feishu 回调、配置、配对、管理页、投递
工具或公开路由。

## DSH 边界

DSH runtime 由 SmartCore Compose 管理；SDK minimal 进程使用持久会话目录，MCP bridge 只提供
SmartCore 高层工具。DSH 不读取 SQLite、数据库卷、备份、`.env` 或宿主 shell，也不接受用户
提交的 owner 字段覆盖 scope。

PWA 的 `/api/assistant/message` 从已认证浏览器 session 派生短期 web scope；daily summary
任务使用日期绑定的 summary scope。scope 不进入模型提示词，用户归属始终由 Server 推导。

DSH bridge 按附件 MIME 在 text 和 vision runtime 之间选择模型；图片不通过文件路径交给模型，
而是由 scope 保护的 Server media route 返回为 MCP image content。两个 profile 使用独立的
持久会话目录，避免跨模型复用会话事实。

每个业务任务至少包含稳定事件 ID、用户上下文、Server 签发的 HMAC 短期
`X-SmartCore-Agent-Scope` 和独立的 `X-SmartCore-Agent-Token`。调用者提交的 user 字段不能
覆盖 scope。

## Agent 工具

`GET /agent/tools` 是 Server 工具名、输入 schema、风险信息和版本的唯一权威来源；DSH MCP
bridge 只对这些 canonical path 做一层高层映射。当前能力覆盖：

- 查询、创建、更新和删除事项，维护 Course、DDL、Plan 和 Reminder 关系；
- 捕获 Idea、把 Idea 转为事项、处理媒体任务；
- 持久化日报、完成事项并追加完成总结；
- 读取脱敏 Computer 工作块证据，提交 Server 规则生成的工作块结果和每日工作日志；
- 读取 `dailyWorkContext` 的当日项目聚合，生成每日简报；
- 将确定性的实时提醒发送到 Screen，PWA 读取历史通知和日报。

Computer 后台分析由 Server 直接调用一次结构化模型并保存结果；默认不把无人值守任务转交
DSH。新调用优先使用 `/agent/db/*`，工具列表中的路径与输入 schema 是实际契约。

工具结果使用稳定 envelope：

```json
{
  "ok": true,
  "stat": "applied",
  "data": {},
  "errors": []
}
```

明确、已授权的请求直接执行。歧义、未找到、校验失败或需要额外输入时返回稳定状态，不让
模型根据自由文本猜测数据库 ID。

## 输出契约

PWA 对话直接显示 DSH 返回的最终答案。DSH bridge 只返回最终答案，不泄露分析、工具输出、
内部 ID 或投递指令。实时提醒由 Server 写入 `notifyLog` 并推送 Screen，PWA 从受保护的 API
读取历史记录。

日报默认 23:59 调度；当天没有 Codex 汇报、Computer 工作块或 Plan 证据的用户直接跳过，
不调用 DSH、不创建占位日报。存在证据时：

- bridge 以任务日期生成首行 `📅 **YYYY年MM月DD日 工作日报**`；
- 必须先调用 `dailyWorkContext`，按项目组织 Codex 报告、Computer 工作块和 Plan 结果；
- 内容只来自该用户当天聚合结果；冲突时依次采用 Plan 人工结果、Codex 报告、工作块推断；
- Server 提取并验证最终报告，日期冲突、重复标题等不可恢复错误直接标记失败。

## Codex 项目汇报

Codex 自动化可在 23:50 汇总当天所有项目，将最小化 JSON 通过
`SmartCoreMonitor codex-report` 上传。Computer token 决定用户和设备，报告只包含项目、结果
状态、单段摘要、时间及 commit/PR/测试证据；不得上传完整对话、源代码、推理或凭证。

## 幂等与失败

- 日报、通知、设备分发和媒体任务分别使用稳定 ID 或唯一键去重；
- DSH bridge 或模型失败返回简短通用错误，不伪造业务成功；
- scheduler 独立于 DSH，模型不可用时确定性提醒和设备状态仍工作；
- 具体运行参数以 `deploy/env.example`、`deploy/dsh.env.example` 和
  `dsh/bridge/patch.yml` 为准；`openclaw/` 仅供显式 rollback profile。
