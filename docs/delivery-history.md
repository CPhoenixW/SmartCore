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

关键边界：最新“所有图片均 OCR”契约取代早期“无文字图片跳过 OCR”的方案；
`docs/media.md` 和相关测试是当前依据。

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
