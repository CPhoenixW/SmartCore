# API 与鉴权契约

本文帮助维护者快速定位协议边界，不复制完整 OpenAPI。字段级 schema 以运行中的
OpenAPI、`GET /agent/tools`、Pydantic 模型和测试为准。

## 响应约定

浏览器和设备接口通常返回：

```json
{"ok": true, "data": {}}
```

Agent 接口使用机器稳定的结果：

```json
{"ok": true, "stat": "done", "data": {}, "errors": []}
```

业务未找到、歧义或校验失败优先返回稳定状态/错误数组；HTTP 401/403 用于凭证和
授权失败。跨用户资源通常返回 404，避免泄露资源存在性。

## 凭证矩阵

| 调用方 | 凭证 | 主要入口 | 所有权来源 |
|---|---|---|---|
| 匿名浏览器 | 无 | `/api/auth/status|setup|register|login` | 尚未建立或新建用户 |
| 登录浏览器 | opaque Session Cookie | `/api/*`、`/api/device/*` | `userSession` active user |
| 管理员 | 同一服务端 Session | `/api/admin/*` | actor 鉴权，active user 定资源范围 |
| DSH bridge | Agent token；用户操作通常另需短期 scope | `/agent/*` | scope 中的 user；例外见下文 |
| 配对中客户端 | `pairId` + `claimCode` | 设备 claim/status/activate | 配对记录用户 |
| 已配对设备 | `X-SmartCore-Device-Token` | dispatch、heartbeat、photo、screen | token 绑定的 device/user |
| Screen WebSocket | query 中 device ID/token | `/screen/ws` | screen device owner |

`/healthz` 和 `/screen` HTML 本身没有应用层认证，但只能通过既定内网边界访问。
公网反向代理只按部署配置允许 PWA 的认证、工作台和助手路径。

## 浏览器会话

当前认证实现位于 `app/server/auth/security.py`：

- Cookie 只包含高熵 opaque token；数据库只保存 SHA-256 hash，不保存可直接复用的 token。
- 登录名或内部 ID 验证成功后，Cookie 必须写入数据库匹配行的内部 `userId`。
- 普通用户的 actor 与 active user 相同。
- 管理员调用 `POST /api/admin/activeUser` 后只更新当前 `userSession.activeUserId`，actor
  保持管理员且 token 不变。
- 资源 owner 由依赖注入，不接受 body/query 提交的 `userId`。

`userSession` 是请求认证的事实源。`POST /api/auth/logout` 撤销当前 Session；
`GET /api/auth/sessions`、`DELETE /api/auth/sessions/{sessionId}` 和
`POST /api/auth/logout-all` 用于设备会话管理；`POST /api/auth/password` 验证旧密码后
撤销 actor 的全部旧 Session，并为当前客户端签发新 Session。部署此版本时旧 HMAC Cookie
明确失效，用户需要重新登录。

主要浏览器域：

| 前缀 | 能力 |
|---|---|
| `/api/auth` | 初始化、注册、登录、注销、当前用户 |
| `/api/admin` | 用户切换和管理审计 |
| `/api/evt` 等 | 事项 CRUD、关系同步、提醒操作 |
| `/api/idea` | Idea、上传、媒体任务、附件读取 |
| `/api/device` | 设备列表、配对、分发、照片请求 |
| `/api/devState` | 状态、历史和滚动用量 |
| `/api/computer` | 电脑活动与 Codex 项目报告上传、状态、统计和洞察 |
| `/api/daily-summaries` | 当前用户日报 |
| `/api/weather` | 登录用户读取共享天气缓存 |
| `/api/assistant` | 登录 PWA 向 DSH 发送 owner-scoped 会话消息 |

日报列表和修改均以浏览器会话中的 active user 为所有权来源。修改使用
`PATCH /api/daily-summaries/{summaryId}`，提交 `content`，并可携带读取时的
`expectedUpdatedAt`；资源不属于当前用户时返回 404，报告已被更新时返回 409，避免
静默覆盖较新的内容。

## 事项契约

现行事项类型：

| 类型 | 时间语义 | 关系 |
|---|---|---|
| `plan` | 绝对开始时间 + duration | 自动拥有开始/结束前 10 分钟提醒 |
| `ddl` | 绝对截止时间 | 可拥有多个 Plan 与一次性 Reminder |
| `course` | 学期起始日、周次、星期、时钟 | 展开为多个 Plan occurrence |
| `remind` | 绝对 trigger time | 独立、Plan 所属或 DDL 所属 |

关系写入必须验证同一用户。普通日程默认隐藏 push-only Reminder。Course 的
`stDate/endDate` 仍有兼容字段，新调用使用 `semesterStart/startWeek/endWeek/weekMode`。

更新/删除以 `evtId` 定位前必须验证 owner。DSH 查询不能静默执行无限制全库
扫描；先解析时间范围并使用 scope 用户。

## Agent API

组装应用由 `app/server/agent/assembly.py` 要求每个 operation 只能来自一个 Router，
发现重复实现即拒绝启动，不再依赖 router 注册顺序。assembled-app 快照位于
`tests/contract/snapshots/assembled_agent_routes.json`；任何同 method+path 的重复 handler
都会使合约测试失败。`/agent/tools`、`/agent/db/query_events`、
`/agent/db/create_event`、`/agent/db/update_event` 需要：

```text
X-SmartCore-Agent-Token
X-SmartCore-Agent-Scope
```

scope 为 HMAC 签名、默认十分钟有效，purpose 为：

- `web`：带 userId，允许 PWA 助手使用当前用户的工具。
- `daily_summary`：绑定 userId 和 reportDate，只允许日报上下文与保存接口。

包括 `/agent/context` 与 `/agent/db/delete_event` 在内的 assembled Agent 路由都要求
Agent token 与用户 scope；不要根据单个 router 文件推断最终契约，修改前用 assembled
`create_app()` 验证实际匹配路由。

新客户端的查询和写入使用：

- `/agent/db/query_events`
- `/agent/db/create_event`
- `/agent/db/update_event`
- `/agent/db/delete_event`
- `/agent/feedback/*`
- `/agent/idea/*`

Agent URL 兼容别名已全部退役，OpenAPI 不再包含 deprecated Agent operation。稳定工具名
仍由 `GET /agent/tools` 映射到上述现代 URL，调用方不得用工具名拼接路径。每次实际
`/agent/*` 调用仍按 method、匹配 path、endpoint 与状态码累计到 `agentRouteUsage`，不保存
token、scope 或 body；assembled app operation 继续写入 `agentRouteObservation`。已退役
路由的历史 observation 保留为 `active=false` 审计记录，管理员兼容报告只返回当前 active
兼容路由，因此现在为空。三批旧入口均在确认生产零调用及第一方迁移后，按用户明确接受的
提前退役风险删除；CI 使用永久退役清单阻止第一方代码重新写死旧 URL。

## 设备配对状态机

```text
created -> claimed -> userConfirmed -> paired
    \---------- expired/cancelled/rejected --------/
```

1. 登录用户 start，Server 生成十分钟有效记录。
2. 客户端持 code claim。
3. 登录 owner confirm。
4. 普通设备持 code activate；token 仅返回一次，数据库保存 SHA-256 hash。
设备 token 只能操作绑定 device。dispatch 的 GET/receipt 不能读取或确认其他设备的
记录。Screen 的 HTTP/WS 同样校验 device owner。

Pi 状态与照片使用 `/dev/*`；通用设备列表/配对/分发使用 `/api/device/*`。兼容期内
`lifeDevice` 是 owner、kind 和激活状态事实源，旧 `device` 只作为状态/照片外键镜像；
启动迁移会双向补齐缺失记录且拒绝 owner 冲突。Server/Web 照片创建、列表、查询和图片
读取均要求浏览器 Session，并验证请求所属 Pi 的 `lifeDevice.userId`；匿名返回 401，
跨用户返回 404。Tailscale 仍是额外网络边界，不替代应用层鉴权。

## 电脑活动

- `POST /api/computer/activity/batch`：computer 设备 token 上传 schema v1 分钟桶，
  每批最多 120 个；Server 以 `(deviceId, bucketStart)` 替换并确认时间。
- `POST /api/computer/heartbeat`：同一凭证上报状态、当前应用、过滤标题、辅助功能权限、
  版本和队列深度。
- `GET /api/computer/status?deviceId=...`：登录 owner 读取当前状态；心跳超过 120 秒为
  `offline`。响应包含基于当前 Plan、电脑状态和同用户新鲜 Pi 状态的确定性 analysis、
  reason codes 与算法版本。
- `GET /api/computer/usage?deviceId=...&range=today|24h|7d|30d&timezone=...`：登录 owner；`24h` 为滚动 24 小时窗口，供活动地图使用
  读取状态总量、Plan 区间并集交集、时间线、会话、应用与过滤后的上下文。可选上下文
  字段为 `contextKind`、`domain`、`workspace` 和 `documentName`。
- `GET /api/computer/insights?deviceId=...&date=YYYY-MM-DD`：登录 owner 读取当前/历史工作块、
  Server 客观 Plan 指标、AI 语义匹配、主题聚类、提醒、每日工作日志和只读小时证据；分析
  状态为 `queued/running/complete/failed`。响应同时返回按项目聚合的 Codex 报告、唯一匹配
  工作块和 Plan；歧义证据归入“其他工作”。
- `POST /api/computer/codex-reports/batch`：computer token 每批、每用户每日最多 100 条 Codex
  项目报告；状态为 `completed/partial/in_progress`，按 `(userId, sourceTaskId, reportDate)` 原子幂等。
- `GET /api/computer/codex-reports?date=YYYY-MM-DD`：登录用户读取自己的当日报告。

上传不接受 `userId` 或其他 owner 字段。非 computer token 返回 403，跨用户浏览器
查询返回 404。Codex 报告只接受项目、标题、单段摘要、时间以及 commit/PR/测试证据，
不接受聊天正文、源代码、内部推理或任意扩展字段。Server 会再次执行敏感应用和认证/金融场景脱敏；会话的 `inference`
和上下文的 `classification` 在 v1 恒为 null。

工作块使用 `GET /agent/computer/work-block-context` 与
`POST /agent/computer/work-block-analysis`；小时接口保留兼容读取，每日接口继续使用
`daily-context/daily-log`。owner 从 scope 派生，run 以稳定 trigger key 幂等；Server
拥有 Plan 活跃覆盖率和最终执行状态，AI 可返回上下文中的 Plan 语义匹配；缺失匹配由 Server
补为 `unclear`、`low`，不能提交或覆盖客观比例。工作块 `action` 字段保留兼容和审计用途，
但有效 action 完全由 Server 按触发器决定。Server 直连分析使用 `deepseek-v4-flash-0731` 并且只请求一次；
`refresh` trigger 只允许 `extend` 同一 open 工作块：累计 active 二十分钟首次触发，此后
每新增六十分钟 active 触发，并向模型同时提供上一版快照、累计事实和新增证据。
无人值守 Computer 任务默认不回退 DSH。兼容回退若单独开启，沿用文本 profile 的
`deepseek-v4-flash-0731`；图片任务才使用 `qwen3.7-plus`。两者只接收 Server 组装的脱敏聚合，
不读取数据库、OCR、网页正文或聊天正文。Computer 每日日志默认只在 23:59 生成一次，
日间预览默认关闭。

注意力提醒不经过 Agent API：Server 使用 Computer `idle` 与 `stateSince` 每分钟确定性检查。
当前 Plan 下连续 idle 五分钟提醒；无 Plan 时需 open 工作块先累计 active 二十分钟。提醒按
连续 idle episode 去重，锁屏、休眠、暂停和离线不触发。

## Idea 媒体状态机

```text
upload -> queued -> processing -> ready -> consumed
                     `-------> failed -> explicit retry
```

- PDF/TXT/ZIP 创建后即可绑定；图片必须经过 ready media job。
- 同一 upload 只有一个 active job；重复创建复用状态/结果。
- 图片由 DSH bridge 通过 scope 保护的 media route 读取并作为 MCP image content；完成工具只接受 jobId 与摘要。
- `/agent/media/ocr` 已退役；OCR 字段和 `ocr_ready` 状态只为历史数据兼容，不发布到
  `GET /agent/tools`，新 Agent 不得调用。
- `PATCH /api/idea/{id}` 用 `expectedRevision`、`addUploadIds`、
  `removeAttachmentIds` 原子提交；stale revision 返回冲突。
- 数据库提交前不删除物理文件，清理不得删除仍被引用的附件。

## 提醒与日报

- 提醒去重由稳定 dedup key 保证；只有真实投递结果写入通知状态。
- Plan 开始提醒不提供完成/延时；结束、DDL 和独立提醒按现行卡片规则处理。
- Plan 结束后的状态修改由 PWA 或 Screen 通过 Server 完成，Server 验证 owner 后更新事项。
- `dailySummary` 以 `(userId, reportDate)` 唯一；DSH bridge 先验证并保存最终报告，PWA
  再从受保护的日报 API 读取。默认每日 23:59 调度；DSH 必须先调用 scope 保护的
  `GET /agent/daily-work-context`，按项目使用 Codex 报告、Computer 工作块和 Plan 人工结果，
  失败不能保存为 completed。事实冲突优先级为人工 Plan 结果、Codex 报告、工作块推断；
  项目投入时长只使用 Server 汇总的 active seconds。
