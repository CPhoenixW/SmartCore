# 项目与服务结构

本文档描述 SmartCore v1 推荐的代码目录、服务模块和数据流。

## 推荐目录结构

```text
SmartCore/
  app/
    main.py
    config.py
    db/
      models.py
      session.py
      migrations/
    feishu/
      event_handler.py
      client.py
      security.py
      commands.py
    scheduler/
      runner.py
      reminder_engine.py
      notification_cards.py
    secretary/
      timetable.py
      assignments.py
      life_events.py
      planner.py
      rules.py
    web/
      routes.py
      templates/
      static/
    backup/
      snapshot.py
      restore.py
      sync_to_pi.py
  data/
    smartcore.sqlite
  backups/
  deploy/
    docker-compose.yml
    Caddyfile
    env.example
  scripts/
    import_timetable.py
    backup_now.sh
    restore_backup.sh
  doc/
  tests/
```

实际落地时可以先从更小的结构开始，但职责边界建议保持一致。

## 服务模块说明

### `app/main.py`

FastAPI 应用入口，负责：

- 注册飞书回调路由。
- 注册内部 Web 面板路由。
- 启动应用生命周期。
- 初始化配置和数据库连接。

### `app/config.py`

加载配置。配置来源优先级建议：

1. 环境变量。
2. 本地配置文件，例如 `passwd.txt` 或 `.env`。
3. 默认值。

敏感配置不进入 Git，例如：

- 飞书 app secret。
- 飞书 verification token。
- 飞书 encrypt key。
- SSH key 路径。
- 树莓派真实主机名。

### `app/feishu/`

飞书集成模块。

职责：

- 校验飞书事件请求是否合法。
- 解析飞书事件。
- 把飞书消息转换成内部命令。
- 调用飞书 API 主动发送消息。

边界：

- 不直接写复杂业务逻辑。
- 不直接生成完整日程计划。
- 只负责“飞书协议”和“内部命令”之间的转换。

### `app/secretary/`

个人秘书业务核心。

职责：

- 课表计算。
- 作业和 DDL 管理。
- 生活事项管理。
- 空闲时间计算。
- 日程冲突检测。
- 今日计划和明日计划生成。

这是系统最重要的业务层，应该尽量不依赖飞书，方便以后换成其他入口。

### `app/scheduler/`

调度模块。

职责：

- 每分钟扫描课表、作业、生活事项，计算当前是否需要发送提醒。
- 通过飞书交互卡片推送晨报、课前提醒、DDL 提醒、事项提醒。
- 仅在发送成功后写入 `reminders` 表作为投递审计（dedup_key 去重），不再预生成提醒队列。

### `app/operations/` + `app/llm/`

语义层。

职责：

- 仅使用 DeepSeek LLM 将自然语言解析为 Action 协议 JSON。
- 输出 `create_event` / `query_event` / `update_event` / `delete_event`。
- 不再维护规则解析器或旧版 `operation/resource/fields` 协议。

### `app/web/`

内部 Web 面板。

职责：

- 查看今日/明日计划。
- 导入课表；导入成功会替换当前课表，而不是叠加旧课程时段。
- 管理作业、DDL、生活事项，并提供完成与一键删除操作。
- 查看提醒日志。
- 管理基础设置。

访问限制：

- 只通过 Tailscale 访问。
- 不通过公网域名暴露。

### `app/backup/`

备份与恢复相关逻辑。

职责：

- 生成 SQLite 一致性快照。
- 压缩备份文件。
- 清理过期本地备份。
- 通过 `rsync over SSH` 同步到树莓派。
- 提供手动恢复辅助脚本。

## 数据模型 v1

建议先支持以下核心表：

### `courses`

保存课程基础信息：

- 课程名。
- 教师。
- 默认地点。
- 备注。

### `course_sessions`

保存课表中的具体上课时间：

- 所属课程。
- 星期几。
- 开始节次。
- 结束节次。
- 开始时间。
- 结束时间。
- 周次规则。
- 地点覆盖。

### `assignments`

保存作业和 DDL：

- 标题。
- 所属课程，可为空。
- 截止时间。
- 状态。
- 优先级。
- 备注。

### `life_events`

保存生活事项：

- 标题。
- 指定时间或期限。
- 状态。
- 提醒规则。
- 备注。

### `reminders`

保存通知投递审计，不再作为待发送队列：

- 提醒类型与 dedup_key（去重键）。
- 目标对象与计划发送时间。
- 实际发送时间、发送状态、重试次数。
- 调度器每分钟从 live 数据计算提醒，发送成功后写入本表。

### `message_logs`

保存飞书消息和系统回复摘要：

- 消息来源。
- 原始消息 ID。
- 命令解析结果。
- 回复状态。

## Docker Compose 服务

v1 推荐两个容器：

```text
caddy
app
```

其中：

- `caddy` 对公网开放 `80` 和 `443`。
- `app` 不直接暴露公网端口。
- `app` 的内部端口只被 Caddy 或 Tailnet 访问。
- SQLite、日志和备份目录通过 Docker volume 或宿主机目录挂载。

## 推荐开发顺序

1. 建立 FastAPI 基础服务和 SQLite 连接。
2. 实现课表导入和今日课程计算。
3. 实现内部 Web 面板的基础查看与编辑。
4. 实现飞书主动推送。
5. 实现飞书事件回调和命令解析。
6. 实现提醒调度器。
7. 实现备份快照和同步到树莓派。
8. 增加测试和部署脚本。
