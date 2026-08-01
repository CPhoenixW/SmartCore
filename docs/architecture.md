# 系统架构

SmartCore 是服务器主控的个人事务系统。Server 是唯一权威节点；Web、手机副屏、
Raspberry Pi 和电脑监视器都是客户端。

```text
Feishu -> Cloudflare/Caddy -> POST /feishu/event -> Server -> OpenClaw Adapter
Pi ---------------------------------------------> Server device API
Vue / Computer / Screen ------------------------> Server HTTP/WebSocket
Server scheduler -------------------------------> Screen or Feishu
```

## 运行节点

| 节点 | 职责 | 不允许 |
|---|---|---|
| Server | SQLite、业务规则、调度、飞书、Agent API、Web | 公开内部 API 或数据卷 |
| Raspberry Pi | 本地识别、状态上报、按需照片、本地日志 | 直接写库、决定提醒 |
| Vue 工作台 | 查询和编辑当前用户数据 | 客户端指定数据所有者 |
| Phone Screen | 展示状态和提醒、回传提醒操作 | 保存主数据 |
| Computer | 采集客观使用状态，离线排队后批量上传 | 导入 Server 模块、判断效率或任务内容 |
| OpenClaw | 自然语言理解和多步工具编排 | 访问 SQLite、卷、备份或密钥 |

端侧依赖方向固定为 `client -> versioned Server API/WebSocket`。Server 不导入端侧
实现，端侧也不能导入 `app.server`。

## 代码布局

```text
app/server/             FastAPI 与全部权威业务
app/raspberryPi/yolo/   Pi 识别和状态客户端
app/computer/macos/     Swift LaunchAgent 监视器与本地 SQLite 队列
frontend/               Vue 工作台，构建后由 Server 托管
openclaw/               Adapter 与 SmartCore skill
deploy/                 Compose、Caddy 和设备配置
scripts/                验证、发布、备份和恢复
```

Server 内部按领域组织：

- `api/`：浏览器业务 API；会话用户决定数据范围。
- `auth/`：密码、session、管理员 active-user 上下文。
- `new_core/`：SQLAlchemy 模型、CRUD、事项关系和领域服务。
- `agent/`：受 token 和短期 scope 保护的 OpenClaw 工具。
- `feishu/`：回调验证、机器人、会话绑定、消息和卡片。
- `user_device/`、`device/`：通用配对/分发与 Pi 状态/照片。
- `computer/`：电脑活动写入、心跳、统计、Plan 时间重叠、连续工作块注释与明细清理。
- `scheduler/`：提醒、日报和天气任务。
- `screen/`：手机副屏及 WebSocket。

`app/server/main.py` 是唯一组装点，`agent/assembly.py` 为每个重复 Agent operation
显式指定唯一 handler。当前仍保留少量标记 deprecated 的旧别名；新集成必须以
`GET /agent/tools` 返回的契约为准，不依赖内部模块或旧别名。Agent path/status 调用量
持久化用于决定兼容入口何时可安全移除，统计不包含请求正文或凭证。

## 权威与所有权

- Server 是唯一数据库写入方，所有业务记录都归属一个 `userId`。
- 浏览器归属来自数据库验证且可撤销的 opaque session；普通用户的 actor 和 active user 相同。
- 管理员可切换 active user，但审计仍记录实际 actor。
- 设备归属来自完成的配对和设备 token，不接受请求体自报 owner。
- 飞书归属来自已验证机器人、身份和聊天绑定。
- OpenClaw 写操作同时需要 Agent token 与 Server 签发的短期用户 scope。
- 跨用户资源统一返回拒绝或 not found，避免泄露资源是否存在。

## 网络与安全

- 公网只转发 `POST /feishu/event`。
- `/work`、`/screen`、`/api/*`、`/agent/*`、设备 API、健康检查和 SSH 只走
  Tailscale。
- Pi 只主动连接 Server，不开放摄像头或识别服务端口。
- SQLite、Idea 媒体、设备照片和备份卷不提供静态公网访问。
- 飞书、浏览器、设备和 Agent 使用不同凭证，不能共享一个长期 token。
- `.env`、数据库、备份、日志、附件、人脸样本、模型权重和 SSH 密钥不进入 Git。
- 日志只保留必要的 ID、状态和错误，不记录 token、scope、附件内容或生物特征。

## 调度与降级

APScheduler 运行在 Server 内：

- 事项提醒由确定性规则扫描，不依赖 LLM。
- 用户在工位时优先投递副屏，离开时使用飞书；结果写入通知日志并去重。
- 天气从 Open-Meteo 定时刷新；临时失败保留最后一次成功缓存。
- 日报由 Server 创建有用户 scope 的任务，OpenClaw 生成内容，Adapter 验证后持久化
  并投递。
- Computer 工作块边界由 Server 确定性维护；Server 将脱敏聚合直接交给
  正式版 `deepseek-v4-flash-0731` 做一次结构化主题、总结和 Plan 语义匹配。
  连续 active 五分钟建立工作块，累计 active 二十分钟更新同一标题与总结，此后每新增
  六十分钟 active 再滚动更新；连续 idle 五分钟的注意力提醒由 Server 确定性发送，
  不调用模型，也不提前关闭工作块。
  模型或校验失败时记录失败，不默认回退到 OpenClaw；兼容回退必须由部署配置显式开启。
  租约与退避不阻断原始活动上传。
- 电脑活动明细每日清理，日汇总不随明细过期。

外部模型、OpenClaw 或飞书失败不能阻断数据库、设备状态和核心提醒扫描。
