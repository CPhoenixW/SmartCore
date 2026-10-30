# 公网域名访问实施计划

状态：待用户确认；尚未实施或部署。
时间：2026-10-13 14:20，Asia/Singapore。

## 已确认需求与验收

- 使用用户已注册的域名作为 HTTPS 入口，根路径进入 `/work`。
- 网页工作台、手机副屏、Pi 和电脑设备可以从公网连接，无需 Tailscale。
- 禁止公开注册；保留现有账户、设备、业务数据和正常登录。
- 浏览器资源要求有效会话，设备资源要求绑定设备凭证；匿名与跨用户访问拒绝。
- 飞书回调保持兼容；Agent、OpenClaw、SSH、健康与运维入口保持私有。
- 副屏长连接有心跳和重连，凭证不进入代理或应用日志；撤销设备后连接不能继续接收数据。
- 未授权注册、初始化及私有入口不通过公网代理。附件与设备照片继续由 owner-scoped handler 提供。

## 环境证据与约束

- 本地分支 dev，检查时 HEAD 为 f37737e；macOS monitor 有五个已修改文件与三张未跟踪图片，均保留。
- Server 为 FastAPI，SQLite 为唯一主数据库，Vue 构建由 Server 托管。
- Compose 已配置 Cloudflared、Caddy HTTPS 和 HTTP tunnel-boundary；两个代理配置当前只放行飞书回调。
- 浏览器使用可撤销的 opaque session，设备凭证绑定 lifeDevice owner。
- 当前匿名注册无配置开关；setup 在默认账户未初始化时允许匿名调用；登录路径未见专门限流与 CSRF 校验。
- Pi 心跳广播未传 owner，ScreenManager 默认向所有连接广播，必须修复。
- 副屏 WebSocket 使用 URL 查询参数携带设备 token，必须处理日志与生命周期。
- 未访问线上服务器；生产部署状态、默认账户初始化状态、实际隧道与 DNS 配置尚待核对。
- 生产只能经 dev 候选和 promote_prod.sh 提升；禁止直接修改生产 checkout 或覆盖数据。

## 实施方案与文件范围

1. 在 auth/config 增加可配置的注册与初始化策略，生产禁止公开注册；前端依据服务端能力隐藏注册入口，服务端直接调用也必须拒绝。
2. 为浏览器写请求增加同源校验或 CSRF 保护，正确识别受信代理后的 HTTPS/origin；设备 token 与飞书回调使用各自验证规则。
3. 为登录与配对增加限流，并明确可信代理/IP 来源，防止伪造转发头绕过；生产启用 Secure Cookie。
4. 修复 Pi 心跳广播的用户范围，检查副屏凭证撤销、心跳和重连；评估短期 WebSocket ticket，避免长期 token 出现在连接 URL。
5. 审计拟开放的路由及头像/媒体读取，按 method/path 建立公网允许清单；两个 Caddy 入口采用一致策略，其他路径拒绝。
6. 域名根路径跳转 /work；Cloudflare Tunnel 指向边界代理，App 的内部端口不改为全网监听。业务响应与私有文件禁止公共缓存，日志过滤敏感查询字段。
7. 更新配置示例及现行架构/API/部署/设备文档、AGENTS.md 网络不变量、decisions.md 与 delivery-history.md。

主要涉及 app/server/config.py、auth/、api/auth_routes.py、main.py、device/routes.py、screen/、user_device/，frontend/src/api/auth.ts、views/LoginView.vue，deploy/Caddyfile*、env.example 与必要的发布检查。复用现有工具链，预计无需新框架或数据库迁移；任何新增持久化结构需单独评估兼容性。

## 验证与审查

- 后端认证、设备、副屏、所有权、媒体、Agent 合约与 smoke 测试；增加注册关闭、同源校验、限流、跨用户广播及撤销连接的行为测试。
- 前端登录/配对相关测试与构建，随后完整 pytest、ruff、npm test/build。
- 验证两个 Caddy 配置的语法、允许入口与拒绝入口，包括不同 method、尾斜杠和编码路径。
- 候选容器启动与 /healthz，隔离数据验证完整登录、配对、心跳、上传、副屏 WS 与飞书回调。
- 审查凭证/日志/缓存、可信转发头、旧客户端兼容、权限范围、配置回滚与未提交工作隔离。
- 性能：重点测登录限流开销、设备正常心跳和 WS 重连；只在隔离候选测量，不对生产做负载测试。

## 发布依赖、数据与回滚

- 上线前需核对域名 DNS 是否接入 Cloudflare、现有隧道 hostname、服务器实际部署与账户初始化；不索取或输出密钥。
- 现有设备 token 预期保持有效，但更换 Server URL/浏览器 origin 后可能需要更新端侧配置或副屏重新配对；Mac 凭证与 Server URL 关联，需验证迁移方式。
- Secure Cookie 会影响旧 HTTP 浏览器访问，生产网页以 HTTPS 域名为正式入口，Tailscale 保留运维用途。
- 不删除用户、附件、设备或业务数据；不重置数据库。
- 发布前保存旧网络配置并使用现有 SQLite 备份流程；失败使用现有镜像回滚，并同步恢复 Caddy、DNS/隧道及生产环境配置。仅回滚 App 镜像不足以恢复网络策略。

## 授权边界

- 当前阶段仅完成检查与本计划；待用户确认后实施本地代码与验证。
- Git 提交/推送、远程访问、DNS/隧道修改和生产发布尚未获明确授权，不执行这些动作。
- 本地验证完成后展示结果，按用户后续授权进入候选和生产流程。
