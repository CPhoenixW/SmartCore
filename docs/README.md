# SmartCore 文档

这里仅保存需要随代码持续维护的现行说明。已完成需求的验收单、一次性实施计划和
旧架构审计不再单独留文件；需要追溯时使用 Git 历史和根目录
[`CHANGELOG.md`](../CHANGELOG.md)。

## 阅读入口

| 文档 | 内容 |
|---|---|
| [项目 README](../README.md) | 项目定位、目录、本地开发和最短发布路径 |
| [Agent 指南](../AGENTS.md) | 模型自动入口、任务地图、不变量、验证和安全规则 |
| [系统架构](./architecture.md) | 运行拓扑、代码边界、权限与安全原则 |
| [领域模型](./domain-model.md) | 用户、事项、提醒、设备、日志和定时任务 |
| [API 与鉴权契约](./api-contracts.md) | 凭证矩阵、关键接口、状态机和兼容别名 |
| [飞书与 OpenClaw](./integrations.md) | 回调、配对、Agent scope、工具与输出契约 |
| [Idea 与媒体](./media.md) | 上传、多模态分析、附件编辑、存储和鉴权 |
| [设备与 Pi](./devices.md) | 设备配对、分发、Pi 状态和照片协议 |
| [架构决策](./decisions.md) | 关键方案原因、拒绝方案和当前技术债 |
| [交付历史](./delivery-history.md) | 影响后续维护的里程碑与验收边界 |
| [发布与恢复](../deploy.md) | 候选构建、生产提升、备份、验证和回滚 |

## 事实来源

文档描述稳定边界，精确的请求字段和返回结构以运行中的 OpenAPI、
`GET /agent/tools`、数据库模型和测试为准：

- API 组装点：`app/server/main.py`
- 数据模型：`app/server/new_core/models.py`
- 部署配置模板：`deploy/env.example`、`deploy/adapter.env.example`
- OpenClaw skill：`openclaw/skills/smartcore/SKILL.md`
- 回归测试：`tests/`、`frontend/tests/`

## 维护规则

- 一个领域只维护一篇现行文档，不为每个功能提交新增永久验收文件。
- 设计中的内容写进 PR/Issue；合并后只把稳定结论更新到对应领域文档。
- 文档只描述当前行为。迁移经过、已废弃方案和发布记录归 Git 历史或
  `CHANGELOG.md`；长期决策与维护相关里程碑分别进入 `decisions.md` 和
  `delivery-history.md`。
- 不在文档中复制可从 OpenAPI 或 `GET /agent/tools` 获得的完整接口清单。
- 示例不得包含真实域名、IP、token、聊天 ID、用户数据、人脸样本或附件内容。
