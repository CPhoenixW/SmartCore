# SmartCore 文档

本文档集分为两部分：

- `doc/refactor/`：当前准备执行的新架构重构文档，是后续实现和验收的依据。
- 本目录下编号文档：旧版 SmartCore 学生秘书架构记录，仅作为历史参考，不再作为新架构开发目标。

重构时优先阅读 [refactor/README.md](./refactor/README.md)。

## 新架构重构文档

- [重构入口](./refactor/README.md)
- [目标架构](./refactor/target-arch.md)
- [实施计划](./refactor/build-plan.md)
- [验收计划](./refactor/acceptance.md)

## 历史文档索引

- [01-总体架构](./01-overall-architecture.md)
- [02-设备职责与部署](./02-device-roles.md)
- [03-项目与服务结构](./03-project-structure.md)
- [04-网络边界与安全](./04-network-security.md)
- [05-数据备份与恢复](./05-backup-restore.md)
- [06-Cursor CLI 执行计划](./06-cursor-cli-execution-plan.md)
- [07-智能体操作与输出架构](./07-agent-operation-notification-architecture.md)
- [08-GitHub 推送与服务器部署手册](./08-github-push-and-server-deploy.md)
- [09-OpenClaw 与 SmartCore 桥接架构](./09-openclaw-smartcore-bridge.md)

## 历史版本核心结论

- 公网服务器是唯一主控节点，负责数据库、调度器、飞书机器人、Web 面板和备份任务。
- 飞书作为主要交互入口，公网只暴露一个很小的 HTTPS 回调路径。
- 手机和电脑通过 Tailscale 访问内部 Web 面板。
- 树莓派 v1 不跑核心业务，只作为数据库快照备份接收节点。
- 业务逻辑采用规则优先，LLM 只作为后续增强，不作为提醒可靠性的依赖。
