# 普通用户共享飞书机器人配对

## 目标

普通用户通过 Device 页面绑定系统默认飞书机器人，不需要管理机器人密钥，也不依赖管理员专用页面。

## API

- `POST /api/feishu/pair/start`
  - 使用当前登录用户和已启用的系统默认机器人创建或复用 `FeishuChatPair`。
- `GET /api/feishu/pair/{pairId}`
  - 仅允许配对记录所属用户查看状态。
- `POST /api/feishu/pair/{pairId}/confirm`
  - 仅允许所属用户确认已经由飞书会话认领的记录。
- `GET /api/feishu/bindings`
  - 返回当前用户自己的有效飞书会话绑定。
- `DELETE /api/feishu/bindings/{bindId}`
  - 仅删除当前用户自己的绑定。

所有响应只包含配对、机器人显示名称和会话摘要，不返回 App Secret、Verification Token、Encrypt Key 或完整飞书身份。

## 权限与运行规则

- 默认机器人必须处于启用状态；普通用户不能读取或修改机器人配置。
- 消息回复和提醒以 `FeishuBind.userId + botId + chatId` 为授权边界，不再要求机器人归该用户所有。
- 非默认用户未绑定飞书时不得回退到系统管理员的默认聊天。
- 共享机器人确认绑定时不得覆盖机器人所有者的 `defaultChatCipher`。

## 数据与回滚

- 不新增表或字段，无数据库迁移。
- 旧 `DevicePair(deviceKind=feishuBot)` 保留但 Device 页面不再创建；现有未完成记录自然过期。
- 回滚只需恢复上一版应用镜像，已有 `FeishuBind` 数据仍兼容。

## 验收

- 普通用户可以启动、认领、确认并查看自己的飞书绑定。
- 用户不能读取、确认或删除其他用户的配对与绑定。
- 绑定后机器人输入、OpenClaw 回复和提醒均回到该用户自己的会话。
- 未绑定普通用户不会收到或触发发送到管理员默认会话。
- Ruff、pytest、Vitest、前端构建与 `/healthz` 通过。
