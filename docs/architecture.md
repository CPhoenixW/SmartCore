# 系统架构

SmartCore 是服务器主控的个人事务系统。手机 PWA 是唯一交互入口，Server 是唯一权威节点；
Raspberry Pi、电脑监视器和副屏只负责采集或展示。

```text
PWA / Vue -----------------------> Server browser session -> DSH Runtime/MCP Bridge
Pi / Computer / Screen ----------> Server device API or WebSocket
Server scheduler ----------------> PWA daily summaries and Screen notifications
```

## 运行节点

| 节点 | 职责 | 不允许 |
|---|---|---|
| Server | SQLite、业务规则、调度、Agent API、Web 和所有写入 | 公开内部 API 或数据卷 |
| Raspberry Pi | 本地识别、状态上报、按需照片、本地日志 | 直接写库、决定提醒 |
| Vue 工作台/PWA | 查询和编辑当前用户数据、助手对话、读取日报 | 客户端指定数据所有者 |
| Screen | 展示状态和提醒、回传提醒操作 | 保存主数据 |
| Computer | 采集客观使用状态，离线排队后批量上传 | 导入 Server 模块、判断效率或任务内容 |
| DSH Runtime | 会话、模型调用和 MCP 工具编排 | 访问 SQLite、数据库卷、shell 或宿主文件 |

端侧依赖方向固定为 `client -> versioned Server API/WebSocket`。Server 不导入端侧实现，
端侧也不能导入 `app.server`。

## 代码布局

```text
app/server/             FastAPI 与全部权威业务
app/raspberryPi/yolo/   Pi 识别和状态客户端
app/computer/macos/     Swift LaunchAgent 监视器与本地 SQLite 队列
frontend/               Vue 工作台和可安装手机 PWA，构建后由 Server 托管
dsh/                    DSH 运行时、SmartCore MCP bridge 和安全 patch
openclaw/               历史回滚 Adapter 与 skill，不属于默认链路
deploy/                 Compose、Caddy 和设备配置
scripts/                验证、发布、备份和恢复
```

Server 内部按领域组织：

- `api/`：浏览器业务 API；会话用户决定数据范围。
- `auth/`：密码、session、管理员 active-user 上下文。
- `new_core/`：SQLAlchemy 模型、CRUD、事项关系和领域服务。
- `agent/`：受 token 和短期 scope 保护的 Server 工具；DSH 只能通过 MCP bridge 调用。
- `user_device/`、`device/`：通用配对/分发与 Pi 状态/照片。
- `computer/`：电脑活动写入、心跳、统计、连续工作块注释与明细清理。
- `scheduler/`：提醒、日报和天气任务。
- `screen/`：副屏及 WebSocket。

`app/server/main.py` 是唯一组装点，`agent/assembly.py` 保证每个 Agent operation 只有一个
handler。新集成必须以 `GET /agent/tools` 返回的契约为准。旧 Feishu 表和迁移定义只为读取
历史数据库而保留，启动不会创建、启用或访问机器人；没有 Feishu 路由、配置、配对或投递。

## 权威与所有权

- Server 是唯一数据库写入方，所有业务记录都归属一个 `userId`。
- 浏览器归属来自数据库验证且可撤销的 opaque session；普通用户的 actor 和 active user 相同。
- 管理员可切换 active user，但审计仍记录实际 actor。
- 设备归属来自完成的配对和设备 token，不接受请求体自报 owner。
- DSH 写操作同时需要 Agent token 与 Server 签发的短期用户 scope；PWA 助手入口先由浏览器
  session 派生 scope。
- 跨用户资源统一返回拒绝或 not found，避免泄露资源是否存在。

## 网络与安全

- 公网只按配置转发 PWA 的登录、工作台和助手 API；不再暴露机器人回调或机器人管理路径。
- `/work`、`/screen`、`/api/*`、`/agent/*`、设备 API、健康检查和 SSH 只走受信网络边界。
- Pi 只主动连接 Server，不开放摄像头或识别服务端口。
- SQLite、Idea 媒体、设备照片和备份卷不提供静态公网访问。
- `.env`、数据库、备份、日志、附件、人脸样本、模型权重和 SSH 密钥不进入 Git。
- 日志只保留必要的 ID、状态和错误，不记录 token、scope、附件内容或生物特征。

## 调度与降级

APScheduler 运行在 Server 内：

- 事项提醒由确定性规则扫描，不依赖 LLM；实时提醒投递到 Screen，历史记录由 PWA 读取。
- 天气从 Open-Meteo 定时刷新；临时失败保留最后一次成功缓存。
- 日报由 Server 创建有用户 scope 的 DSH 任务，DSH 生成内容，MCP 工具写回后由 PWA 读取。
- Computer 工作块边界由 Server 确定性维护，结构化主题和总结由受限模型调用完成。
- 模型或 DSH 失败只记录失败，不阻断数据库、设备状态和核心提醒扫描。
