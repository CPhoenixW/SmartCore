# SmartCore 手机助手与个人设备控制优化计划

## 已确认需求

- 主要使用场景是本人手机上的 PWA，侧边栏需要更少、更适合单手操作。
- 助手体验参考 Grok：请求发出后先显示自然语言承接，再显示正在查询/调用工具/整理结果等运行状态，最后输出答案。
- 日期和时间必须以 Server 的可信当前时间为准，避免模型自行猜年份。
- 服务器通过 Tailscale 访问本人 Mac，助手可以在明确边界内读取状态并执行少量安全操作，逐步接近个人助手体验。
- 课程、DDL 和确定性提醒需要支持手机通知；PWA 未安装或未授权时仍保留站内通知和 Screen 降级。
- 允许调整 PWA、Server、DSH bridge 和部署配置；部署目标沿用候选环境 -> 生产提升流程，保留现有数据库和回滚路径。

## 环境证据

- PWA 当前侧边栏包含 10 个入口；移动端只有抽屉菜单，没有底部主导航。
- `POST /api/assistant/message` 通过同步 HTTP 请求等待 DSH 最终答案；DSH bridge 已收到 `session.status` 和 `tool/call` 事件，但当前全部丢弃，因此 PWA 只能一次性看到最终文本。
- DSH prompt 没有注入当前 Server 时间；截图中模型把当前日期推断成 2025 年。
- Server 当前时区是 `Asia/Shanghai`，显示时间与系统日期一致，但 `chrony` 尚未同步到 NTP，需要校时并增加可观测性。
- Server 的 Tailscale 已看到在线的 Mac peer：`phoenix-macbook-air.tail59b7ac.ts.net` / `100.67.156.123`；22 端口可达，但没有可用的 SSH 身份或别名。
- 现有通知只写 `notifyLog` 并推送 Screen，PWA 没有 Push subscription 和 Service Worker `push` 处理。

## 实施范围

### A. 手机优先工作台

- 将导航收敛为“总览、助手、课表、添加”四个主入口；每日总结、灵感、设备、日志、设置放入“更多”抽屉。
- 手机端增加固定底部导航和安全区适配；保留桌面端侧栏，但减少视觉噪声和菜单层级。
- 顶部搜索改为可收起的入口，避免占用手机首屏；页面操作按钮满足 44px 触控尺寸。
- 不改变现有路由和权限，只改变入口组织方式，保证旧链接继续可用。

### B. Grok 风格助手流式体验

- DSH bridge 新增受保护的 SSE endpoint，转发 `assistant/message`、`tool/call`、`tool/result`、`session.status` 的脱敏事件。
- Server 新增 `/api/assistant/stream`，从已认证浏览器 session 派生 scope，代理 DSH SSE；旧 `/api/assistant/message` 保留兼容。
- 前端按事件增量显示：立即承接、理解中、查询/写入某类资料、整理结果、完成；模型在工具调用前的自然语言优先展示，缺失时由 UI 提供短承接。
- 工具名只显示人类可读类别，不泄露内部参数、scope、ID 或数据库结果；断线时保留已收到文本并提供重试。
- DSH prompt 强制“先用一句话说明将要查询或修改什么，再调用工具；完成后再总结”。

### C. 时间可信链路

- Server 为每次助手事件注入 `serverNow` 和经过校验的 IANA `timezone`，DSH prompt 明确“以该时间为准，不自行猜年份”。
- 增加只读 `/api/runtime/clock`，返回 Server 当前时间、UTC 偏移、时区和同步状态，用于 PWA 状态诊断和测试。
- 检查并修复生产主机 chrony/NTP；部署后验证系统时间、应用时间、数据库写入时间和模型查询上下文一致。
- 前端事件显示统一使用带偏移的 ISO 时间，避免把无时区字符串当作本地时间。

### D. 手机通知

- 增加 `pushSubscription` 持久化表和 owner-scoped 注册/注销接口。
- Service Worker 处理 `push` 和点击跳转；PWA 增加“开启手机通知”入口，显示浏览器/安装状态和授权结果。
- `notifyLog` 保持为统一历史记录；提醒优先走 Web Push，未配置 VAPID、未订阅或投递失败时写明原因并降级到 Screen/站内历史。
- 课程开始前、DDL 以及现有确定性提醒沿用 Server scheduler 和 dedup 规则，不把提醒时序交给 DSH。
- 部署生成并保存 VAPID 密钥，只进入 server env，不写入仓库。

### E. Tailscale 个人设备助手

- 先完成 Tailscale DNS/SSH 基线：固定 Mac 别名、主机指纹、专用最小权限密钥和连接健康检查；不把私人密钥放进容器镜像或 Git。
- 增加独立 `computer-control` 内部服务/客户端，Server 通过鉴权 API 调用，DSH 只看到高层 Agent 工具，不直接拥有 shell、数据库或文件系统能力。
- 第一批只开放可审计的只读能力（在线状态、当前前台应用/窗口的已脱敏摘要、系统基本信息）和少量可逆动作（打开 URL、发送本地通知）；所有动作需 user scope、allowlist、超时和审计日志。
- 本轮暂不实现 SSH/Mac 控制；先完成 PWA、助手、时间和 Push。SSH/Mac 控制作为下一阶段，沿用本计划的安全边界。

## 本轮交付边界

本轮交付 A-D；E（Tailscale 个人设备助手）延期到下一阶段，不影响本轮 PWA、助手和提醒功能。

## 文件与组件

- `frontend/src/layouts/WorkLayout.vue`、`frontend/src/views/AssistantView.vue`、`frontend/src/api/assistant.ts`、`frontend/src/styles/*`、`frontend/src/locales/*`。
- `dsh/bridge/server.mjs`、`dsh/bridge/patch.yml`。
- `app/server/api/assistant_routes.py`、新增通知/运行时路由、`app/server/config.py`、`app/server/new_core/notify.py`、`app/server/new_core/models.py`、`app/server/scheduler/*`。
- `frontend/public/sw.js`、`frontend/public/manifest.webmanifest`、数据库 schema/migration、部署 env 示例与 `deploy/docker-compose.yml`。
- Tailscale/SSH 只修改服务器运行配置和用户明确授权的 Mac 配置；凭证和生产数据不进 Git。

## 验证矩阵

- Frontend: Vitest（导航、流式助手状态、时间格式、Push 注册降级）、`npm run build`。
- Backend: assistant SSE contract、时间路由、通知订阅 owner isolation、dedup/fallback、schema migration、全套 pytest 与 ruff。
- DSH: bridge SSE 事件顺序、工具调用脱敏、最终答案和旧 query endpoint 兼容。
- E2E 候选环境: 登录 -> 手机 PWA -> 助手查询（先承接/状态再答案）、当前时间查询、课程/DDL 通知注册和测试投递、Mac 控制健康检查。
- 生产发布: 复用已验证镜像，检查 `/healthz`、`/api/runtime/clock`、manifest/sw/icon、DSH health、数据库备份和回滚状态。

## 风险、数据和回滚

- 新增表只追加，不删除或重写现有事项/提醒；旧 `notifyLog` 数据可继续读取。
- Web Push 依赖浏览器授权和 VAPID 配置；未满足条件时保留 Screen/站内降级。
- SSE 不改变旧同步 API；前端失败可回退到同步请求。
- 设备控制默认拒绝未知动作，SSH 连接失败不影响事务、调度和 PWA。
- 每次候选部署前备份数据库；生产失败按现有 `promote_prod.sh` 回滚到上一镜像和 env 备份。

## 性能基线

- 当前助手请求为同步等待，用户首个可见反馈延迟等于完整模型/工具链耗时；改造后测量首个 `status` 事件、首个承接文本、首个工具事件和最终答案的 p50/p95。
- PWA 测量移动端首屏请求数、构建体积和助手 SSE 连接错误率；不对生产做压力测试。
