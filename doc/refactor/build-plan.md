# 实施计划

本计划按“先删除旧结构，再建立新内核，再接设备”的顺序执行。旧架构不兼容、不迁移到运行路径。生产数据如需保留，只能先导出为人工可读备份，再按新模型重新导入。

## 阶段 0：服务器准备

目标：保证可以在 server 上安全测试和回滚。

任务：

- `ssh server` 进入服务器。
- 在 `/opt/smartcore` 或新的 server 工作目录拉取重构分支。
- 备份当前 SQLite、`.env`、docker compose 配置。
- 记录当前容器状态和健康检查。
- 准备测试数据库，不直接覆盖生产数据库。
- 明确 server 上的测试命令。

验收：

- server 上有可恢复备份。
- 可以在 server 上启动测试实例。
- 本地不作为集成测试准环境。

## 阶段 1：删除旧结构

目标：清空旧架构负担。

删除范围：

- 旧 `courses`、`course_sessions`、`assignments`、`life_events` 模型。
- 旧确认卡片流。
- 旧 OpenClaw skill。
- 旧 `/agent/*` tool schema。
- 旧 dashboard 中绑定旧表的页面。
- 旧 scheduler 中绑定旧模型的扫描逻辑。

保留范围：

- FastAPI 应用框架。
- 配置加载框架。
- Feishu 安全校验可参考但要简化接口。
- Docker/Caddy/Tailscale 边界。
- 备份脚本思路。

验收：

- 代码中不再出现旧业务表作为运行路径。
- `openclaw/skills/smartcore` 被重写，不保留旧说明。
- 新测试不要求旧功能通过。

## 阶段 2：新 DB 内核

目标：实现新表和 CRUD 服务。

新增模型：

- `evtBase`
- `lifeEvt`
- `ddlEvt`
- `courseTpl`
- `courseInst`
- `idea`
- `ideaToEvt`
- `devState`
- `notifyLog`
- `msgLog`
- `actLog`

任务：

- 使用无下划线简拼命名。
- 字段使用 lowerCamel。
- 实现 SQLite 初始化。
- 实现基础 service 层。
- 每个写操作记录 `actLog`。
- 删除操作默认软删除或写 `stat=cancelled`。

验收：

- server 测试库能创建全部表。
- 每个主表至少能 create/read/update/delete。
- 删除 `evtBase` 能级联删除子表。

## 阶段 3：内部 API

目标：供 `/work` 和设备调用。

任务：

- 实现 `/api/evt`。
- 实现 `/api/lifeEvt`。
- 实现 `/api/ddlEvt`。
- 实现 `/api/courseTpl`。
- 实现 `/api/courseInst`。
- 实现 `/api/idea`。
- 实现 `/api/devState`。
- 实现 `/api/notifyLog`、`/api/msgLog`、`/api/actLog`。
- 实现 `/api/undo/{undoToken}`。
- 实现 `/dev/state` 给树莓派上报。

验收：

- 只在 Tailscale 内部可访问。
- 错误返回短而明确。
- API 命名符合无下划线风格。

## 阶段 4：OpenClaw bridge 和新 skill

目标：降低 OpenClaw 失败率和反馈延迟。

任务：

- 删除旧 `openclaw/skills/smartcore` 内容。
- 重写 `SKILL.md`。
- 新 skill 只声明边界、工具发现、调用顺序。
- `/agent/tools` 返回小而稳定的 schema。
- `/feishu/event` 接收后转发 OpenClaw。
- OpenClaw 失败时写 `msgLog` 并简短反馈。
- 不再使用旧确认卡片流。

推荐 agent tools：

- `evtQuery`
- `evtCreate`
- `evtUpdate`
- `evtDelete`
- `ideaCapture`
- `ideaToEvt`
- `sendText`
- `sendCard`
- `screenPush`

验收：

- 同一条飞书消息不会失败后无限重试。
- schema 错误能在 server 日志和 `/work/logs` 看见。
- 常见请求一次完成或一次自然追问。

## 阶段 5：树莓派状态链路

目标：server 能使用 Pi 的工作状态。

任务：

- server 实现 `/dev/state`。
- Pi 端从 `yolo` 进程取状态。
- Pi 每隔固定时间 POST：

```json
{
  "devId": "pi",
  "state": "working",
  "confidence": 0.92,
  "seenAt": "2026-07-03T13:00:00+08:00",
  "meta": {}
}
```

- server 超时未收到则 state 视为 `unknown`。

验收：

- `ssh Pi` 后可以手动 curl server 上报。
- server `/api/devState` 能看到状态变化。

## 阶段 6：手机副屏

目标：副屏通过 Tailscale 直接连接 server。

任务：

- 实现 `/screen` 页面。
- 实现 `/screen/ws`。
- WebSocket 首包发送当前状态。
- 定时推送时间和当前摘要。
- scheduler 可向副屏推送提醒。
- 副屏断线后 server 清理连接。

验收：

- 手机副屏浏览器可打开 `http://server-tailnet:8000/screen`。
- 页面不需要 Cloudflare。
- WebSocket 断线不会影响 server。

## 阶段 7：提醒路由

目标：根据工作状态选择通知通道。

任务：

- 实现 notify router。
- `working` 优先副屏。
- `away` 优先 Feishu。
- `unknown` 优先 Feishu。
- 副屏失败 fallback Feishu。
- 每次投递写 `notifyLog`。

验收：

- 手动设置 `devState=working` 时提醒到副屏。
- 手动设置 `devState=away` 时提醒到 Feishu。
- 副屏离线时自动回退。

## 阶段 8：电脑工作台

目标：Linux PC 和 MacBook 高效编辑数据。

任务：

- 实现 `/work`。
- 页面包括：
  - today
  - evt
  - lifeEvt
  - ddlEvt
  - courseTpl
  - idea
  - devState
  - notifyLog
  - msgLog
  - actLog
- 表单尽量短。
- 支持撤销入口。
- 自然语言输入作为后续增强，不替代表单。

验收：

- 电脑端能完成核心 CRUD。
- 页面不显示 token、secret、`.env`。

## 阶段 9：服务器验收和切换

目标：在 server 上完成真实验收。

任务：

- server 测试实例跑全量测试。
- 使用测试 Feishu 或受控 chat 验证。
- 使用 Pi 手动或真实上报验证。
- 使用手机副屏真实浏览器验证。
- 确认后停止旧服务，切换新服务。

验收：

- `/healthz` 正常。
- `/work` 正常。
- `/screen` 正常。
- `/feishu/event` 正常。
- scheduler 正常。
- 日志无持续异常。
