# 领域模型

数据库使用 SQLite 与 SQLAlchemy。表名保留现有 compact camelCase；创建和兼容迁移
在应用启动时执行。这里记录关系和不变量，字段细节以
`app/server/new_core/models.py` 与 `app/server/db/sql/` 为准。

## 用户与会话

`appUser` 保存稳定 `userId`、唯一登录名、密码哈希、展示信息、角色和状态。当前
浏览器认证由 HMAC 签名 Cookie 保存 active user、actor 和过期时间；`userSession`
模型存在，但尚未成为请求认证的事实源。

- 密码只存哈希；登录必须解析到数据库内部 `userId` 后再签发 Cookie。
- 普通用户只能以自己作为 active user。
- 管理员切换 active user 只改变业务视角，Cookie 与写操作仍保留 actor 审计。
- 浏览器请求不能用 body/query 中的 `userId` 改变资源归属。

## 事项与关系

```text
appUser
  `- evtBase
      |- planEvt
      |   |- remindEvt (plan_start_10m / plan_end_10m)
      |   |- ddlPlan ---- ddlEvt
      |   `- coursePlan - courseEvt
      |- ddlEvt
      |- courseEvt
      `- remindEvt
```

`evtBase` 是公共记录，现行类型为 `plan`、`ddl`、`course` 和 `remind`。子表通过
`evtId` 继承用户所有权，不重复接受客户端指定的 owner。

关键规则：

- Plan 是有开始时间和持续时长的可执行时间块。
- DDL 可以关联多个 Plan 和多个一次性 Reminder；关联两端必须属于同一用户。
- 每个 Plan 自动维护开始前 10 分钟和结束前 10 分钟两个 Reminder。
- Reminder 是推送记录，不出现在普通日程列表；开始提醒不提供完成/延时操作。
- Course 是学期模板，根据学期起始日、周次、星期和单双周展开为 Plan；
  `coursePlan` 保留 occurrence 日期和序号。
- 修改 Plan 时间会同步提醒；显式同步 Course 才会重排它生成的课次。
- 状态至少包含 `todo`、`done`、`cancelled`；Overview 的快速切换只在 todo/done
  之间操作。

Web 主接口位于 `/api/evt`、`/api/planEvt`、`/api/ddlEvt`、`/api/courseEvt` 和
`/api/remindEvt`。日期、星期、时钟和学期周次搜索由 Server 解释。

## Idea 与附件

`idea` 保存标题、Markdown 描述、处理状态和 revision；`ideaAttachment` 是正式附件；
`ideaUpload` 是临时上传；`ideaMediaJob` 保存图片分析状态、摘要和幂等结果。旧 OCR 字段
只用于已有数据兼容，新流程不写入 evidence。

- 所有记录都以用户为边界。
- 编辑使用 `expectedRevision` 防止覆盖并发修改。
- 附件增删和 Idea 元数据在一个数据库事务中完成。
- 文件删除在数据库提交后执行；临时上传和任务会过期清理。

完整媒体流程见 [Idea 与媒体](./media.md)。

## 设备

通用配对与命令分发使用 `lifeDevice`、`deviceKey`、`devicePair`、
`deviceDispatch` 和 `deviceReceipt`。Pi 的状态与按需照片沿用 `device`、
`deviceStateLog` 和 `devicePhotoRequest` 运行记录。

- 一个设备只属于一个用户；撤销后 token 立即失效。
- token 只在激活时返回一次，数据库只保存哈希。
- 配对码短期有效，需要客户端认领、用户确认和客户端激活。
- 分发只能被目标设备拉取，receipt 只能确认自己的 dispatch。
- 状态和照片写入必须由与 `deviceId` 匹配的设备凭证完成。

协议见 [设备与 Pi](./devices.md)。

电脑活动使用八张追加表：`computerActivityContext` 按用户去重应用及过滤后的上下文，
可保存窗口标题、浏览器域名、工作区和文档名；敏感场景只保存应用身份；
`computerActivityBucket` 以 `(deviceId, bucketStart)` 幂等；`computerActivitySlice` 保存
状态秒数；`computerMonitorStatus` 保存最后心跳；`computerDailyUsage` 与
`computerDailyAppUsage` 保存永久日汇总；`computerHourlyAnalysis` 保存按小时的 AI 注释，
`computerDailyWorkLog` 保存永久日聚合日志。两张分析表只追加、不覆盖活动事实，唯一键分别是
`(userId, deviceId, hourStart)` 与 `(userId, deviceId, logDate)`。所有 owner 都从设备 token
或 Agent scope 派生。

明细和无引用上下文保留 90 天，日汇总保留。稳定的 `sessionId`、`contextId`
和 `schemaVersion` 属于采集事实；未来推断只能增加 annotation，不能覆盖原始记录。

## 飞书

`feishuBot` 保存管理员配置的机器人及加密凭据；`lifeIdentity` 映射外部身份；
`feishuBind` 把用户、机器人、身份和聊天组成授权端点；`feishuChatPair` 保存短期配对。

- 入站事件先匹配并验证机器人，再解析身份和聊天绑定。
- 同一身份可以绑定同一用户的多个聊天；一个 binding 可标记为 primary。
- 主动提醒只使用用户的有效 primary binding，不回退到其他用户的默认聊天。
- 普通用户只能绑定系统默认机器人，不能读取或修改机器人密钥。
- 管理员可以创建、测试、启停和删除机器人；明文凭据只在写入时出现。

## 日志、日报与天气

- `actLog`：业务写操作和管理员上下文行为。
- `notifyLog`：提醒路由、投递状态和去重键。
- `msgLog`：飞书等消息的方向、外部 ID、意图与处理状态。
- `dailySummary`：每个用户每天最多一条日报，记录 queued/failed/completed。
- `weatherForecast`：共享的规范化天气缓存，不包含用户数据。

日报读取、日志读取和事件完成操作始终按用户隔离。天气读取需要登录，但缓存本身可
跨用户共享。

## 工作台行为

`/work` 是 Vue 工作台，主要视图包括总览、事项、课程、Idea、设备、日报、日志和
设置。设备页按 Computer、RaspberryPi、Screen、Feishu Bot 分隔管理。Computer 统计先展示
客观状态、Plan 时间交集、会话和应用，再展示小时总结、Plan 执行判断、主题、提醒和每日工作日志。
Server 根据当前 Plan、电脑状态和同用户的新鲜 Pi 状态生成可解释的客观判断；AI 只追加注释，
不修改 Plan 或原始活动。
总览提供日期切换、事项状态切换、天气和设备状态；事项编辑使用完整详情，
不能用列表摘要覆盖 DDL 的计划/提醒关系。写操作必须显示成功或错误状态，API 失败
不能让整个页面白屏。

`/screen` 是横向手机副屏，通过 WebSocket 接收状态和提醒。提醒支持完成、延时和
过期展示；Server 决定更新及再次投递，不由副屏保存状态。
