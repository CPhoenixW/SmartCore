# SmartCore Project Handoff

更新日期：2026-06-01

本文档用于把 SmartCore 当前项目背景、已完成工作、部署进展、关键坑点和后续任务完整交接给新的开发者或另一个 AI 工程师。文档中不会记录真实密码、飞书密钥、Verification Token、App Secret 等敏感信息。

## 1. 当前项目目标

SmartCore 的目标是构建一个低 API 使用量的个人学生秘书系统，重点解决学生场景中的日程管理、课表驱动提醒、作业/DDL 管理、消息推送和简单互联网信息抓取，并支持多设备协同。

当前 v1 聚焦为“个人秘书型”产品：

- 以学生课表为日程核心，课表占据日程中约一半内容。
- 支持课程、作业、生活事项、提醒队列和消息日志的本地化管理。
- 使用飞书机器人作为主要交互入口。
- 使用 Web 面板作为内部管理入口。
- 使用公网服务器作为主控节点。
- 使用 Tailscale 将电脑、手机、树莓派、服务器接入同一虚拟局域网。
- 使用树莓派作为 SQLite 快照备份接收节点。
- 低 API 使用量：规则和本地调度优先，LLM 或外部搜索只作为后续增强。

目标设备协同模型：

```text
手机 / 电脑
  |  飞书消息 / Tailscale 内网 Web
  v
公网服务器
  |  主业务、数据库、调度器、机器人、HTTPS 回调
  v
树莓派
  |  只接收数据库快照备份
```

## 2. 已完成工作

### 产品与架构设计

已完成一组架构文档，位置在 `doc/`：

- `doc/01-overall-architecture.md`：总体架构。
- `doc/02-device-roles.md`：各设备职责与部署方式。
- `doc/03-project-structure.md`：项目结构与服务边界。
- `doc/04-network-security.md`：网络边界、安全策略、Tailscale 与公网入口关系。
- `doc/05-backup-restore.md`：数据库快照备份与恢复方案。
- `doc/06-cursor-cli-execution-plan.md`：交给 Cursor CLI 的阶段化执行计划。

核心设计结论：

- 公网服务器是唯一主控节点。
- 飞书作为移动端和日常消息交互入口。
- 公网只保留一个很小的 HTTPS 回调入口 `/feishu/event`。
- Web 面板不直接公网开放，只通过 Tailscale 内网访问。
- 树莓派 v1 不跑业务，只作为备份节点。
- SQLite 作为 v1 数据库，降低部署复杂度。
- 调度提醒由服务器本地规则驱动，避免依赖高频外部 API。

### 代码实现

当前项目已经有 FastAPI 应用骨架和业务模块：

- `app/main.py`：FastAPI 入口。
- `app/config.py`：配置加载。
- `app/db/`：SQLite/SQLAlchemy 数据模型、会话、CRUD。
- `app/secretary/`：课表、作业、生活事项、规划规则。
- `app/scheduler/`：晨报、提醒、调度 runner。
- `app/feishu/`：飞书安全校验、事件处理、命令解析、消息发送 client。
- `app/web/`：内部 Web 面板、模板、静态样式。
- `app/backup/`：快照与同步逻辑。
- `scripts/backup_now.sh`：手动备份脚本。
- `scripts/restore_backup.sh`：恢复脚本。
- `tests/`：健康检查、部署、备份、调度、Web、规划、飞书等测试。

### 部署配置

已完成 Docker 部署文件：

- `deploy/docker-compose.yml`
- `deploy/Dockerfile`
- `deploy/Caddyfile`
- `deploy/env.example`

生产部署目录：

```text
/opt/smartcore
```

生产服务：

- `deploy-app-1`：FastAPI app，容器内监听 `8000`。
- `deploy-caddy-1`：Caddy，监听公网 `80` 和 `443`。
- 服务器上还运行过一个 derper 容器，与 SmartCore 主业务无直接关系。

### 已部署状态

服务器上 Docker Compose 已经可以启动 app 和 Caddy。

本机或服务器内访问 app 健康检查应该成功：

```bash
curl http://127.0.0.1:8000/healthz
curl http://172.17.0.1:8000/healthz
```

预期：

```json
{"status":"ok"}
```

`172.17.0.1:8000` 是 Docker 宿主机网桥地址。Cloudflare Tunnel 的 cloudflared 如果以 Docker 容器运行，容器里的 `127.0.0.1` 指的是 cloudflared 容器自己，不是宿主机，所以应使用 `http://172.17.0.1:8000` 访问宿主机映射出来的 SmartCore app。

### 已做过的部署优化

由于服务器访问 Docker Hub 和 PyPI 很慢，已做以下处理：

- `deploy/Dockerfile` 改为使用清华 PyPI 镜像源，减少 `pip install` 时间。
- Docker 镜像拉取可使用 DaoCloud 镜像前缀临时绕过 Docker Hub 超时。
- Caddyfile 已增加 access log，方便观察公网请求是否真的到达 Caddy。
- Caddy 已关闭 HTTP/3，只保留 HTTP/1.1 和 HTTP/2，减少排障变量。
- 飞书事件处理和飞书 client 已增加日志，方便确认是否收到消息、是否回复失败。

当前存在未提交改动：

```text
M app/feishu/client.py
M app/feishu/event_handler.py
M deploy/Caddyfile
M deploy/Dockerfile
```

这些改动主要是部署排障和日志增强。

## 3. 当前进展

当前正在解决“飞书事件回调公网入口”的最后一段连通性问题。

已经确认：

- 飞书事件订阅页面已经配置请求地址：

```text
https://smartcore.phoenixw.online/feishu/event
```

- 飞书已订阅事件：

```text
im.message.receive_v1
```

- 事件订阅类型为“应用身份”。
- 相关消息读取权限已经开通并发布。
- 飞书 Encrypt Key 当前未启用，事件请求应为明文 JSON。
- 服务器本地模拟 URL verification 可以成功返回 challenge。
- 经 Caddy 转发时，服务器本机模拟也曾成功返回 challenge。

但是飞书控制台曾持续显示：

```text
Post "https://smartcore.phoenixw.online/feishu/event": EOF
httpCode: 0
```

这个错误已基本定位为公网入口被云厂商或网络层阻断，而不是 FastAPI 代码、飞书 App ID、飞书 Token 或 Caddy 反代错误。

关键原因：

- 域名 `phoenixw.online` 在大陆云服务器上直接使用 `80/443` 提供公网服务时，未备案域名会被阻断。
- 外部请求曾出现：
  - HTTP 返回 `403 Forbidden`
  - 响应头中出现 `Server: ADM/2.1.1`
  - 页面标题类似“非法阻断”
  - HTTPS 连接被 reset
  - 飞书侧表现为 EOF/httpCode=0

因此当前改用 Cloudflare Tunnel。

Cloudflare 当前进展：

- 用户已经把 `phoenixw.online` 托管到 Cloudflare。
- 当前 `dig +short smartcore.phoenixw.online` 返回：

```text
104.21.52.249
172.67.206.16
```

这说明 `smartcore.phoenixw.online` 已经不再直接解析到华为云公网 IP，而是走 Cloudflare 代理 IP。

下一步应继续验证 Cloudflare Tunnel 的 Public Hostname 是否正确指向服务器内的 SmartCore 服务。

## 4. 关键设计决策

### 4.1 服务器主控

选择公网服务器作为唯一主控节点，负责：

- FastAPI 应用。
- SQLite 数据库。
- 调度器。
- 飞书机器人事件处理。
- Web 面板。
- 备份任务。
- HTTPS 入口。

原因：

- 服务器在线时间稳定。
- 飞书要求公网可访问 HTTPS 回调。
- 调度提醒必须长期可靠运行。
- 移动设备和个人电脑不适合作为常驻主控。

### 4.2 Tailscale 用于内部网络，不直接用于飞书回调

Tailscale 适合连接自己的设备，但飞书开放平台不在用户的 Tailnet 中，无法直接访问 Tailscale 私网地址。

因此架构分成两层：

- 内部访问：电脑、手机、树莓派通过 Tailscale 访问服务器内部服务。
- 外部回调：飞书通过公网 HTTPS 访问一个小入口。

### 4.3 公网入口最小化

Caddy 原始设计中只允许公网访问：

```text
POST /feishu/event
```

其他路径返回 404。

Web 面板和内部 API 不通过公网开放。

这样可以降低攻击面，即使开放 `80/443`，也只暴露一个很小的 webhook 接口。

### 4.4 使用 Cloudflare Tunnel 绕过未备案域名阻断

因为大陆服务器直接绑定未备案域名的 `80/443` 可能被阻断，改为：

```text
飞书 -> Cloudflare -> Cloudflare Tunnel -> 华为云服务器上的 SmartCore app
```

这样飞书访问的是 Cloudflare 的公网入口，不直接访问华为云公网 `443`。

Public Hostname 选择：

```text
Published application
```

不是：

- `Private hostname`
- `Private CIDR`
- `Workers VPC`

因为当前需求是把本地应用发布为公网 hostname 给飞书访问。

### 4.5 SQLite + 快照备份

v1 使用 SQLite 是合理选择：

- 部署简单。
- 数据量小。
- 个人使用场景并发低。
- 方便做文件级快照。

备份采用快照格式：

```text
smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz
```

并同步到树莓派。

### 4.6 规则优先，LLM 后置

提醒、课程、DDL 等必须可靠，不能依赖 LLM 是否可用。

v1 采用确定性规则：

- 今天计划。
- 明天计划。
- 课前提醒。
- DDL 提醒。
- 每日摘要。

LLM 可以在后续用于自然语言解析、总结、信息抓取，但不作为核心提醒链路依赖。

## 5. 已排除的方案

### 5.1 只用 Tailscale 暴露给飞书

已排除。

原因：飞书服务器不在用户的 Tailscale 网络中，无法访问 Tailscale 私网地址。

### 5.2 让树莓派运行主业务

v1 暂不采用。

原因：

- 树莓派稳定性和公网接入不如云服务器。
- 飞书回调需要公网 HTTPS。
- 树莓派更适合做低成本备份节点。

### 5.3 电脑作为主控节点

已排除。

原因：

- 电脑不保证 24 小时在线。
- 睡眠、换网、代理、系统更新都会影响提醒和回调。

### 5.4 直接用大陆云服务器公网 IP 加域名跑飞书回调

当前已基本排除。

原因：

- 未备案域名在大陆云服务器上绑定 `80/443` 可能被阻断。
- 飞书侧表现为 EOF/httpCode=0。
- 外部 curl 出现 connection reset 或 ADM 阻断页。

### 5.5 完全依赖 Docker Hub/PyPI 默认源

部署时体验很差。

原因：

- Docker Hub 拉取镜像容易 timeout。
- pip 默认源下载依赖很慢。

当前已改为：

- Docker 镜像必要时用 DaoCloud 前缀。
- Python 依赖使用清华 PyPI 镜像。

## 6. 未完成任务

### 部署与公网入口

- 完成 Cloudflare Tunnel 的 Public Hostname 配置。
- 确认 `smartcore.phoenixw.online` 通过 Cloudflare Tunnel 访问到 SmartCore app。
- 用外部网络验证 `POST /feishu/event` 可以正常返回 challenge。
- 在飞书后台重新验证事件请求 URL。
- 给机器人发送消息，确认 app 日志能收到 `im.message.receive_v1`。

### 飞书消息闭环

当前曾出现过“事件进入 app 后，回复飞书失败 400 Bad Request”的迹象。公网入口通后，还需要继续排查：

- `FEISHU_APP_ID` 是否正确。
- `FEISHU_APP_SECRET` 是否正确。
- 机器人是否已启用并发布。
- 是否拥有发送消息所需权限。
- `chat_id` / `open_id` / `receive_id_type` 是否使用正确。
- 飞书 API 返回的具体错误体。

### 安全收尾

用户曾在对话中暴露过服务器密码和飞书 Verification Token。项目调通后应：

- 重置服务器 root 密码。
- 重新生成飞书 Verification Token。
- 检查 `.env` 不被 Git 跟踪。
- 后续改用 SSH key 登录服务器。
- 限制服务器安全组，只保留必要端口。

### Git 收尾

- 当前本地有未提交改动，需要检查 diff。
- 运行测试。
- 提交部署排障相关改动。
- 如果可能，补充一条部署故障排查文档。

### 备份落地

- 确认树莓派 SSH key-based auth。
- 配置 `PI_USER`、`PI_HOST`、`PI_BACKUP_DIR`。
- 手动执行备份。
- 验证树莓派收到 `.sqlite.gz` 快照。
- 后续配置 cron 定时备份。

## 7. 当前待解决问题

### 7.1 Cloudflare Tunnel 是否真正接到 app

当前 DNS 已经返回 Cloudflare IP：

```text
104.21.52.249
172.67.206.16
```

这说明 DNS 已经从直连华为云切到 Cloudflare 代理，但还不能单独证明 Tunnel 后端配置正确。

需要确认 Cloudflare Zero Trust 中 Public Hostname：

```text
Hostname: smartcore.phoenixw.online
Service Type: HTTP
Service URL: http://172.17.0.1:8000
```

如果 cloudflared 不是 Docker 容器运行，而是直接在宿主机运行，那么 Service URL 可以考虑：

```text
http://127.0.0.1:8000
```

但如果 cloudflared 在 Docker 容器内运行，优先使用：

```text
http://172.17.0.1:8000
```

### 7.2 HTTPS handshake failure

用户最近执行：

```bash
curl --noproxy '*' -i -X POST https://smartcore.phoenixw.online/feishu/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"url_verification","token":"<redacted>,"challenge":"cf_test"}'
```

得到：

```text
LibreSSL: sslv3 alert handshake failure
```

注意：该 curl 的 JSON body 也写错了，`token` 字符串少了结束引号。但 handshake failure 发生在发送 HTTP body 之前，所以主要问题仍应先看 Cloudflare SSL/Tunnel/DNS 配置。

应优先检查：

- Cloudflare SSL/TLS 模式是否为 Full，而不是异常配置。
- `smartcore` 记录是否为 Tunnel 创建的 CNAME 或 Cloudflare 代理记录。
- 是否仍残留旧的 `A 1.94.36.113`。
- Tunnel 是否在线。
- Public Hostname 是否绑定到正确 tunnel。
- cloudflared 到 `http://172.17.0.1:8000` 是否通。

### 7.3 飞书事件日志仍可能看不到

如果公网入口还未通，飞书控制台会继续显示 EOF/httpCode=0，app 和 Caddy 日志可能看不到请求。

判断顺序：

1. 外部 curl 是否能到 Cloudflare。
2. Cloudflare Tunnel 是否能到服务器 app。
3. app 是否能返回 challenge。
4. 飞书 URL verification 是否通过。
5. 飞书消息事件是否进入 app 日志。
6. app 是否能成功回复飞书消息。

## 8. 关键文件路径

本地项目路径：

```text
/Users/phoenixw/SmartCore
```

服务器项目路径：

```text
/opt/smartcore
```

远程总结文档备份目录：

```text
/home/phoenix/DiskE/DesktopApp/1
```

核心文档：

```text
/Users/phoenixw/SmartCore/README.md
/Users/phoenixw/SmartCore/PROJECT_CONTEXT.md
/Users/phoenixw/SmartCore/doc/README.md
/Users/phoenixw/SmartCore/doc/01-overall-architecture.md
/Users/phoenixw/SmartCore/doc/02-device-roles.md
/Users/phoenixw/SmartCore/doc/03-project-structure.md
/Users/phoenixw/SmartCore/doc/04-network-security.md
/Users/phoenixw/SmartCore/doc/05-backup-restore.md
/Users/phoenixw/SmartCore/doc/06-cursor-cli-execution-plan.md
```

应用入口：

```text
/Users/phoenixw/SmartCore/app/main.py
/Users/phoenixw/SmartCore/app/config.py
```

飞书模块：

```text
/Users/phoenixw/SmartCore/app/feishu/security.py
/Users/phoenixw/SmartCore/app/feishu/event_handler.py
/Users/phoenixw/SmartCore/app/feishu/client.py
/Users/phoenixw/SmartCore/app/feishu/commands.py
```

个人秘书核心：

```text
/Users/phoenixw/SmartCore/app/secretary/timetable.py
/Users/phoenixw/SmartCore/app/secretary/assignments.py
/Users/phoenixw/SmartCore/app/secretary/life_events.py
/Users/phoenixw/SmartCore/app/secretary/planner.py
/Users/phoenixw/SmartCore/app/secretary/rules.py
```

调度器：

```text
/Users/phoenixw/SmartCore/app/scheduler/runner.py
/Users/phoenixw/SmartCore/app/scheduler/reminder_engine.py
/Users/phoenixw/SmartCore/app/scheduler/daily_digest.py
```

Web 面板：

```text
/Users/phoenixw/SmartCore/app/web/routes.py
/Users/phoenixw/SmartCore/app/web/templates/
/Users/phoenixw/SmartCore/app/web/static/style.css
```

备份：

```text
/Users/phoenixw/SmartCore/app/backup/snapshot.py
/Users/phoenixw/SmartCore/app/backup/sync_to_pi.py
/Users/phoenixw/SmartCore/scripts/backup_now.sh
/Users/phoenixw/SmartCore/scripts/restore_backup.sh
```

部署：

```text
/Users/phoenixw/SmartCore/deploy/docker-compose.yml
/Users/phoenixw/SmartCore/deploy/Dockerfile
/Users/phoenixw/SmartCore/deploy/Caddyfile
/Users/phoenixw/SmartCore/deploy/env.example
```

生产环境私有配置：

```text
/opt/smartcore/deploy/.env
```

注意：`.env` 不应提交，不应写入真实密钥到交接文档。

## 9. 关键命令

### 本地开发

```bash
cd /Users/phoenixw/SmartCore
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

### 查看当前 Git 状态

```bash
cd /Users/phoenixw/SmartCore
git status --short
git diff
```

### 同步代码到服务器

建议同步时排除虚拟环境、缓存、数据库和备份：

```bash
rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude 'data/' \
  --exclude 'backups/' \
  /Users/phoenixw/SmartCore/ \
  root@100.65.243.93:/opt/smartcore/
```

### 服务器 Docker Compose

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml config
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
```

### 只重建 app

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml build --pull=false app
docker compose -f deploy/docker-compose.yml up -d --pull never app
```

### 强制重建 Caddy

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml up -d --force-recreate caddy
```

### 查看日志

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml logs --tail=100 app
docker compose -f deploy/docker-compose.yml logs --tail=100 caddy
```

持续观察：

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml logs -f app caddy
```

### 健康检查

服务器本机：

```bash
curl -i http://127.0.0.1:8000/healthz
curl -i http://172.17.0.1:8000/healthz
```

公网/Tunnel：

```bash
curl --noproxy '*' -i https://smartcore.phoenixw.online/healthz
```

注意：如果 Caddy 仍只允许 `/feishu/event`，公网访问 `/healthz` 可能返回 404。这不是 app 故障。Cloudflare Tunnel 如果直接指到 app，则可能可以访问 `/healthz`。

### 模拟飞书 URL verification

不要把真实 token 写进命令历史或文档。使用时把 `<real-verification-token>` 替换为服务器 `.env` 中真实值：

```bash
curl --noproxy '*' -i -X POST https://smartcore.phoenixw.online/feishu/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"url_verification","token":"<real-verification-token>","challenge":"cf_test"}'
```

预期响应：

```json
{"challenge":"cf_test"}
```

### 检查 DNS

```bash
dig +short smartcore.phoenixw.online
dig +short CNAME smartcore.phoenixw.online
dig +trace phoenixw.online
```

当前期望：

- `smartcore.phoenixw.online` 不再返回华为云公网 IP。
- 应返回 Cloudflare 代理 IP，或 CNAME 指向 Cloudflare Tunnel。
- Cloudflare 托管成功后，权威 NS 应是 Cloudflare 分配的 nameserver。

### Docker Hub 拉取慢的替代方式

```bash
docker pull m.daocloud.io/docker.io/library/python:3.11-slim
docker tag m.daocloud.io/docker.io/library/python:3.11-slim python:3.11-slim

docker pull m.daocloud.io/docker.io/library/caddy:2-alpine
docker tag m.daocloud.io/docker.io/library/caddy:2-alpine caddy:2-alpine
```

### 备份

```bash
cd /opt/smartcore
./scripts/backup_now.sh
```

恢复前必须先停 app：

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml stop app
./scripts/restore_backup.sh /path/to/smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz
docker compose -f deploy/docker-compose.yml start app
```

## 10. 后续建议

### 优先级 P0：打通 Cloudflare Tunnel

下一位接手者应先做最小验证，不要同时改很多东西：

1. 确认 cloudflared tunnel 在线。
2. 确认 Public Hostname 是 `smartcore.phoenixw.online`。
3. 确认 Service URL 指向正确后端。
4. 从服务器本机验证 `http://172.17.0.1:8000/healthz`。
5. 从外部验证 `https://smartcore.phoenixw.online/feishu/event` 的 POST challenge。
6. 飞书后台重新保存并验证 URL。

### 优先级 P1：恢复飞书消息闭环

公网入口通后，再处理机器人收发消息：

- 开一条服务器日志：

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml logs -f app caddy
```

- 在飞书给机器人发“帮助”。
- 看 app 是否打印收到消息。
- 若回复失败，查看飞书 API 400 的响应体。
- 根据响应体修正 `receive_id_type`、权限或 chat/open id 使用方式。

### 优先级 P1：安全轮换

项目调通后立即做：

- 轮换飞书 Verification Token。
- 轮换服务器 root 密码。
- 改用 SSH key 登录。
- 检查 `.env`、数据库、备份文件未进入 Git。
- 最小化服务器安全组。

### 优先级 P2：Git 整理

当前有未提交改动，应：

```bash
cd /Users/phoenixw/SmartCore
git status --short
git diff
pytest
git add app/feishu/client.py app/feishu/event_handler.py deploy/Caddyfile deploy/Dockerfile PROJECT_CONTEXT.md
git commit -m "deploy: document handoff and improve feishu troubleshooting"
```

如果测试失败，先修复再提交。

### 优先级 P2：备份自动化

手动备份验证通过后，在服务器配置 cron：

```text
0 3 * * * cd /opt/smartcore && ./scripts/backup_now.sh
```

同时确认树莓派端可定期收到快照。

### 优先级 P3：产品能力增强

在稳定运行后，再考虑：

- 课程导入更顺滑。
- 飞书自然语言添加作业/事项。
- 每日晨报和睡前明日预告。
- 简单网页抓取，例如天气、考试安排、校园通知。
- LLM 只用于解释、摘要、自然语言解析，不影响核心提醒可靠性。

## 交接提醒

当前最重要的判断是：飞书 EOF 不是飞书 App ID 或 Verification Token 的首要问题，而是公网入口在大陆云服务器未备案域名直连时被阻断。现在 DNS 已切到 Cloudflare，下一步应围绕 Cloudflare Tunnel 后端服务连通性逐步验证。

处理时请一次只改一个变量，保留日志，避免同时修改 DNS、Caddy、Tunnel、飞书配置和 app 代码，否则很难判断是哪一层产生变化。
