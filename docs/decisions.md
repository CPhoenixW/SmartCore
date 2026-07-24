# 架构决策与已知约束

本文保留“为什么这样做”。当前行为仍以代码、测试和其他现行文档为准。

## D001 Server 是唯一权威节点

状态：已采用。

数据、业务规则、调度、权限和审计全部归 Server。Pi、Web、Screen、Computer 和
OpenClaw 都是客户端。

原因：避免不同设备各自写数据、重复提醒和离线冲突。结果是端侧必须只依赖稳定
HTTP/WebSocket 协议，不能导入 `app.server` 或直接访问 SQLite。

## D002 所有权来自已验证上下文

状态：已采用。

浏览器使用签名 session Cookie，设备使用设备 token，Feishu 使用 bot/identity/chat
binding，OpenClaw 使用 Agent token + 短期 scope。客户端提交的 `userId` 不决定
owner。

原因：仅在前端隐藏用户选择无法阻止横向越权。管理员切换必须同时保存 active user
和实际 actor，以便授权与审计使用不同身份。

## D003 事项使用公共基表与显式关系

状态：已采用。

`evtBase` 保存公共字段，Plan、DDL、Course、Reminder 使用子表。Course occurrence、
DDL Plan 和 Reminder 都使用关系表/外键表达，不在描述文本里隐式推断。

原因：统一查询、状态和用户边界，同时保留不同时间语义。代价是创建/更新时间时必须
维护关系一致性，启动时仍需要 `relation_compat` 和 maintenance 处理旧数据库。

## D004 确定性调度不依赖 LLM

状态：已采用。

提醒扫描、去重、天气刷新和投递路由由 APScheduler 与领域服务执行。OpenClaw 参与
自然语言任务和日报生成，但不参与每分钟提醒判断。

原因：模型延迟、费用或故障不能让提醒系统停止。任何新周期任务先判断能否用普通
代码可靠完成，再决定是否调用模型。

## D005 OpenClaw 只通过受限 Agent API 工作

状态：已采用。

SmartCore 验证并规范化 Feishu 事件，Adapter 运行 OpenClaw skill，OpenClaw 通过
`/agent/*` 读写。最终飞书投递由 Adapter/SmartCore 管理。

拒绝的方案：让开发工具或 OpenClaw 直接读 SQLite/volume。这样无法可靠实施用户
scope、审计、幂等和回滚，也会扩大密钥与生产数据暴露面。

## D006 Feishu bot 与用户聊天绑定分离

状态：已采用。

`feishuBot` 表示应用凭据和 bot runtime，`lifeIdentity` 表示外部身份，`feishuBind`
表示具体用户/bot/chat 授权端点。

原因：一个 bot 可以服务多个用户和聊天，但任何消息/提醒都必须回到已绑定目标，
不能使用全局默认聊天造成跨用户投递。普通用户只绑定默认 bot；管理员才管理凭据。

## D007 媒体使用私有存储、幂等 OCR 与证据

状态：已采用。

附件先进入 owner-scoped 私有存储。图片执行一次有界 OCR，再由媒体模型生成短摘要；
文档只存储。OCR evidence 绑定用户、上传和过期时间。

原因：保留原始附件、限制模型费用、防止 prompt 漂移绕过 OCR，并避免把附件路径或
供应商凭据暴露给浏览器。Idea 元数据与附件差量原子提交，物理删除晚于数据库提交。

## D008 发布使用候选镜像晋升

状态：已采用。

`dev` 在 `/opt/smartcore-dev` 构建和验证带 Git SHA 的候选；
`promote_prod.sh` 快进 `main` 并切换同一组已验证镜像。生产阶段不重新构建。

原因：保证测试提交、main 和生产镜像一致，同时复用构建缓存。提升前备份 SQLite，
健康失败恢复上一镜像；代码回滚不自动倒退数据库。

## D009 按部署目标拆分代码

状态：已采用。

代码分别位于 `app/server`、`app/raspberryPi`、`app/computer`；Vue 工作台仍由 Server
托管，不等同于未来 Computer monitor。

原因：明确依赖和发布边界，避免把 Pi 摄像头依赖或未来桌面依赖装入 Server。

## D010 文档只保存现行领域事实

状态：已采用并修正。

不再为每次功能提交保留一篇永久验收稿。现行规则进入领域文档，长期决策进入本文，
里程碑进入 `delivery-history.md`，细节留在 PR/Git 历史。

原因：旧方案和现行契约混放会误导模型。与此同时，不能只留下高层概述，所以根
`AGENTS.md` 和 `api-contracts.md` 专门保存任务导航、兼容边界与状态机。

## D011 电脑活动先保存客观事实

状态：已采用。

v1 只记录 active/idle/locked/sleeping/paused 与过滤后的应用上下文。Plan 关联只按
时间区间并集求交，不从窗口标题推断任务，也不输出效率、分心、分类或建议。

原因：先建立可核对的数据质量、隐私和离线同步基础。`sessionId`、`contextId`、
`schemaVersion` 及空 inference/classification 保留扩展点；未来 AI 以 annotation
追加结论，不修改原始活动事实。

## 当前兼容与技术债

这些不是可直接删除的“冗余”：

1. `app/server/agent/` 有多个重叠 router。`main.py` 的注册顺序影响实际 handler；
   应先建立 assembled-app 合约测试，再收敛别名。当前 canonical delete 首次命中
   token-only v2 route，尚未具备与 query/create/update 相同的 scope 隔离。
2. `lifeDevice` 与 `device` 两套设备记录分别承载配对/分发和 Pi 状态/照片。合并需要
   数据迁移、token 兼容和端侧升级计划。
3. `relation_compat.py` 与启动维护保护旧数据库关系。移除前必须用生产 schema 副本
   验证迁移幂等。
4. 浏览器 session 当前是签名 Cookie，`userSession` 表没有成为请求鉴权权威。
   若要支持服务端撤销，需要完整切换而非只写表。
5. Pi 照片的部分 Server/Web 路由只依赖内网边界，缺少逐路由 session/owner 校验。
6. `app/server/new_core/event_relations.py`、`crud.py` 和 Agent route 文件职责较重。
   拆分应按事务/领域边界进行，不能机械按文件行数拆。
7. `DASHBOARD_BASE_URL` 是历史命名；配置示例指向现行 `/work`，删除该设置前应检查
   生产环境与飞书卡片调用方。

处理这些债务时，优先增加能证明现状的测试，再做迁移或删除。
