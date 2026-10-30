# SmartCore 手机 PWA 与 DSH 迁移计划

创建时间：2026-10-30 14:33（Asia/Singapore）

> 本计划根据“直接用 DSH 替代 OpenClaw、PWA 作为唯一交互入口”的决定修订。

## 目标

为单一个人用户提供一个手机优先的 SmartCore 入口，并将模型会话与工具编排迁移到 DeepSeek Harness（DSH）。SmartCore 继续是唯一数据库写入者和权限边界；DSH 只通过一个受限 MCP 工具桥访问 Server Agent API，不读取 SQLite，也不获得 shell 或文件系统工具。

## 已确认范围

- 手机端先做跨平台 PWA，不先做 iOS/Android 原生 App。
- 直接使用 DSH 替换 OpenClaw 主路径，允许调整交互和工具契约。
- 删除飞书机器人入口、回调、配对、管理页、投递工具和部署公开路由；PWA 是唯一交互入口。
- 本次目标包含候选环境部署；不执行生产提升、不重置生产数据、不直接编辑生产目录。
- 当前服务可以在候选切换时暂停；旧 OpenClaw 配置保留用于回滚。
- 保留现有数据库所有权、用户 scope、媒体隔离和 Server 唯一写入原则。
- 工作区现有未提交修改必须保留，不覆盖、不回滚。

## 现状证据

- 前端当前以桌面工作台为中心，OverviewView 有日程/天气/设备/Idea，但没有移动 Today 工作流。
- Vite 没有 PWA manifest、service worker 或移动助手入口。
- OpenClaw adapter 同时承担事件接收、提示词拼接、子进程、媒体 staging、日报校验和失败回写，约 1176 行；它不再属于默认链路。
- Agent 工具目录基础约 20 个，动态反馈工具和 serverContext 后约 25 个；Computer 内部工具不适合暴露给普通个人对话。
- DSH 官方 sdk-minimal profile 提供长驻 JSON-RPC 会话；官方 MCP client 可将受限外部工具接入模型。

## 设计

### A. 手机 PWA 第一阶段

1. 保留现有 `/work` 桌面工作台，增加 manifest、service worker、安装元数据和移动 Assistant 路由。
2. 移动 Assistant 使用浏览器 session 调用 `/api/assistant/message`，由 Server 将请求转给 DSH，并返回完整的助手结果。
3. 离线只缓存用户明确发送的文本草稿；请求失败时保留在本地 Inbox，不静默丢弃。
4. 第一阶段不引入 Web Push；推送作为后续垂直切片接入现有通知路由。

### B. DSH 运行时替换

1. 使用精确版本的官方 `sdk-minimal` 作为会话内核，外加官方 Pi-AI provider 连接现有 OpenAI-compatible gateway。
2. 通过受限 MCP server 暴露 SmartCore 高层动作：今日上下文、事项查询/创建/更新/完成/删除、Idea 捕获/转事项、媒体读取和 Screen/日报相关动作。
3. MCP server 只调用 `/agent/*` API，携带 Server 签发的 scope；scope 不进入模型提示词，用户归属始终由 Server 推导。
4. DSH bridge 维护每个用户的会话运行时，按来源生成稳定 session id，并提供异步事件入口和同步查询入口。
5. 浏览器、媒体、daily summary、Computer 调度统一切到 DSH endpoint；旧 OpenClaw compose service 改为 rollback profile。

### C. 候选部署与验证

- 本地运行 DSH 协议/MCP 冒烟、相关 Python 测试、ruff、前端测试和构建。
- 扩展仓库候选 compose/build/health 流程，验证 app 与 DSH runtime 两个容器。
- 验证 `/healthz`、`/work`、manifest、service worker、Assistant 认证、Agent scope 和 DSH `/healthz`；确认不存在 Feishu 路由或工具。
- 只有候选 DSH 健康且真实用户路径通过后，才暂停候选中的旧 OpenClaw；不运行生产提升。

## 接受标准

- 手机浏览器可将 SmartCore 安装到主屏幕，助手页面在窄屏可用。
- 浏览器助手请求只接受已登录 session，不能通过请求体指定另一个用户。
- DSH 能启动、建立持久会话、调用 SmartCore MCP 工具并返回文本结果；工具失败会明确返回错误。
- 普通个人对话只看到 SmartCore 高层工具，不看到 shell、文件系统、Computer 内部工具或数据库凭据。
- PWA、daily summary、Computer 后台路径仍能通过 scope 完成现有 Server API 操作；日常提醒只写入 PWA/Screen。
- 现有核心回归测试通过，前端测试/构建通过，候选环境两个健康检查通过。
- OpenClaw rollback profile 和旧镜像标签仍可恢复服务。

## 风险与回滚

- DSH 当前为预览版本；依赖版本固定，启动时验证 profile 组合，升级只通过显式版本变更。
- 模型网关必须支持 DSH Pi-AI 的 OpenAI Chat Completions 流式协议；配置错误时 DSH 健康检查仍可启动，但助手请求会返回可诊断错误。
- PWA service worker 使用版本化 cache key；异常时可卸载 service worker 后回到普通 `/work`。
- 候选切换失败时保留 OpenClaw profile 和旧镜像，不触碰生产数据库。

## 性能评估

- 比较 PWA 改动前后生产构建 gzip 体积和助手首屏请求数量。
- 对 DSH 记录启动耗时、MCP 工具发现耗时、首 token/完整响应耗时和每用户常驻内存；不在生产进行压力测试。

## 本轮执行状态（2026-10-30）

- 已完成：PWA 唯一交互入口、DSH 主路径、飞书主动链路删除、前端/路由/部署 allowlist 清理。
- 已验证：后端 198 项、前端 60 项、ruff、Python 编译、前端生产构建、Agent 路由快照和无飞书路由烟测。
- Compose 文件已通过静态 `config` 校验；本机 Docker daemon 不可用，因此没有在本机启动候选容器，也没有触碰生产目录或服务。
- 旧数据库中的机器人表和迁移结构仍保留为兼容层，未创建或激活任何机器人；后续完成数据迁移后再删除这些表。
