# SmartCore 新架构重构入口

本目录是新架构重构的唯一有效文档入口。编号历史文档只记录旧系统，不作为实现依据。

本次重构采用“直接替换”策略：

- 不做旧表兼容。
- 不保留旧 OpenClaw skill。
- 不保留旧确认卡片体验。
- 不在本地完成主要集成测试，服务器是主要测试环境。
- 本地仓库只保存框架、源码、文档和测试定义。

## 文档顺序

1. [目标架构](./target-arch.md)
2. [实施计划](./build-plan.md)
3. [验收计划](./acceptance.md)

## 关键偏好

### 命名

项目内部命名使用无下划线简拼 lowerCamel 风格。

推荐表/模型名：

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

推荐字段名：

- `evtId`
- `tplId`
- `ideaId`
- `evtType`
- `prio`
- `stat`
- `createdAt`
- `updatedAt`
- `dueAt`
- `doneAt`
- `ddlAt`
- `hardDdl`
- `classDate`
- `attendStat`
- `srcType`
- `mediaPath`
- `handled`
- `convertedAt`

避免：

- `schedule_events`
- `course_templates`
- `pendingOperations`
- `event_id`
- `created_at`

### 交互

默认不使用“请确认/确认卡片/待确认操作”作为主要体验。系统应更像助手，而不是表单机器人。

写操作策略：

- 明确请求直接执行。
- 模糊请求先自然追问。
- 高风险操作使用软删除、撤销和审计，而不是机械确认。
- 飞书反馈要短，尽快给结果。

### 部署与测试

服务器是主要运行和测试环境。

- 在 server 上运行真实服务、数据库、OpenClaw 联调、Feishu 回调、WebSocket、scheduler。
- 本地只保留项目框架、文档、测试定义和必要源码。
- 重要验收以 `ssh server` 后的结果为准。

## 后续实现约束

- Cursor 或人工实现不得修改本目录文档，除非用户要求重新设计。
- 可以删除旧代码、旧表、旧 skills，但必须先备份服务器数据。
- 新代码以新架构为准，不追求旧接口兼容。
