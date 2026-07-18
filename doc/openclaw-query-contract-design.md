# OpenClaw 查询契约收敛设计

## 目标与验收

- 单日查询使用 `date: YYYY-MM-DD`，范围查询只使用 `timeRange.start/end`。
- `start_time`、`end_time`、`filter` 等未知字段不得静默忽略，接口返回明确失败。
- OpenClaw 直接读取 `data.items`、`data.count`、`data.total`，不得截断响应后自行过滤。
- 每次 Adapter 镜像启动时，将镜像内同版本 SmartCore Skill 原子同步到 OpenClaw 工作目录。
- 2026-07-20 的线上只读查询应返回“实习 10:00–19:00”。

## API 契约

保留一个规范事件查询接口和一个兼容别名：

- `POST /agent/db/query_events`
- `POST /agent/evtQuery`（兼容别名）

辅助只读接口：

- `GET /agent/tools`：当前工具和 JSON Schema。
- `GET /agent/context`：服务器时间、时区和星期规则。

事件查询支持 `date`、`timeRange`、事件类型、状态、文本、事件 ID、关联计划、
提醒可见性和数量上限。返回结构固定为 `data.items/count/total`。

## 安全边界

- Agent Token 继续认证调用方。
- 每条飞书消息的签名 Scope 决定 `userId/botId/chatId`；请求体不能覆盖用户。
- Skill 不读取数据库、备份、环境文件或令牌内容。
- 未知查询字段返回业务失败，不回退为全量查询。

## 数据与 UI

- 无数据库迁移，无数据写入，无前端状态变化。
- Skill 文件随 Adapter 镜像版本化；同步只覆盖受控的 SmartCore `SKILL.md`。

## 测试矩阵

- 正确的 `date` 和 `timeRange` 查询。
- 拒绝 `start_time/end_time`、`filter` 及未知字段。
- 请求体伪造 `userId` 仍由 Scope 覆盖。
- 缺少或伪造 Scope 返回 401。
- Skill 契约、镜像打包和 Adapter 启动同步。
- Ruff、pytest、Vitest、前端构建、`/healthz`。

## 发布与回滚

- 合入 `dev` 后生成 App 与 Adapter 同 SHA 候选镜像。
- 验证后将同一镜像提升到生产，不在生产重新构建。
- 回滚到上一 SHA 时，旧 Adapter 镜像会同步其对应 Skill。
