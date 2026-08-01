# 交付历史摘要

本文只保留影响后续维护的里程碑与验收边界。完整提交和讨论使用 Git 历史；当前
行为以现行领域文档、代码和测试为准。

## 2026-05 至 2026-06：原型与统一操作链路

- 建立 FastAPI、SQLite、飞书回调、提醒和早期 Dashboard。
- 将自然语言操作收敛为查询、创建、更新、删除和结构化结果。
- 引入候选引用与二阶段语义选择，降低模型直接猜测数据库 ID 的风险。
- 建立 OpenClaw bridge 与 Agent API，飞书事件由 SmartCore 验证后转发。

维护意义：仓库仍保留 `evtQuery`、`evtCreate`、`sendText` 等早期命名作为兼容别名，
但新调用使用 `/agent/db/*` 与 `/agent/feedback/*`。

## 2026-07-03 至 07-05：Server 核心、工作台与副屏

- 用 `app/server/new_core`、新 SQL schema 和 `/api` 替换旧学生秘书式模块。
- `/work` 成为 Vue 工作台；事项看板以扫描和详情编辑为主。
- `/screen` 成为横向手机副屏，通过 WebSocket 接收状态与提醒。
- 提醒形成完成、延时、过期与飞书卡片闭环。

关键边界：Server 是唯一写入方；副屏不保存主数据；明确请求直接执行，不恢复旧的
机械确认流程。

## 2026-07-07 至 07-09：Pi 与事项关系

- 定义 Pi 心跳、状态、照片请求和设备本地数据边界。
- Course 按学期、周次、星期和单双周展开为 Plan occurrence。
- 每个 Plan 自动拥有开始/结束前 10 分钟 Reminder。
- DDL、Plan、Reminder 与 Course 关系成为统一 Web/Agent 契约。

关键边界：Reminder 是 push-only；关系两端必须属于同一用户；端侧不得访问数据库。

## 2026-07-12 至 07-17：认证、用户设备和 Feishu 多用户

- 增加登录、密码哈希、管理员 active-user 切换和用户隔离。
- 增加用户设备配对、一次性 token、dispatch 与 receipt。
- 增加管理员 Feishu bot 密文配置、测试和配对。
- Feishu 身份扩展为 bot/identity/chat binding，并为 Agent 请求签发用户 scope。
- 普通用户可以绑定系统默认 bot，不读取机器人凭据。

关键边界：owner 只能来自 session/token/binding/scope；主动提醒不回退到其他用户
聊天；管理员操作保留 actor 审计。

## 2026-07-18：部署与 OpenClaw 契约收敛

- 生产发布改为 Server 构建候选镜像、记录 SHA、人工确认后晋升同一镜像。
- Adapter、边界代理和应用集成到 Compose 运行模型。
- OpenClaw 查询、回复和工具 helper 变为确定性契约。
- 飞书最终回复使用 Markdown 卡片，Overview/DDL 编辑和状态切换得到修复。

关键边界：`main` 只快进到已验证 `dev` 提交；发布前备份；模型输出必须经过 Adapter
提取/验证，不能发送分析或工具痕迹。

## 2026-07-19 至 07-20：日报、用量和天气

- 每用户每日一条日报，OpenClaw 生成后先持久化再投递。
- 事项完成可以追加完成总结并保持幂等。
- 设备用量改为最近 12 小时滚动曲线。
- Open-Meteo 天气由 Server 定时缓存和投递；供应商失败保留旧缓存。

关键边界：日报按用户/日期唯一且严格验证格式；天气是确定性集成，不消耗
OpenClaw 周期请求。

## 2026-07-22 至 07-23：Idea 富媒体

- Idea 改为标题、Markdown 描述和多附件；文件进入私有 owner-scoped 存储。
- 飞书文本、图片和文件统一转发为媒体任务。
- 图片必须经过一次 DeepSeek OCR 2，随后由媒体模型生成不超过 100 字的事实摘要。
- 增加 media job、OCR evidence、revision 与原子附件编辑。
- 文档只存储；图片可鉴权预览和下载；重复调用不能产生第二次付费 OCR。

当时边界：“所有图片均 OCR”取代早期“无文字图片跳过 OCR”的方案；该链路后来由
2026-07-25 的原生多模态流程取代。

## 2026-07-24：多端布局与文档收敛

- 按部署目标拆分 `app/server`、`app/raspberryPi`、`app/computer`。
- Server 入口统一为 `app.server.main:app`，Docker、测试和脚本同步。
- Pi 源码纳入仓库，但 token、人脸样本、抓拍、日志和模型仍只在设备本地。
- 文档从逐功能验收稿收敛为领域文档，并增加 Agent 导航、API 契约、决策和本摘要。

后续交付只在这里增加高层里程碑；单个修复、字段或 UI 微调由 `CHANGELOG.md`、PR
和测试保存。

## 2026-07-24：macOS 客观使用统计 v1

- 增加 Swift/AppKit 菜单栏监视器、Keychain 凭证和本地 SQLite 离线队列。
- Server 增加 owner-scoped 分钟桶、心跳、90 天明细清理与永久日汇总。
- 工作台增加 Pi/电脑标签、当前状态、Plan 时间交集、三轨时间线、会话和趋势。

关键边界：v1 不做效率或任务推断；敏感应用标题屏蔽；未来 AI 只能追加 annotation。

## 2026-07-25：macOS 后台监视器

- 菜单栏开发版收敛为登录自启的无界面 LaunchAgent，并修复任意输入空闲时间判断。
- 端侧只上传客观状态与应用，Server 不再保存或返回窗口标题。
- Server 结合当前 Plan、电脑状态和新鲜 Pi 状态生成带证据的确定性当前判断。

关键边界：原始分钟桶与日汇总保持兼容；分析可重算且不能覆盖采集事实。

## 2026-07-25：OpenClaw 原生多模态媒体流程

- SmartCore Agent 切换到 `tokendance/qwen3.7-plus`，图片直接作为模型视觉输入。
- Adapter 对图片路径、类型和大小做服务端校验，隔离暂存并在任务结束后清理。
- Agent 工具移除 OCR/evidence 要求，Skill 只保留 scoped helper 与附件安全边界。

关键边界：文档仍只存储；旧 OCR 路由、字段和状态仅用于滚动兼容，不删除历史数据。

## 2026-07-27：Computer 工作智能分析

- Computer 设备页调整为默认入口，增加小时总结、Plan 执行判断、主题聚类、智能提醒和每日工作日志。
- Server 新增小时/每日追加分析表、owner-scoped insights 与 Agent context/write 接口；迁移只新增表和索引。
- Scheduler 每小时第 5 分钟和每日 23:59 通过 OpenClaw `qwen3.7-plus` 生成分析；原始 Computer 上传与普通日报保持兼容。

关键边界：AI 只读取脱敏聚合事实，不访问数据库、OCR 或聊天正文；结果不能覆盖活动事实或修改 Plan，生产启用由 `COMPUTER_ANALYSIS_ENABLED` 控制。

## 2026-07-29：Computer 连续工作块分析

- 小时分析改为客观快照，前端以跨小时连续工作块为主，小时记录进入证据抽屉。
- 新增工作块和分析运行账本，支持 5 分钟边界评估、稳定幂等键、租约回收和退避重试。
- Plan 覆盖率改为 Server 按已过计划时间计算，OpenClaw 只判断脱敏上下文的语义匹配。
- 每日工作日志随工作块变化生成预览，并在 23:59 定稿；旧小时注释保留且不做历史回填。

关键边界：生产由 `COMPUTER_WORK_BLOCK_ANALYSIS_ENABLED` 独立启用；回滚代码不删除新增表。

## 2026-07-30：Codex 项目汇报与每日简报

- macOS 监视器增加 `codex-report`，用 Computer token 幂等上传当天各 Codex 项目的结果摘要。
- Server 将 Codex 报告、Computer 工作块和 Plan 人工结果保守聚合为项目投入，Computer 页优先展示项目。
- Plan 结束后通过绑定的 primary Feishu 卡片回收结果；按钮可完成 Plan，卡片回复只追加 description。
- 日报改为 23:59 按项目生成，23:50 Codex 汇报先提供素材；空段落不再生搬固定格式。

关键边界：不上传 Codex 对话、代码或推理；归属歧义进入“其他工作”；投入时长只使用
Computer active seconds；结果卡片必须匹配原 owner、bot、chat 和消息。

## 2026-07-31：Computer 后台分析降耗

- 工作块和每日工作日志改为 Server 直连 `deepseek-v4-flash` 的单次结构化分析，最多修复一次。
- OpenClaw `qwen3.7-plus` 保留为模型不可用或结构化校验失败时的回退，不再是正常路径。
- 每日预览随工作块变化更新，但默认每 60 分钟最多生成一次；23:59 定稿不受节流影响。
- 小时任务继续只保存客观快照，不再生成新的小时 AI 注释。

关键边界：工作块边界、Plan 覆盖率、owner scope 和持久化仍由 Server 控制；无数据库迁移，
回滚代码不会修改或删除已有日志。

## 2026-08-01：Computer OpenClaw 调用收口

- 关闭日间 Computer 日志预览，日志默认只在 23:59 生成一次。
- Computer 结构化分析默认只请求一次 `deepseek-v4-flash`，失败不再自动转入多轮 OpenClaw。
- OpenClaw 继续处理飞书自然语言、图片和每日简报；Computer Agent 工具仅作显式兼容回退。

关键边界：不修改活动事实、工作块、已有日志或数据库结构；部署配置可显式恢复兼容行为。

## 2026-08-01：Computer 注意力提醒与滚动总结

- Work Block 在累计 active 二十分钟后更新同一标题与总结，此后每新增六十分钟 active 滚动更新。
- 当前 Plan 连续 idle 五分钟触发中性提醒；无 Plan 时需 open Block 先累计 active 二十分钟。
- 提醒使用 Computer `stateSince` 和稳定 dedup key，不调用模型；锁屏、休眠、暂停与离线跳过。

关键边界：idle 五分钟只提醒，idle 二十分钟才关闭工作块；不新增报告、Project 实体或数据库表。
