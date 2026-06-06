# 智能体操作与输出架构

本文档定义 SmartCore 从“命令机器人”升级为“可靠个人调度系统”的下一阶段架构。目标是让自然语言、Web 操作、飞书按钮、未来设备输入都转化为同一套标准操作；让提醒、晨报、状态推送、异常通知都走同一套可追踪输出系统。

## 核心原则

SmartCore 不把 LLM 当成直接执行者。LLM 只负责把自然语言翻译为结构化操作草案；真正修改数据、生成提醒、发送消息的逻辑必须由确定性的 Action、Resource、Event 和 Notification 模块完成。

系统必须满足：

- 输入标准化：飞书、Web、内部 API、设备按钮都转化为 operation。
- 执行可确认：中高风险 operation 必须进入 pending 状态，用户确认后执行。
- 状态可追踪：每次理解、确认、执行、通知发送都要有记录。
- 失败可重试：通知发送失败不丢失，delivery 记录原因和重试次数。
- 能力可扩展：新增能力时只新增语义规则、Action、资源模型、事件规则和通知模板。

## 分层架构

```text
飞书 / Web / 内部 API / 设备按钮
  ↓
Interface Layer
  ↓
Semantic Layer
自然语言、规则、DeepSeek/OpenAI 等 LLM Provider
  ↓
Pending Operation
结构化草案、置信度、确认状态
  ↓
Action Layer
业务动作、校验、审计、资源调用
  ↓
Resource Layer
标准 CRUD 和 SQLite 数据模型
  ↓
Event & Schedule Layer
数据变化事件、时间到期事件、提醒生成
  ↓
Notification Layer
通知队列、模板渲染、发送记录
  ↓
Channel Layer
飞书 / Web Inbox / 树莓派 / 手机 / 电脑
```

## 输入侧：Operation

Operation 是系统接收输入后的标准执行草案。它不是数据库写入本身，而是“准备执行什么”的结构化描述。

建议字段：

- `source`：输入来源，例如 `feishu`、`web`、`internal_api`。
- `raw_text`：原始输入。
- `action_name`：准备执行的 Action，例如 `create_event`、`update_event`、`delete_event`、`query_event`。
- `operation_payload`：结构化参数 JSON。
- `confidence`：语义解析置信度。
- `status`：`pending`、`confirmed`、`applied`、`rejected`、`failed`。
- `result_resource_type` / `result_resource_id`：执行后产生或影响的资源。
- `error_message`：执行失败原因。

低风险 Read 操作可以直接执行；Create 默认建议确认；Update 和 Delete 必须确认；语义模糊时必须追问或停留在 pending。

当前飞书读接口必须覆盖常用自然问法，而不是只接受机械命令：

- `今日`、`今天`、`今天有啥事`、`今天有什么安排` 等应返回今日计划。
- `明日`、`明天`、`明天有什么安排` 等应返回明日计划。
- `待办`、`待完成事项`、`还有什么没做` 等应返回所有未完成作业与生活事项。
- `本周DDL` 应返回本周未完成 DDL。
- `提醒队列` 应返回提醒队列状态。

这些低风险查询不进入 pending confirmation；它们应直接查询 Resource/Secretary 层并即时回复，同时 `message_logs.parsed_command` 必须记录实际查询命令，例如 `today` 或 `todos`，不能把已支持自然问法记录为 `help`。

### 第一阶段：LLM 事件接口

大模型面向 Action Layer 的主接口必须收敛为统一事件协议，而不是直接暴露内部表名或提醒队列表。

统一事件资源：

- `resource`: 固定为 `event`。
- `operation`: `create`、`update`、`delete`、`query` 四种；兼容模型输出 `read`，归一化为 `query`。
- `fields.event_type`: 三类用户可见事件之一：
  - `course_session`：课程/上课事件，映射到 `courses` + `course_sessions`。
  - `assignment`：作业/DDL 事件，映射到 `assignments`。
  - `life_event`：生活事项/个人安排，映射到 `life_events`。
- `selector`: 修改、删除、精确查询已有事件时必须包含 `id`，并应包含 `event_type`；缺失时由 `fields.event_type` 补齐。
- `fields`: 事件字段，例如 `title`、`course_name`、`due_at`、`scheduled_at`、`deadline_at`、`weekday`、`start_time`、`end_time`、`notes`、`reminder_lead_minutes`。

Action 名称边界：

- `create_event`：新增三类事件；`assignment` 和 `life_event` 默认需要确认。
- `update_event`：修改已有事件；必须确认。
- `delete_event`：删除语义先实现为软删除/取消；必须确认。
- `query_event`：查询事件；低风险，直接执行并回复，不进入 pending。

内部资源边界：

- `reminder` 是内部提醒队列，不是用户直接创建的事件类型。用户说“提醒我……”时应输出 `resource=event`、`event_type=life_event`，并通过 `reminder_lead_minutes` 表达提前提醒。
- LLM 和规则写入入口不得再产生 `create_assignment`、`create_life_event`、`update_reminder`、`cancel_reminder` 等旧 Action；历史 pending operation 如果仍携带这些 action，应失败并进入审计，而不是继续扩散旧协议。

### 可观测性

Web 面板必须能直接查看最近输入和执行链路：

- `/dashboard/logs` 展示最近 `message_logs`，包含来源、外部消息 ID、原始内容、解析命令、回复状态和创建时间。
- 同页展示最近 `pending_operations`，包含原始命令、Action、状态、结果资源和错误信息。
- 飞书自然语言解析失败必须在应用日志里记录错误；前端至少能通过 `message_logs.reply_status=help` 发现用户看到了降级帮助。

## 执行侧：Action

Action 是业务动作边界。接口层、LLM 层、飞书层都不能直接写复杂业务逻辑，必须调用 Action。

第一批标准 Action：

- `create_event`
- `update_event`
- `delete_event`
- `query_event`
- `confirm_operation`
- `reject_operation`

Action 负责：

- 校验 payload。
- 调用资源 CRUD 修改数据库。
- 写入操作状态。
- 产生领域事件。
- 必要时触发通知队列。

## 输出侧：Notification

输出系统也必须标准化，不能让各功能散落地调用 `send_text()`。

通知分为四类：

- 即时回复：用户查询后立即返回，同时写 message log。
- 定时提醒：课前提醒、DDL 提醒、明日预告。
- 批量摘要：每日晨报、天气通勤、每周总结。
- 异常通知：备份失败、抓取失败、发送失败、服务异常。

建议核心资源：

- `notification`：一条准备发送或已发送的信息。
- `notification_delivery`：一次具体通道发送记录。
- `notification_template`：后续可选，用于管理消息格式。
- `device_channel`：后续可选，用于管理飞书、Web、树莓派等通道。

Notification Dispatcher 只负责发送队列中的通知，并写 delivery。业务模块只创建 notification，不直接关心飞书 API。

## LLM Provider 策略

本阶段接入 DeepSeek Provider，但不把真实 API key 写入仓库。配置通过环境变量提供：

- `LLM_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `LLM_MODEL=deepseek-chat`

默认实现先运行 `RuleBasedOperationParser`，规则不支持时再调用 DeepSeek。LLM 只能返回结构化 `ParsedOperation`，不能直接修改数据库。LLM 调用失败时必须降级为帮助信息或可理解错误，不能影响现有命令。

## 新增能力流程

新增任何能力时按以下顺序落地：

1. 定义用户意图：用户会怎么说、想达到什么结果。
2. 修改语义规则或 LLM prompt：把输入转成标准 operation。
3. 新增或修改 Action：定义确定性执行边界。
4. 修改资源模型：新增表、字段、状态或索引。
5. 定义事件和调度规则：执行后是否产生提醒或通知。
6. 定义通知模板和通道：发送什么、发给谁、失败如何处理。
7. 增加测试：覆盖解析、执行、通知、失败降级。

## 第一阶段验收

第一阶段不追求完整智能体，只要求形成最小可靠闭环：

- 可以把确定性文本解析为 pending operation。
- 用户确认后 Action 写入 assignment 或 life_event。
- Action 执行后写入结果资源和状态。
- 可以创建 notification，并通过 fake channel 发送。
- 发送成功和失败都写 notification delivery。
- 现有飞书命令、Web 面板、提醒引擎测试不回退。

## 第二阶段：主动提醒调度

配置完成后，SmartCore 必须从“被动命令机器人”升级为“会主动提醒的个人秘书”。本阶段先不引入 LLM，也不处理树莓派备份，只把现有 ReminderEngine 接入 FastAPI 生命周期。

目标行为：

- 服务启动时，如果 `SCHEDULER_ENABLED=true` 且飞书主动推送配置完整，则启动后台调度。
- 调度器按 `SCHEDULER_INTERVAL_SECONDS` 周期调用 `SchedulerRunner.tick()`。
- 每次 tick 先生成当天提醒，再发送到期提醒。
- 发送通道使用 `FEISHU_DEFAULT_CHAT_ID`，不能依赖收到用户消息时的临时 chat_id。
- 配置不完整时，应用仍然正常启动，只是不启动主动调度。
- 服务关闭时，后台调度必须停止，避免 reload 或容器退出时留下重复任务。

本阶段的可靠性边界：

- 不在启动时发送测试消息，避免部署时误打扰。
- 不要求每条 reminder 进入 notification 队列表；现有 `Reminder` 表可继续作为定时提醒的可靠队列。
- 飞书发送失败按现有 retry 规则记录在 reminder 上，不能让后台任务崩溃。
- 后续如果统一到 `notification` 队列，应保持对 `ReminderEngine` 行为的兼容测试。

## 第三阶段：飞书确认式操作闭环

飞书入口开始承担第一条真实智能体链路：把用户的写操作转成 `pending_operation`，再由用户显式确认或拒绝。读操作仍然可以即时回复。

本阶段范围：

- `添加作业 ...` 和 `添加事项 ...` 在飞书中不直接写入资源表。
- 飞书回复必须包含 operation id，并提示 `确认 <id>` / `拒绝 <id>`。
- `确认 <id>` 调用 ActionExecutor，把 pending operation 应用到数据库。
- `拒绝 <id>` 只更新 operation 状态，不产生资源。
- 确认或拒绝不存在、已处理、格式错误的 operation 时，必须给出可理解回复，不让事件处理失败。
- `今日`、`明日`、`本周DDL`、`帮助`、`完成 ...` 继续保持现有行为。

本阶段暂不接 DeepSeek。语义层继续使用 `RuleBasedOperationParser`，后续 LLM Provider 只能替换“从文本到 ParsedOperation”的部分，不能绕过 PendingOperation 和 ActionExecutor。

## 第四阶段：LLM 与卡片确认

飞书入口升级为自然语言优先的确认式交互：

- 规则命令继续本地解析。
- 规则不认识的写操作调用 DeepSeek，把自然语言转成 `PendingOperation`。
- 例如 `今晚八点提醒我做程设作业` 应转为 `create_event`，字段包含 `event_type=life_event`、`title` 与 `scheduled_at`。
- 带计划时间的 `life_event` 在用户确认后必须同时创建事件前提醒；默认提前 15 分钟，用户输入指定“提前 X 分钟/小时提醒”时，语义层应输出 `fields.reminder_lead_minutes`，执行层按该值覆盖默认提前量。
- 飞书回复必须使用交互卡片展示操作摘要，包含“确认”“修改命令”“拒绝”三个入口。
- “确认”“拒绝”按钮通过 `card.action.trigger` 回调执行，不依赖用户手动输入 `确认 <id>`。
- “修改命令”跳转到 Tailscale 内网前端的 pending operation 页面。
- 前端提供 `/dashboard/pending-operations`，可查看、确认、拒绝和修改待确认操作。

飞书开发者后台需要额外订阅新版卡片回传交互回调 `card.action.trigger`，请求地址与事件订阅一致：`https://<DOMAIN>/feishu/event`。

## 第五阶段：体验增强与可视化队列

本阶段不改变分层架构，只在现有层补齐可用性：

- 读命令层继续承载 `今日`、`明日`，并新增轻量 `提醒队列` 查询，展示待发送、已发送、失败提醒。
- `今日` / `明日` 回复除了计划项，还应包含当天待发送提醒摘要，让用户知道系统接下来会主动推送什么。
- PendingOperation 卡片必须把字段翻译成人能直接确认的信息：事项标题、计划时间、提醒时间、提前量；不要只展示 `scheduled_at`、`reminder_lead_minutes` 这类内部字段名。
- `/dashboard/reminders` 是提醒队列中控台，应展示状态概览、下一条提醒、最近提醒列表，便于从电脑或手机检查后台调度状态。
- `/dashboard/today` 作为默认首页，应显示轻量中控台摘要：待确认操作数、待发送提醒数、下一条提醒，帮助用户快速判断系统是否按预期运转。
- 这些增强只能使用现有 `Reminder`、`PendingOperation`、Feishu card、dashboard 模板，不引入新的框架或外部服务。

## 第六阶段：提醒修改与取消

本阶段仍然只增强现有提醒层，不引入统一 CRUD 框架：

- 飞书命令层支持显式 `修改提醒 <id> <YYYY-MM-DD HH:MM>` 和 `取消提醒 <id>`。
- 前端 `/dashboard/reminders` 支持对待发送提醒修改计划发送时间、取消提醒。
- 取消提醒只把 `Reminder.status` 改为 `cancelled`，不能删除记录，保留审计线索。
- 已发送提醒不能取消或修改；失败提醒后续可通过重试策略处理，本阶段不改变调度器语义。
- 所有修改都作用于现有 `reminders` 表，不改变事件、课程、作业等上游资源结构。

## 第七阶段：LLM 统一事件输出协议

语义层从“动作名优先”升级为唯一的事件操作协议：

- DeepSeek 必须输出 `operation/resource/selector/fields`。
- `operation` 取值为 `create/update/delete/query`；兼容模型输出 `read`，解析层归一化为 `query`；写操作仍需 `needs_confirmation=true`。
- `resource` 固定为 `event`。
- `fields.event_type` 固定为 `course_session`、`assignment`、`life_event` 三选一；查询可使用 `all`。
- `selector` 用来定位已有事件，例如 `{"event_type": "life_event", "id": 12}`；多义或缺少定位信息时，应降低置信度或生成需要用户补充的信息。
- 解析层只规范化为 `create_event`、`update_event`、`delete_event`、`query_event`。
- Reminder 队列是调度内部资源，前端和显式飞书命令可管理队列，但 LLM 不直接增删改查 reminder。

## 第九阶段：二阶段语义候选选择

自然语言查询、修改、删除不能依赖数据库文本模糊匹配，也不能要求用户提前知道数据库 id。除 `create_event` 外，语义层必须使用二阶段流水线：

```text
用户自然语言
  ↓
LLM #1：抽取 operation、candidate_scope、patch
  ↓
DB：只用结构化条件召回候选短列表
  ↓
LLM #2：从短候选中语义选择目标
  ↓
query 直接回复 / update-delete 生成确认卡片
  ↓
用户确认后执行数据库写入
```

第一阶段输出仍使用统一 event 协议，但 `selector` 不再强制包含 `id`。它可以包含：

- `event_type`: `all`、`assignment`、`life_event`、`course_session`。
- `time_range`: `{"start": ISO8601, "end": ISO8601}`。
- `status`: 默认 `open`。
- `max_candidates`: 默认 20，上限 50。
- `target_description`: 用户口中的目标描述，例如“程序设计作业”。

数据库候选召回只使用强结构条件：类型、时间范围、状态、数量限制。不得把 `target_description` 当作唯一 SQL text match 条件。候选列表传给 LLM #2 前必须压缩成低 token 结构，字段只保留：

- `event_type`
- `id`
- `status`
- `time_label`
- `title`

第二阶段只负责从候选里选择，不允许产生新的数据库写入字段。结构化输出：

```json
{
  "match_status": "single | multiple | ambiguous | none",
  "selected_ids": [{"event_type": "life_event", "id": 1}],
  "confidence": 0.92,
  "reason": "候选标题和用户目标最接近"
}
```

执行规则：

- `query_event`: 展示 LLM #2 选中的候选；如果 `none`，回复暂无匹配。
- `update_event`: 只有 `single` 且置信度足够时生成 pending confirmation；多候选或低置信度必须要求用户澄清。
- `delete_event`: `single` 或明确批量 `multiple` 可以生成 pending confirmation；卡片必须展示将删除的候选列表。多义 `ambiguous` 必须澄清。
- 确认前不得修改数据库。
- pending payload 必须保存已解析出的真实目标 id，执行层只执行这些目标。

## 第八阶段：失败回滚与操作审计

本阶段不新增审计框架，先复用 `PendingOperation`：

- ActionExecutor 捕获可预期执行失败，不能让飞书事件处理或前端确认请求直接崩溃。
- 失败操作必须写入 `PendingOperation.status=failed` 与可读 `error_message`。
- 已定位到目标资源但因状态限制失败时，应记录 `result_resource_type` 与 `result_resource_id`，方便前端审计。
- 创建类操作如果后续步骤失败，例如 life_event 已创建但 reminder 创建失败，应回滚或清理已创建资源，避免半写入。
- `/dashboard/pending-operations` 除待确认列表外，应展示最近操作审计，包括 applied/rejected/failed 状态和错误信息。
