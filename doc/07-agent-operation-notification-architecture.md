# 智能体操作与输出架构

本文档定义 SmartCore 从“命令机器人”升级为“可靠个人调度系统”的架构。目标是让自然语言、Web 操作、飞书按钮都转化为同一套标准 Action；让提醒、晨报、状态推送走可追踪的输出系统。

## 当前实现摘要（2026-06）

### 语义层：仅 LLM + Action 协议

- 飞书文本入口只使用 `OperationParser`（DeepSeek）。
- 必须配置 `LLM_PROVIDER=deepseek` 与 `DEEPSEEK_API_KEY`。
- LLM 输出必须是 Action 协议：

```json
{
  "action": "create_event | query_event | update_event | delete_event",
  "payload": {},
  "confidence": 0.9,
  "needs_confirmation": false
}
```

- 已删除：`RuleBasedOperationParser`、旧版 `operation/resource/fields` unified 协议、飞书关键词命令分支。

### 调度层：扫描式提醒 + 飞书卡片

- `SCHEDULER_ENABLED=true` 时，APScheduler 每 `SCHEDULER_INTERVAL_SECONDS`（默认 60 秒）调用 `SchedulerRunner.tick()`。
- `ReminderEngine.scan_and_notify()` 从 live 数据（课表、作业、生活事项）计算当前窗口内应发送的提醒。
- 提醒通过飞书**交互卡片**发送（`app/scheduler/notification_cards.py`），包含 richer markdown 内容。
- **不再预写提醒队列**。`reminders` 表仅作投递审计：发送成功后写入 `dedup_key` 记录，避免同一提醒重复发送。
- 数据变更（改 DDL、取消作业）会立即反映到下一次扫描，不会出现“队列与数据库不一致”。

### 写操作：PendingOperation 确认闭环

- `create_event` / `update_event` / `delete_event` 先写 `pending_operations`，飞书卡片确认后由 `ActionExecutor` 落库。
- `query_event` 低风险直查，不进 pending。

---

## 核心原则

SmartCore 不把 LLM 当成直接执行者。LLM 只负责把自然语言翻译为结构化操作草案；真正修改数据、生成提醒、发送消息的逻辑必须由确定性的 Action 模块完成。

系统必须满足：

- 输入标准化：飞书、Web 都转化为 Action 协议。
- 执行可确认：中高风险 Action 必须进入 pending 状态，用户确认后执行。
- 状态可追踪：每次理解、确认、执行、通知发送都要有记录。
- 失败可重试：通知发送失败记录在 `reminders` 投递审计上，下次 tick 可重试。
- 提醒与数据一致：调度器扫描 live 数据，不维护独立提醒队列。

## 分层架构

```text
飞书 / Web
  ↓
Interface Layer（FastAPI /feishu/event、/dashboard/*）
  ↓
Semantic Layer（DeepSeek → OperationParser → ParsedOperation）
  ↓
Normalize Layer（action_from_parsed → Action JSON）
  ↓
Pending Operation（写操作预览、确认状态）
  ↓
Action Layer（ActionExecutor）
  ↓
Resource Layer（crud → SQLite）
  ↓
Event & Schedule Layer（ReminderEngine.scan_and_notify）
  ↓
Notification Layer（OutboundNotification、dedup_key 投递审计）
  ↓
Channel Layer（Feishu 交互卡片 / 文本）
```

## Action 协议

详见 `doc/action-result-protocol.md`。

公开 `event_type`：

- `course` — 课程块
- `plan` — 计划块（起止时间）
- `schedule` — 生活安排 / 提醒事项
- `deadline` — 作业 DDL

Action 名称：

- `create_event` — 默认需确认
- `update_event` — 必须确认
- `delete_event` — 必须确认（软删除/取消）
- `query_event` — 直接执行

## 调度提醒类型

| 类型 | 触发条件 | 卡片内容 |
|------|----------|----------|
| `daily_digest` | 每天 07:00 窗口 | 今日课程、DDL、生活事项 |
| `tomorrow_preview` | 每天 21:00 窗口 | 明日安排 |
| `pre_class` | 开课前 15 分钟 | 课程名、时间、地点、倒计时 |
| `ddl_eve` / `ddl_today` | 截止前夜 20:00 / 当天 08:00 | 作业详情、截止时间 |
| `assignment_pre_due` | DDL 前 30/15 分钟 | 作业卡片 |
| `life_event_pre_event` | 事项开始前 30/15 分钟 | 事项卡片 |

dedup_key 示例：`daily_digest:2026-03-02`、`pre_class:12:2026-03-02`。

## 二阶段语义候选选择

对带 `target_description` 的 query/update/delete：

1. 先 `query_event` 拉候选列表（后端生成 ref）
2. LLM `select_candidates()` 从候选中选 ref
3. 再执行或回复

`query_event` 带 `time_range` 时必须按真实发生时间过滤所有事件类型。课程必须展开为指定日期内的课程实例，再按实例起止时间判断是否落入范围；不能返回没有落入该时间段的全部课表 session。课程实例判断周次时必须使用系统配置的 `SEMESTER_START`，不能退回到按目标年份 9 月 1 日计算，否则单双周和周次范围课程会在查询中漏掉。

`query_event` 在飞书入口输出时应优先使用交互卡片，而不是纯文本列表。查询卡片至少展示查询标题、匹配数量、事件类型、事项名称、开始/结束时间或 `time_label`，课程还应展示地点等基础内容（如可用）。无匹配结果也应发送卡片并明确提示暂无匹配安排。

## 飞书交互卡片

待确认操作卡片只展示用户确认所需的最小信息：

- 操作名称（新增事项、修改事项、删除事项等）
- 事件类型（course / plan / schedule / deadline）
- 事项名称
- 开始时间和结束时间（如存在）
- 默认提醒时间（schedule / deadline 使用开始或截止前 30/15 分钟）

待确认卡片不展示原始命令、内部 resource 字段、模型备注、数据库字段名或调试信息。用户确认成功后，系统必须主动发送一张“操作成功”飞书卡片，包含操作名称和事项名称；原确认卡片仍应被删除，避免重复点击。

## Web 可观测性

- `/dashboard/logs` — 飞书 message_logs + pending 审计
- `/dashboard/pending-operations` — 待确认操作
- `/dashboard/reminders` — 通知投递记录（已发送/失败），非待发送队列
- `/dashboard/today` — 今日计划 + 待确认数 + 最近通知摘要

## Web 管理行为

- 课表导入是“替换当前课表”，每次导入成功后应删除旧课程和旧课程时段，再写入新 CSV 内容。
- 作业 / DDL 与生活事项列表都必须提供一键删除按钮；删除应使用软删除/取消状态，不直接暴露数据库删除。
- 页面展示应以扫描和操作为主：列表信息密度适中，状态、时间、操作按钮清晰对齐，避免把调试 JSON 或过长原始协议内容放在主视图。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_PROVIDER=deepseek` | 启用自然语言解析（必需） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `SCHEDULER_ENABLED=true` | 启用后台扫描提醒 |
| `SCHEDULER_INTERVAL_SECONDS=60` | 扫描间隔（秒） |
| `FEISHU_DEFAULT_CHAT_ID` | 主动提醒目标会话 |
