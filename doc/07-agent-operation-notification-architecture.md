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
- `action_name`：准备执行的 Action，例如 `create_assignment`。
- `operation_payload`：结构化参数 JSON。
- `confidence`：语义解析置信度。
- `status`：`pending`、`confirmed`、`applied`、`rejected`、`failed`。
- `result_resource_type` / `result_resource_id`：执行后产生或影响的资源。
- `error_message`：执行失败原因。

低风险 Read 操作可以直接执行；Create 默认建议确认；Update 和 Delete 必须确认；语义模糊时必须追问或停留在 pending。

## 执行侧：Action

Action 是业务动作边界。接口层、LLM 层、飞书层都不能直接写复杂业务逻辑，必须调用 Action。

第一批标准 Action：

- `create_assignment`
- `create_life_event`
- `complete_item`
- `postpone_reminder`
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

本阶段预留 DeepSeek Provider，但不把真实 API key 写入仓库。配置通过环境变量提供：

- `LLM_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `LLM_MODEL=deepseek-chat`

默认实现应先提供 `RuleBasedOperationParser`，在没有 key 或关闭 LLM 时也能处理确定性命令。LLM 调用失败时必须降级为 pending 或帮助信息，不能影响现有命令。

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
