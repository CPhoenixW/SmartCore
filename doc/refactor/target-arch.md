# 目标架构

SmartCore 新架构是一个服务器主控的个人智能体系统。服务器是唯一权威节点；树莓派提供工作状态；Linux PC 和 MacBook 使用 Web 工作台；手机副屏通过 Tailscale 直连服务器页面；手机飞书用于离开工位时的自然语言入口和提醒入口。

## 网络拓扑

```text
手机飞书
  -> Feishu Open Platform
  -> Cloudflare / Caddy
  -> server /feishu/event
  -> OpenClaw
  -> server /agent tools
  -> server DB

树莓派
  -> Tailscale
  -> server /dev/state

Linux PC / MacBook
  -> Tailscale
  -> server /work

手机副屏
  -> Tailscale browser
  -> server /screen
  -> server /screen/ws

server scheduler
  -> every minute scan DB + devState
  -> working: push screen
  -> away/unknown: push Feishu
```

## 设备职责

### server

server 负责：

- 保存 SQLite 数据库。
- 提供 DB CRUD API。
- 提供 OpenClaw tool API。
- 接收 Feishu webhook。
- 把 Feishu 消息转成 OpenClaw 事件。
- 每分钟扫描提醒。
- 接收树莓派 `devState`。
- 维护手机副屏 WebSocket。
- 为电脑提供 `/work` 工作台。
- 负责备份、恢复、日志、审计。

server 不负责：

- 不暴露数据库到公网。
- 不让 OpenClaw 读写 SQLite 文件。
- 不保留旧表兼容逻辑。

### pi

pi 负责：

- 在 `yolo` 目录运行人脸识别或工作状态检测。
- 判断 `working` / `away` / `unknown`。
- 通过 Tailscale 直连 server 上报 `devState`。

pi 不负责：

- 不写数据库。
- 不发 Feishu。
- 不做提醒调度。

### linuxPc / macBook

电脑负责：

- 通过 Tailscale 打开 `/work`。
- 快速修改 `lifeEvt`、`ddlEvt`、`courseTpl`、`idea`。
- 查看 `devState`、`notifyLog`、`msgLog`、`actLog`。
- 后续支持自然语言输入，但必须保留结构化编辑入口。

### sidePhone

手机副屏在 Tailscale 局域网里，因此直接访问 server：

- `http://server-tailnet:8000/screen`
- `ws://server-tailnet:8000/screen/ws`

副屏负责：

- 展示时间。
- 展示当前 `devState`。
- working 时展示当前事项、下一事项、关键待办。
- away/unknown 时展示更简洁的低干扰界面。
- 接收 server 推送的提醒。

副屏不是公网入口，不需要 Cloudflare。

### phoneFeishu

手机飞书负责：

- 文本输入规划、灵感、查询、安排。
- away/unknown 时接收提醒。
- 后续支持语音、图片、OCR。

## 数据模型

新架构直接使用新表。旧表删除，不做兼容。

### `evtBase`

日程基础表。

字段：

- `evtId` 主键。
- `title`。
- `desc`。
- `evtType`: `ddl` / `course` / `life`。
- `prio`: `high` / `mid` / `low`。
- `stat`: `todo` / `done` / `cancelled`。
- `createdAt`。
- `updatedAt`。

约束：

- 每条 `evtBase` 必须对应且只对应一个子表记录。
- 子表由 `evtType` 决定。

### `lifeEvt`

普通事项。

字段：

- `evtId` 主键，引用 `evtBase.evtId`，级联删除。
- `dueAt`，计划完成时间。
- `doneAt`，实际完成时间。

### `ddlEvt`

截止日期。

字段：

- `evtId` 主键，引用 `evtBase.evtId`，级联删除。
- `ddlAt`，截止时刻。
- `hardDdl`，是否强截止。

### `courseTpl`

课表模板。

字段：

- `tplId` 主键。
- `courseName`。
- `teacher`。
- `room`。
- `weekday`: 1 到 7。
- `startTime`。
- `endTime`。
- `startWeek`。
- `endWeek`。
- `weekMode`: `all` / `odd` / `even`。
- `semester`。

### `courseInst`

课程实例。

字段：

- `evtId` 主键，引用 `evtBase.evtId`，级联删除。
- `tplId`，引用 `courseTpl.tplId`，限制删除。
- `classDate`。
- `attendStat`。

课程实例可以按查询窗口生成，也可以由后台预生成。对外统一表现为 `courseInst`。

### `idea`

突发灵感。

字段：

- `ideaId` 主键。
- `content`。
- `srcType`: `text` / `voice` / `ocr`。
- `mediaPath`。
- `handled`。
- `createdAt`。

### `ideaToEvt`

灵感转换记录。

字段：

- `ideaId` 主键，引用 `idea.ideaId`，级联删除。
- `evtId`，引用 `evtBase.evtId`，级联删除。
- `convertedAt`。

### `devState`

设备状态。

字段：

- `stateId` 主键。
- `devId`，例如 `pi`、`sidePhone`。
- `state`: `working` / `away` / `unknown` / `online` / `offline`。
- `confidence`。
- `seenAt`。
- `meta`。

### `notifyLog`

通知投递审计。

字段：

- `notifyId` 主键。
- `dedupKey`。
- `targetKind`: `screen` / `feishu`。
- `targetId`。
- `title`。
- `content`。
- `scheduledAt`。
- `sentAt`。
- `stat`: `sent` / `failed` / `fallback`。
- `failReason`。

### `msgLog`

消息审计。

字段：

- `msgId` 主键。
- `src`: `feishu` / `openclaw` / `web` / `screen`。
- `externalId`。
- `rawText`。
- `intent`。
- `stat`。
- `createdAt`。

### `actLog`

动作审计和撤销依据。

字段：

- `actId` 主键。
- `src`。
- `actor`。
- `actType`: `create` / `update` / `delete` / `undo` / `routeNotify`。
- `targetKind`。
- `targetId`。
- `beforeData`。
- `afterData`。
- `undoToken`。
- `createdAt`。

## API 设计

### 内部 Web API

只走 Tailscale。

建议路径：

- `GET /api/evt`
- `POST /api/evt`
- `PATCH /api/evt/{evtId}`
- `DELETE /api/evt/{evtId}`
- `GET /api/lifeEvt`
- `POST /api/lifeEvt`
- `GET /api/ddlEvt`
- `POST /api/ddlEvt`
- `GET /api/courseTpl`
- `POST /api/courseTpl`
- `GET /api/courseInst`
- `GET /api/idea`
- `POST /api/idea`
- `POST /api/idea/{ideaId}/toEvt`
- `GET /api/devState`
- `POST /dev/state`
- `GET /api/notifyLog`
- `GET /api/msgLog`
- `GET /api/actLog`
- `POST /api/undo/{undoToken}`

### OpenClaw Agent API

旧 skill 删除，重写为很薄的工具说明。OpenClaw 只需要知道如何调用 SmartCore，不复制业务逻辑。

建议工具：

- `evtQuery`
- `evtCreate`
- `evtUpdate`
- `evtDelete`
- `ideaCapture`
- `ideaToEvt`
- `sendFeishuText`
- `sendFeishuCard`
- `screenPush`

工具调用规则：

- 请求必须短，schema 必须稳定。
- OpenClaw 先 `GET /agent/tools`，再调用工具。
- SmartCore 返回统一 `ok/stat/data/errors`。
- OpenClaw 不直接拼复杂卡片。
- OpenClaw 不读 SQLite、不改备份、不碰 `.env`。

## OpenClaw 失败治理

之前请求失败多次，主要风险是 skill 太厚、schema 不稳定、自然语言链路太长。

新设计要求：

- skill 从零重写，不保留旧文件。
- tool schema 以 `/agent/tools` 为准，skill 只描述调用策略。
- 每个工具请求体尽量小，不嵌套过深。
- Feishu 消息进入后，SmartCore 先记录 `msgLog`。
- OpenClaw 超时或失败时，SmartCore 给 Feishu 一个简短反馈。
- 同一消息失败不得无限重试。
- 错误必须在 `/work/logs` 可见。

## 交互策略

取消旧确认卡片模式。

新策略：

- 明确新增：直接创建，返回“已加入”。
- 明确完成：直接完成，返回“已完成”。
- 明确删除：软删除，返回“已取消，可撤销”。
- 模糊修改：先追问，不创建确认卡片。
- 高风险批量操作：先列候选并询问一句自然问题。
- 所有写操作进入 `actLog`，提供 undo。

## 提醒路由

每分钟 scheduler：

1. 读取 `evtBase`、`lifeEvt`、`ddlEvt`、`courseInst`。
2. 读取最新 `devState`。
3. 生成 due reminders。
4. 如果 `working` 且 `sidePhone` WebSocket 在线，推送副屏。
5. 否则推送 Feishu。
6. 写 `notifyLog`。

副屏推送失败时回退 Feishu。

## 非目标

第一轮不做：

- 旧表兼容。
- 旧 skill 兼容。
- 多用户权限。
- 离线多端同步。
- RSS/weather 成品功能。
- 语音和图片完整闭环。
