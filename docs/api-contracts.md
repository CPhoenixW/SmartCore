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
| 登录浏览器 | HMAC 签名 Cookie | `/api/*`、`/api/device/*`、`/api/feishu/*` | Cookie active user |
| 管理员 | 同一 Cookie，另含 actor | `/api/admin/*` | actor 鉴权，active user 定资源范围 |
| Feishu | callback token/签名/加密 | `POST /feishu/event` | 匹配 bot + identity + chat binding |
| OpenClaw | Agent token；用户操作通常另需短期 scope | `/agent/*` | scope 中的 user/bot/chat；例外见下文 |
| 配对中客户端 | `pairId` + `claimCode` | 设备 claim/status/activate | 配对记录用户 |
| 已配对设备 | `X-SmartCore-Device-Token` | dispatch、heartbeat、photo、screen | token 绑定的 device/user |
| Screen WebSocket | query 中 device ID/token | `/screen/ws` | screen device owner |

`/healthz` 和 `/screen` HTML 本身没有应用层认证，但只能通过既定内网边界访问。
公网反向代理只允许飞书回调。

## 浏览器会话

当前认证实现位于 `app/server/auth/security.py`：

- Cookie 内容包含 active `userId`、实际 actor ID、版本和过期时间，并由 HMAC 签名。
- 登录名或内部 ID 验证成功后，Cookie 必须写入数据库匹配行的内部 `userId`。
- 普通用户的 actor 与 active user 相同。
- 管理员调用 `POST /api/admin/activeUser` 后 active user 改变，actor 保持管理员。
- 资源 owner 由依赖注入，不接受 body/query 提交的 `userId`。

`userSession` 表目前不是请求认证的事实源。若未来切换到可撤销服务端 session，必须
同时迁移 Cookie 解码、密码变更失效、注销行为和测试，不能只改模型。

主要浏览器域：

| 前缀 | 能力 |
|---|---|
| `/api/auth` | 初始化、注册、登录、注销、当前用户 |
| `/api/admin` | 用户切换、Feishu bot 配置/测试/绑定 |
| `/api/evt` 等 | 事项 CRUD、关系同步、提醒操作 |
| `/api/idea` | Idea、上传、媒体任务、附件读取 |
| `/api/device` | 设备列表、配对、分发、照片请求 |
| `/api/feishu` | 普通用户绑定默认机器人 |
| `/api/devState` | 状态、历史和滚动用量 |
| `/api/computer` | 电脑活动上传、心跳、客观状态与使用统计 |
| `/api/daily-summaries` | 当前用户日报 |
| `/api/weather` | 登录用户读取共享天气缓存 |

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

更新/删除以 `evtId` 定位前必须验证 owner。OpenClaw 查询不能静默执行无限制全库
扫描；先解析时间范围并使用 scope 用户。

## Agent API

组装应用中，优先注册的是 relation query/write 和 feedback routers，因此当前
`/agent/tools`、`/agent/db/query_events`、`/agent/db/create_event`、
`/agent/db/update_event` 需要：

```text
X-SmartCore-Agent-Token
X-SmartCore-Agent-Scope
```

scope 为 HMAC 签名、默认十分钟有效，purpose 为：

- `feishu`：必须带 userId、botId、chatId，可进行绑定聊天反馈。
- `web`：带 userId，不带 bot/chat，不能调用飞书投递。

`/agent/context` 等后注册的只读实现可能只声明 Agent token，但不要根据单个 router
文件推断最终契约；修改前用 assembled `create_app()` 验证实际匹配路由。

当前例外：`/agent/db/delete_event` 首次出现在随后注册的 v2 router，只校验 Agent
token，且没有从 scope 派生用户。这是待收敛的安全债，不是新接口可沿用的设计。
OpenClaw 当前应优先使用带 scope 的兼容删除路径 `/agent/evtDelete`；修复 canonical
delete 前必须增加 assembled-app 鉴权与跨用户测试。

新客户端的查询和写入使用：

- `/agent/db/query_events`
- `/agent/db/create_event`
- `/agent/db/update_event`
- `/agent/feedback/*`
- `/agent/idea/*`、`/agent/media/ocr`

删除暂时例外：在 canonical `/agent/db/delete_event` 完成 scope 加固前，调用方使用
`/agent/evtDelete`，并同时携带 Agent token 与用户 scope。不要把 token-only canonical
行为视为稳定契约。

`evtQuery`、`evtCreate`、`evtUpdate`、`evtDelete`、`sendText`、`sendCard` 等是兼容
别名。移除前必须核对 Adapter、OpenClaw skill、生产调用日志和对应测试。

## 设备配对状态机

```text
created -> claimed -> userConfirmed -> paired
    \---------- expired/cancelled/rejected --------/
```

1. 登录用户 start，Server 生成十分钟有效记录。
2. 客户端持 code claim。
3. 登录 owner confirm。
4. 普通设备持 code activate；token 仅返回一次，数据库保存 SHA-256 hash。
5. Feishu bot 配对在用户确认时由 Server 激活，并继续建立 identity/binding。

设备 token 只能操作绑定 device。dispatch 的 GET/receipt 不能读取或确认其他设备的
记录。Screen 的 HTTP/WS 同样校验 device owner。

Pi 状态与照片使用 `/dev/*`；通用设备列表/配对/分发使用 `/api/device/*`。两者目前
跨 `device` 与 `lifeDevice` 两组模型，修改时必须运行两组测试。

注意：`app/server/device/routes.py` 中 Server/Web 照片创建、查询和读取路由目前没有
逐个声明浏览器 session 依赖，依靠 Tailscale/反向代理边界。它们不得进入公网路由；
若补 owner 鉴权，需要同步前端、测试和旧 Pi/Screen 调用方。

## 电脑活动

- `POST /api/computer/activity/batch`：computer 设备 token 上传 schema v1 分钟桶，
  每批最多 120 个；Server 以 `(deviceId, bucketStart)` 替换并确认时间。
- `POST /api/computer/heartbeat`：同一凭证上报状态、当前应用、版本和队列深度；旧版
  标题与权限字段仍接受但不再保存。
- `GET /api/computer/status?deviceId=...`：登录 owner 读取当前状态；心跳超过 120 秒为
  `offline`。响应包含基于当前 Plan、电脑状态和同用户新鲜 Pi 状态的确定性 analysis、
  reason codes 与算法版本。
- `GET /api/computer/usage?deviceId=...&range=today|7d|30d&timezone=...`：登录 owner
  读取状态总量、Plan 区间并集交集、时间线、会话与应用。

上传不接受 `userId` 或其他 owner 字段。非 computer token 返回 403，跨用户浏览器
查询返回 404。会话的 `inference` 和上下文的 `classification` 在 v1 恒为 null。

## Feishu 配对状态机

普通用户：

```text
POST /api/feishu/pair/start
-> 在目标聊天发送「绑定 <code>」
-> claimed
-> POST /api/feishu/pair/{id}/confirm
-> active FeishuBind
```

入站消息只有匹配 `(bot, identity, chat)` 的 active binding 才能签发 scope。主动提醒
只选该用户 primary binding；没有 binding 时不得回退到管理员聊天。

管理员 `/api/admin/feishuBots/*` 可以配置、启停、测试和配对 bot。明文 App Secret、
Verification Token 与 Encrypt Key 只允许写入，读取响应和日志绝不返回。

## Idea 媒体状态机

```text
upload -> queued -> processing -> ready -> consumed
                     `-------> failed -> explicit retry
```

- PDF/TXT/ZIP 创建后即可绑定；图片必须经过 ready media job。
- 同一 upload 只有一个 active job；重复 Agent OCR 调用复用状态/结果。
- OCR evidence 绑定 user/upload/expiry，不能跨用户或用于文档。
- `PATCH /api/idea/{id}` 用 `expectedRevision`、`addUploadIds`、
  `removeAttachmentIds` 原子提交；stale revision 返回冲突。
- 数据库提交前不删除物理文件，清理不得删除仍被引用的附件。

## 提醒与日报

- 提醒去重由稳定 dedup key 保证；只有真实投递结果写入通知状态。
- Plan 开始提醒不提供完成/延时；结束、DDL 和独立提醒按现行卡片规则处理。
- Screen 与 Feishu 的 done/snooze 最终都由 Server 修改同一事项。
- `dailySummary` 以 `(userId, reportDate)` 唯一；Adapter 先验证并保存最终报告，再投递
  Feishu。失败不能保存为 completed。
