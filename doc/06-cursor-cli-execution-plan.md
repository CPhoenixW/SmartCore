# Cursor CLI 执行计划

本文档用于交给 Cursor CLI 或其他编码智能体执行 SmartCore v1。执行者必须严格遵守本文档中的阶段、测试和 Git 规则。

## 执行总目标

实现一个学生个人秘书 v1：

- Python FastAPI 核心服务。
- SQLite 保存课表、作业、生活事项、提醒队列和消息日志。
- Caddy 只暴露飞书 HTTPS 回调入口。
- Tailscale 内部访问 Web 面板和内部 API。
- 调度器负责晨报、课前提醒、DDL 提醒和明日预告。
- 每日 SQLite 快照备份，并通过 `rsync over SSH` 同步到树莓派。

执行时优先参考：

- `doc/01-overall-architecture.md`
- `doc/02-device-roles.md`
- `doc/03-project-structure.md`
- `doc/04-network-security.md`
- `doc/05-backup-restore.md`

## 强制执行规则

### Git 规则

当前目录如果还不是 Git 仓库，第一步必须执行：

```bash
git init
```

然后立即创建 `.gitignore`，确保以下内容不会进入 Git：

```text
passwd.txt
.env
*.sqlite
*.sqlite-*
*.db
data/
backups/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.venv/
node_modules/
dist/
build/
```

每完成一个阶段，必须：

```bash
git status
pytest
git add <本阶段相关文件>
git commit -m "<清晰的阶段提交信息>"
```

如果测试失败，不允许提交。必须先修复。

推荐提交粒度：

1. `docs: add architecture and execution plan`
2. `chore: initialize project scaffold`
3. `feat: add timetable and planning core`
4. `feat: add reminders and scheduler`
5. `feat: add feishu integration`
6. `feat: add internal web panel`
7. `feat: add backup and restore scripts`
8. `test: cover secretary workflows`
9. `deploy: add compose and caddy config`

### 安全规则

禁止读取、打印、提交或修改真实密钥文件，尤其是：

```text
passwd.txt
.env
SSH private key
飞书 app secret
飞书 verification token
飞书 encrypt key
```

如果需要配置，只能创建示例文件：

```text
deploy/env.example
```

示例文件中只能使用占位值。

### 架构规则

必须保持以下边界：

- 飞书模块只处理飞书协议、签名校验、消息解析和消息发送。
- 个人秘书核心逻辑不得依赖飞书。
- Web 面板不得通过公网 Caddy 暴露。
- SQLite 数据库不得进入 Git。
- 备份文件不得进入 Git。
- 树莓派只作为备份节点，不运行核心业务。

## 推荐 Cursor CLI 使用方式

在项目根目录执行 Cursor CLI 前，先把本文档作为主要指令上下文。

示例：

```bash
cursor-agent --model auto --prompt-file doc/06-cursor-cli-execution-plan.md
```

如果你的 Cursor CLI 命令名称不同，使用等价方式即可。关键是要求它：

- 先读 `doc/` 下所有架构文档。
- 按阶段实现。
- 每阶段运行测试。
- 每阶段提交 Git。
- 不读取或提交密钥。

如果 Cursor CLI 支持交互式任务，建议第一条指令使用：

```text
你是 SmartCore 项目的执行工程师。请先阅读 doc/ 下的架构文档和 doc/06-cursor-cli-execution-plan.md，然后按阶段实现。每个阶段完成后运行测试并提交 Git。不要读取、打印、修改或提交 passwd.txt、.env、数据库和备份文件。
```

## 阶段 0：仓库初始化

### 目标

把当前目录整理成可维护的 Git 项目。

### 任务

- 如果没有 `.git`，执行 `git init`。
- 创建 `.gitignore`。
- 创建基础目录：

```text
app/
tests/
deploy/
scripts/
data/
backups/
```

- 创建 `README.md`，说明项目目标和本地开发方式。
- 确保 `data/` 和 `backups/` 仅通过 `.gitkeep` 或文档说明保留目录意图，不提交真实数据。

### 测试

```bash
git status
```

确认 `passwd.txt` 没有被跟踪。

### 提交

```bash
git add .gitignore README.md doc app tests deploy scripts
git commit -m "chore: initialize project scaffold"
```

## 阶段 1：Python 项目骨架

### 目标

建立 FastAPI + SQLite + pytest 的最小可运行项目。

### 任务

- 创建 `pyproject.toml`。
- 使用 Python 3.11 或更高版本。
- 添加依赖：
  - `fastapi`
  - `uvicorn`
  - `sqlalchemy`
  - `pydantic`
  - `pydantic-settings`
  - `apscheduler`
  - `httpx`
  - `python-multipart`
  - `jinja2`
  - `pytest`
  - `pytest-asyncio`
  - `ruff`
- 创建 `app/main.py`。
- 创建 `/healthz`。
- 创建配置加载模块 `app/config.py`。
- 创建数据库连接模块 `app/db/session.py`。

### 验收标准

```bash
pytest
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问：

```text
GET /healthz
```

返回：

```json
{"status":"ok"}
```

### 提交

```bash
git commit -m "chore: add fastapi project skeleton"
```

## 阶段 2：数据模型与数据库

### 目标

实现 SmartCore v1 的核心数据模型。

### 任务

实现以下表：

- `courses`
- `course_sessions`
- `assignments`
- `life_events`
- `reminders`
- `message_logs`

推荐使用 SQLAlchemy ORM。

必须提供：

- 数据库初始化函数。
- 测试数据库 fixture。
- 基础 CRUD 服务。

### 验收标准

测试覆盖：

- 可以创建课程。
- 可以创建课程 session。
- 可以创建作业和生活事项。
- 可以创建提醒。
- 测试数据库不会写入真实 `data/smartcore.sqlite`。

### 提交

```bash
git commit -m "feat: add core database models"
```

## 阶段 3：课表与计划核心

### 目标

实现不依赖飞书的个人秘书核心逻辑。

### 任务

创建 `app/secretary/`：

- `timetable.py`
- `assignments.py`
- `life_events.py`
- `planner.py`
- `rules.py`

必须支持：

- 周循环课表。
- 单双周。
- 指定周范围。
- 按日期生成当天课程实例。
- 合并当天课程、作业、生活事项。
- 生成今日计划和明日计划。

### 验收标准

测试覆盖：

- 普通周循环课程。
- 单周课程。
- 双周课程。
- 不同地点课程。
- 当天 DDL 出现在今日计划中。
- 明天课程出现在明日计划中。
- 未指定时间的生活事项进入待安排列表。

### 提交

```bash
git commit -m "feat: add timetable and planning core"
```

## 阶段 4：提醒调度

### 目标

实现可恢复、幂等的提醒生成与发送流程。

### 任务

创建 `app/scheduler/`：

- `runner.py`
- `reminder_engine.py`
- `daily_digest.py`

必须支持：

- 每日晨报提醒。
- 明日预告。
- 课前提醒。
- DDL 前一天提醒。
- DDL 当天提醒。
- 提醒状态：`pending`、`sent`、`failed`、`cancelled`。
- 失败重试次数。
- 防止重复发送。

发送接口先抽象为 `NotificationSender`，不要在核心调度里直接依赖飞书。

### 验收标准

测试覆盖：

- 同一天重复生成提醒不会重复创建。
- 已发送提醒不会再次发送。
- 发送失败会增加重试次数。
- 服务重启后，pending 提醒仍可继续发送。

### 提交

```bash
git commit -m "feat: add reminder scheduler"
```

## 阶段 5：飞书集成

### 目标

实现飞书机器人主动推送和事件回调。

### 任务

创建 `app/feishu/`：

- `client.py`
- `security.py`
- `event_handler.py`
- `commands.py`

必须实现：

- 飞书 API client。
- 主动发送文本消息。
- `/feishu/event` 路由。
- verification token 校验。
- 签名或 encrypt key 校验，按飞书事件订阅配置选择实现。
- timestamp 防重放。
- 命令解析：
  - `今日`
  - `明日`
  - `本周DDL`
  - `添加作业 ...`
  - `添加事项 ...`
  - `完成 ...`
  - `帮助`

### 验收标准

测试覆盖：

- 非法 token 被拒绝。
- 非法签名被拒绝。
- 合法事件被转换为内部命令。
- 未识别命令返回帮助提示。
- 飞书 client 可以被 mock，不访问真实飞书 API。

### 提交

```bash
git commit -m "feat: add feishu bot integration"
```

## 阶段 6：内部 Web 面板

### 目标

提供只通过 Tailscale 访问的管理界面。

### 任务

创建 `app/web/`：

- 今日计划页面。
- 明日计划页面。
- 课表导入页面。
- 作业/DDL 管理页面。
- 生活事项管理页面。
- 提醒日志页面。

Web 面板可以先使用 Jinja2 服务端渲染，避免引入前端复杂度。

### 安全要求

- Caddy 公网配置不得转发 Web 面板路径。
- 面板可以先不做复杂登录，但只能通过 Tailscale 访问。
- 后续再补内部登录或 Tailscale identity。

### 验收标准

测试覆盖：

- 面板路由可访问。
- 可以创建作业。
- 可以创建生活事项。
- 可以查看今日计划。

### 提交

```bash
git commit -m "feat: add internal web panel"
```

## 阶段 7：备份与恢复

### 目标

实现 SQLite 快照、本地保留和同步到树莓派。

### 任务

创建：

- `app/backup/snapshot.py`
- `app/backup/sync_to_pi.py`
- `scripts/backup_now.sh`
- `scripts/restore_backup.sh`

必须支持：

- 使用 SQLite `.backup` 能力生成一致性快照。
- 压缩为 `smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz`。
- 本地保留 30 天。
- 通过 `rsync over SSH` 同步到树莓派。
- 树莓派保留 90 天。
- 手动恢复指定快照。

### 配置

从本地配置读取：

```text
PI_USER
PI_HOST
PI_BACKUP_DIR
```

不得硬编码真实树莓派地址。

### 验收标准

测试覆盖：

- 快照文件名格式正确。
- 本地过期快照会被清理。
- rsync 命令可以 dry-run 或 mock。
- 恢复脚本不会在未指定备份文件时执行。

### 提交

```bash
git commit -m "feat: add sqlite backup and restore"
```

## 阶段 8：部署配置

### 目标

提供服务器可部署配置。

### 任务

创建：

- `deploy/docker-compose.yml`
- `deploy/Caddyfile`
- `deploy/env.example`

Docker Compose 至少包含：

- `app`
- `caddy`

Caddy 只转发：

```text
/feishu/event
```

不得转发：

```text
/dashboard
/admin
/api
/docs
/backup
```

### 验收标准

检查：

```bash
docker compose -f deploy/docker-compose.yml config
```

如果当前环境没有 Docker，记录无法运行的原因，但仍需保证配置文件语法清晰。

### 提交

```bash
git commit -m "deploy: add docker compose and caddy config"
```

## 阶段 9：质量收尾

### 目标

让项目达到可维护的 v1 工程状态。

### 任务

- 补充 README 部署说明。
- 补充 `.env` 配置说明。
- 补充飞书机器人配置说明。
- 补充备份恢复说明。
- 运行完整测试。
- 运行 lint。

### 验收标准

```bash
pytest
ruff check .
git status
```

工作区应干净。

### 提交

```bash
git commit -m "docs: add setup and operations guide"
```

## 最终交付检查清单

执行完成后必须确认：

- Git 仓库已初始化。
- `passwd.txt` 未被跟踪。
- `.env` 未被跟踪。
- SQLite 数据库未被跟踪。
- 备份文件未被跟踪。
- 所有测试通过。
- Caddy 只暴露 `/feishu/event`。
- Web 面板只通过 Tailscale 访问。
- 飞书回调做了 token 和签名校验。
- 提醒发送具备幂等保护。
- 备份快照可以生成。
- rsync 同步可以配置到树莓派。
- 恢复脚本必须显式指定快照文件才会执行。

