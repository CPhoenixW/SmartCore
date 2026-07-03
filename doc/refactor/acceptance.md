# 验收计划

本验收计划以服务器测试为主。本地只需要保证文档和源码框架可读，不作为最终集成判断。

## 基础原则

- 新架构不兼容旧架构。
- 旧表、旧 skills、旧确认卡片流都可以删除。
- 每次 server 测试前先备份。
- 测试数据库和生产数据库分离。
- 真机链路必须在 Tailscale 中验证。

## 本地轻量检查

本地只做：

```bash
git status --short
python3 -m ruff check .
```

如果没有本地依赖，可以跳过测试执行，但不能跳过文档和 diff 检查。

## 服务器测试准备

在 server 上执行：

```bash
ssh server
cd /opt/smartcore
docker ps
curl http://100.65.243.93:8000/healthz
```

测试前必须：

- 备份 SQLite。
- 备份 deploy `.env`。
- 使用测试数据库或测试 compose project。
- 记录当前容器状态。

## DB 验收

必须验证：

- `evtBase` 可创建。
- `lifeEvt` 可创建并引用 `evtBase`。
- `ddlEvt` 可创建并引用 `evtBase`。
- `courseTpl` 可创建。
- `courseInst` 可创建并引用 `courseTpl` 和 `evtBase`。
- `idea` 可创建。
- `ideaToEvt` 可创建。
- `devState` 可写入。
- `notifyLog`、`msgLog`、`actLog` 可写入。
- 删除或取消事件后状态正确。
- `actLog` 可用于撤销。

不验收：

- 旧表查询。
- 旧表迁移。
- 旧接口兼容。

## API 验收

必须验证：

- `GET /api/evt`
- `POST /api/lifeEvt`
- `POST /api/ddlEvt`
- `POST /api/courseTpl`
- `GET /api/courseInst`
- `POST /api/idea`
- `POST /api/idea/{ideaId}/toEvt`
- `POST /dev/state`
- `GET /api/devState`
- `GET /api/notifyLog`
- `GET /api/msgLog`
- `GET /api/actLog`
- `POST /api/undo/{undoToken}`

验收标准：

- 成功响应短且稳定。
- 错误响应包含明确原因。
- API 只在 Tailscale 内可用。
- 字段命名无下划线。

## OpenClaw 验收

必须验证：

- 旧 `openclaw/skills/smartcore` 已被新 skill 替换。
- `GET /agent/tools` 返回新工具。
- skill 文档中的工具名和 `/agent/tools` 一致。
- 飞书消息能到 SmartCore。
- SmartCore 能转发 OpenClaw。
- OpenClaw 能调用 SmartCore tool。
- 请求失败时不会无限重试。
- 失败日志进入 `msgLog`。

典型场景：

- “今天有什么”
- “今晚八点提醒我写报告”
- “记个灵感：把副屏做成低干扰模式”
- “把报告取消”
- “我刚才那个撤销”

验收标准：

- 明确请求不弹机械确认卡片。
- 模糊请求自然追问。
- 常见请求不需要多次失败重试。

## 飞书验收

必须验证：

- URL verification。
- token/signature 校验。
- 文本消息接收。
- card/action 可接收。
- OpenClaw 超时时有简短反馈。
- 公网只暴露 `/feishu/event`。

## Pi 验收

在 Pi 上验证：

```bash
ssh Pi
curl -X POST http://server-tailnet:8000/dev/state \
  -H 'Content-Type: application/json' \
  -d '{"devId":"pi","state":"working","confidence":0.9,"seenAt":"2026-07-03T13:00:00+08:00","meta":{}}'
```

验收标准：

- server 收到状态。
- `/api/devState` 显示最新状态。
- 心跳过期后状态变为 `unknown`。

## 手机副屏验收

在手机副屏浏览器打开：

```text
http://server-tailnet:8000/screen
```

必须验证：

- 页面能打开。
- WebSocket 能连接。
- 页面显示时间。
- 页面显示 `devState`。
- working 时显示待办和下一事项。
- away/unknown 时显示简洁界面。
- server 能推送提醒。
- 副屏断线不影响 server。

## 提醒路由验收

必须验证：

- `devState=working` 且副屏在线：提醒到副屏。
- `devState=away`：提醒到 Feishu。
- `devState=unknown`：提醒到 Feishu。
- 副屏离线：fallback Feishu。
- 每次投递写 `notifyLog`。
- 同一 `dedupKey` 不重复发送。

## Web 工作台验收

电脑通过 Tailscale 打开：

```text
http://server-tailnet:8000/work
```

必须验证：

- 创建 lifeEvt。
- 创建 ddlEvt。
- 创建 courseTpl。
- 查看 courseInst。
- 记录 idea。
- idea 转 evt。
- 查看 devState。
- 查看 notifyLog/msgLog/actLog。
- 撤销一次写操作。

## 切换前最终检查

必须确认：

- 没有提交 `.env`。
- 没有提交数据库。
- 没有提交备份。
- server 上有回滚备份。
- 新服务 healthz 正常。
- Feishu 回调正常。
- 副屏正常。
- Pi 状态正常。
- scheduler 正常。

## 本轮文档验收

本轮只检查：

- `doc/refactor/README.md` 存在。
- `doc/refactor/target-arch.md` 存在。
- `doc/refactor/build-plan.md` 存在。
- `doc/refactor/acceptance.md` 存在。
- 旧编号重构文档已删除。
- `doc/README.md` 不再把新架构和历史编号文档混成同一套版本。
