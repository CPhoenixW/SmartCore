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

Plan 结束结果询问同样由 Server 确定性投递。只有 primary Feishu binding 对原卡片的
按钮或直接回复可修改该 Plan；普通消息不会被猜测为执行结果。

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

## D007 媒体使用私有存储与原生多模态理解

状态：已采用。

附件先进入 owner-scoped 私有存储。图片经 Adapter 校验并临时复制到隔离工作区，由
SmartCore Agent 的多模态模型直接理解；文档只存储。任务结束即删除临时图片。

原因：单一多模态模型能同时处理视觉内容与用户意图，减少一次供应商调用和 OCR 提示
链路，同时不向模型暴露原始存储路径、凭据或跨用户附件。Idea 元数据与附件差量仍
原子提交，物理删除晚于数据库提交。Agent 只加载 SmartCore skill 和 helper 所需的
`exec` 工具；旧 OCR 路由和字段暂留一版用于滚动兼容。

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

v1 记录 active/idle/locked/sleeping、应用 Bundle ID/名称和过滤后的聚焦窗口标题。
Mac 端是用户会话中的无界面 LaunchAgent；辅助功能权限仅用于读取聚焦窗口的标题与
文档引用。用户可选开启浏览器域名、IDE 工作区和文档名，完整 URL、路径及正文不进入
队列。密码管理器、银行、支付和系统认证场景在客户端与 Server 双重降级为仅应用名。
Plan 关联只按时间区间并集求交，不从上下文推断任务，也不输出效率、分心、分类或建议。

设备 token 使用应用支持目录内的 `0600` 文件。原因是无 Developer ID 的 ad-hoc
可执行文件每次构建都会改变 Keychain 代码要求，后台升级会阻塞等待授权；token 本身
只具备 computer 设备范围，Server 仍只保存哈希。旧 Keychain token 仅一次性迁移。

原因：先建立可核对的数据质量、隐私和离线同步基础。`sessionId`、`contextId`、
`schemaVersion` 及空 inference/classification 保留扩展点；未来 AI 以 annotation
追加结论，不修改原始活动事实。Server 可以用当前 Plan、电脑状态和同用户新鲜 Pi
状态生成带 reason codes 与算法版本的确定性 analysis；该派生视图可重算且不写回事实。

## D012 Computer 分析是追加注释层

状态：已采用。

分钟桶和小时客观快照保持不可变，用户可见分析以跨小时 `computerWorkBlock` 为主。
Server 每 5 分钟确定性识别开始、20 分钟 idle、锁屏/休眠/暂停、跨日和候选主题切换；
Server 只在开始、切换、结束或 Plan 语义变化时调用一次正式版
`deepseek-v4-flash-0731` 结构化分析。展示字段由 Server 本地限长清洗；Schema 或控制字段
校验失败时不重复请求相同输入。
模型或校验失败时记录失败，不默认转为多轮 OpenClaw 任务；兼容回退必须显式配置。
Plan 活跃覆盖率和最终状态由 Server 计算，AI 只返回语义匹配。任务运行单独保存租约、稳定
trigger key 和退避重试，`NO_REPLY` 不能永久留下 queued 记录。每日工作日志默认只在 23:59
生成一次；日间预览必须显式配置。旧小时 AI 注释只读保留，不回填历史工作块。

提醒仍由 Server 根据 10 分钟未活跃和低于 30% 重叠规则产生，按用户现有
Screen/Feishu 路由并写入 `notifyLog`；AI 不直接发送小时消息或修改 Plan。

## D013 每日简报使用最小证据聚合

状态：已采用。

Codex 每个任务只提交项目、结果状态、摘要和 commit/PR/测试证据，不上传完整对话、代码或
推理。Server 再以保守唯一匹配把 Computer 工作块和 Plan 归入项目，歧义证据进入“其他工作”。
日报只读取该 owner-scoped 聚合；事实冲突依次采用 Plan 人工结果、Codex 报告和工作块推断，
项目投入时长只来自 Computer active seconds，不累加 Codex 任务墙钟时间。

无人值守日报的分析 scope 只允许读取聚合和保存日报，独立投递 scope 不进入模型上下文；
设备报告使用原子 upsert 和每日配额，所有聚合文本均按不可信事实处理。无任何 Codex、
Computer 工作块或 Plan 证据的日期不调度日报；固定标题由 Adapter 根据任务日期本地生成，
模型标题的可恢复格式差异不触发第二次调用，只有无有效中文正文或叙述泄漏才隔离重试一次。

原因：显式结果能补足仅靠窗口标题无法确认的产出，同时把隐私、错误归因和重复计时控制在
可审计边界内。23:50 的 Codex 汇报先于 23:59 日报，日报不依赖同一分钟的 Computer 日终任务。

## 当前兼容与技术债

这些不是可直接删除的“冗余”：

1. `app/server/agent/` 有多个重叠 router。`main.py` 的注册顺序影响实际 handler；
   应先建立 assembled-app 合约测试，再收敛别名。
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
