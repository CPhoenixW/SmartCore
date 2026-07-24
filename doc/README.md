# SmartCore 文档

## 当前文档

- [多端项目结构](./25-multi-device-project-layout.md)：Server、Pi、Computer 的代码与依赖边界。
- [部署与回滚](../deploy.md)：候选构建、生产提升、验证和回滚。
- [网络安全](./04-network-security.md)：公网、Tailscale、设备和密钥边界。
- [备份恢复](./05-backup-restore.md)：SQLite 快照、保留和恢复。
- [Pi 通信协议](./10-pi-server-communication-v2.md)：心跳、状态和按需照片。
- [OpenClaw 桥接](./09-openclaw-smartcore-bridge.md)：Agent API 与 Adapter 边界。
- [Action 结果协议](./action-result-protocol.md)：工具执行结果与反馈格式。

`docs/` 保存仍在演进的专题设计；编号文档记录已交付功能的设计或验收背景。
`doc/refactor/` 是 2026-07 重构归档，不再作为待执行计划。

## 文档规则

- README 只说明入口和稳定操作，不重复专题协议。
- 当前事实优先更新本索引列出的文档；历史记录只修正明显错误，不持续扩写。
- 示例不得包含真实域名、IP、token、用户数据或人脸样本。
- 代码路径以 `app/server`、`app/raspberryPi`、`app/computer` 为准。
