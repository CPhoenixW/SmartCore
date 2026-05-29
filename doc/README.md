# SmartCore 学生个人秘书架构文档

本文档集描述 SmartCore v1 的产品与工程架构。目标是构建一个低 API 使用量、服务器主控、飞书可交互、Tailscale 内部协同的学生个人秘书系统。

## 文档索引

- [01-总体架构](./01-overall-architecture.md)
- [02-设备职责与部署](./02-device-roles.md)
- [03-项目与服务结构](./03-project-structure.md)
- [04-网络边界与安全](./04-network-security.md)
- [05-数据备份与恢复](./05-backup-restore.md)
- [06-Cursor CLI 执行计划](./06-cursor-cli-execution-plan.md)

## v1 核心结论

- 公网服务器是唯一主控节点，负责数据库、调度器、飞书机器人、Web 面板和备份任务。
- 飞书作为主要交互入口，公网只暴露一个很小的 HTTPS 回调路径。
- 手机和电脑通过 Tailscale 访问内部 Web 面板。
- 树莓派 v1 不跑核心业务，只作为数据库快照备份接收节点。
- 业务逻辑采用规则优先，LLM 只作为后续增强，不作为提醒可靠性的依赖。
