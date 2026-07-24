# 重构验收归档

重构验收覆盖：

- 数据库关系、事件 CRUD、提醒去重和审计。
- 飞书、OpenClaw Agent API、Pi 心跳和副屏 WebSocket。
- Vue 工作台、认证与多用户隔离。
- Docker 候选构建、生产健康检查、备份和回滚。

当前每次发布必须通过后端测试、Ruff、前端测试与构建、候选容器健康检查，随后
使用 `scripts/promote_prod.sh` 提升。操作命令见 [deploy.md](../../deploy.md)。
