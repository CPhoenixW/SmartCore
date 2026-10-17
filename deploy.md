# SmartCore 发布

## 环境

| 用途 | 位置 | 分支 |
|---|---|---|
| 候选构建 | `server:/opt/smartcore-dev` | `dev` |
| 生产 | `server:/opt/smartcore` | `main` |

生产配置、数据库和备份只保留在服务器，不进入 Git。

## 发布流程

1. 本地验证并推送 `dev`；GitHub Actions CI 自动运行 pytest、ruff 和前端测试。
2. 确认 CI 通过后，服务器构建候选镜像，运行后端、前端、容器和隔离健康检查。
3. 提升脚本将已验证提交快进到 `main`，备份 SQLite，并切换 App 与 Adapter 镜像。

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app/server tests
cd frontend && npm test && npm run build
git push origin dev
# 等待 GitHub Actions CI 通过

ssh server 'cd /opt/smartcore-dev && ./scripts/deploy_dev.sh'
ssh server 'cd /opt/smartcore && ./scripts/promote_prod.sh'
```

涉及 SmartCore Agent 模型时，在候选镜像通过后应用并检查 OpenClaw 配置。脚本会先把
当前配置以 `0600` 权限备份，并在校验或 Gateway 重启失败时自动恢复：

```bash
ssh server 'cd /opt/smartcore-dev && ./scripts/configure_openclaw_qwen.sh --apply'
ssh server 'cd /opt/smartcore-dev && ./scripts/configure_openclaw_qwen.sh --status'
```

不要直接在 `/opt/smartcore` 编辑文件，也不要用普通 `docker compose up --build`
替代候选提升流程。

## 验证

```bash
ssh server 'cd /opt/smartcore && docker compose -f deploy/docker-compose.yml ps'
ssh server 'cd /opt/smartcore && docker compose -f deploy/docker-compose.yml exec -T app python -c "import urllib.request; print(urllib.request.urlopen('\''http://127.0.0.1:8000/healthz'\'', timeout=3).read().decode())"'
```

同时确认：

- App 与 OpenClaw Adapter 的 revision label 等于发布提交。
- 两个服务均为 `healthy`，Cloudflared 正在运行。
- Tailscale `/healthz`、`/work` 和一个只读 API 正常。
- 启动日志没有迁移、认证或调度错误。

## 回滚

```bash
ssh server 'cd /opt/smartcore && ./scripts/deploy_prod.sh --rollback'
```

模型配置独立回滚，必须显式使用 `--apply` 输出的备份路径：

```bash
ssh server 'cd /opt/smartcore && ./scripts/configure_openclaw_qwen.sh --rollback /root/.openclaw/backups/openclaw-before-qwen-YYYYMMDDTHHMMSSZ.json'
```

脚本使用上一个已记录镜像回滚，不删除 Docker 卷。若涉及数据迁移，先评估数据库
兼容性；禁止直接覆盖或删除生产数据库。

## 备份与恢复

生产发布前会自动创建 SQLite 一致性快照。手动备份：

```bash
ssh server
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml exec -T app python -c \
  'from app.server.backup.snapshot import run_local_backup; print(run_local_backup())'
```

该命令在 App 容器内操作挂载的数据库和备份 volume。快照命名为
`smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz`。默认在 Server 保留 30 天，可通过
SSH/rsync 同步到 Pi 并保留 90 天；实际目录和保留时间以
`deploy/env.example` 中的 `BACKUP_*`、`PI_*` 配置为准。

恢复会覆盖当前数据库，必须明确指定备份 volume 内的快照文件。以下过程复用当前
App 容器的镜像、环境和 volume，避免操作宿主机上的同名路径：

```bash
ssh server
cd /opt/smartcore
app_id="$(docker compose -f deploy/docker-compose.yml ps -q app)"
image_id="$(docker inspect --format '{{.Image}}' "$app_id")"
docker compose -f deploy/docker-compose.yml stop app
docker run --rm --env-file deploy/.env --volumes-from "$app_id" "$image_id" \
  python -c "from pathlib import Path; from app.server.backup.snapshot import restore_snapshot; from app.server.config import get_settings; cfg = get_settings(); print(restore_snapshot(Path('/app/backups/smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz'), cfg.database_path))"
docker compose -f deploy/docker-compose.yml start app
```

`restore_snapshot` 会先在数据 volume 中保存当前数据库副本。完成后检查容器健康、
关键记录、待提醒事项和重复投递。恢复不得通过 Web 或公网接口暴露，也不得直接
删除生产 volume。仓库中的 `backup_now.sh`、`restore_backup.sh` 只适合环境变量和
数据路径已经指向目标 SQLite 的本地/运维环境，不能直接代替上述 Compose 流程。

## 固定边界

### 公网域名访问

生产环境通过 `https://smartcore.phoenixw.online` 向公网提供工作台访问。流量路径为：

```text
Cloudflare Tunnel -> tunnel-boundary (Caddy) -> app
```

Cloudflare Tunnel 终止 TLS 并连接到 Server 上的 tunnel-boundary 代理（`172.17.0.1:8000`，
即 docker0 网关）。tunnel-boundary 使用 `deploy/Caddyfile.public-routes` 定义的允许清单
过滤请求，只放行以下入口：

- **飞书回调**：`POST /feishu/event`
- **工作台和 API**：`PUBLIC_ACCESS_ENABLED=true` 时，`/work`、`/screen`、`/api/*` 中的
  用户数据和设备 API（需要会话或设备凭证）

以下入口**保持私有**，公网访问返回 404：

- `/agent/*`（OpenClaw Agent API）
- `/api/admin/*`（管理员接口）
- `/api/auth/setup`、`/api/auth/register`（初始化和注册）
- `/dev/state`（Pi 内部状态）
- SSH、SQLite 数据库、备份卷

生产 `deploy/.env` 设置：

```bash
PUBLIC_ACCESS_ENABLED=true
PUBLIC_ORIGIN=https://smartcore.phoenixw.online
AUTH_REGISTRATION_ENABLED=false
AUTH_SETUP_ENABLED=false
AUTH_COOKIE_SECURE=true
TUNNEL_PROXY_NETWORK=172.18.0.1/32
```

主 Caddy 为 `DOMAIN` 配置 HTTPS；该域名的 ACME 证书申请可能失败（因为公网流量走
Cloudflare），但不影响服务。

### 关闭公网访问

若需要关闭公网访问，修改生产 `deploy/.env`：

```bash
PUBLIC_ACCESS_ENABLED=false
```

然后使用当前运行镜像重建容器。必须从部署状态文件读取镜像标签（`/var/lib/smartcore-deploy/state`
由 `deploy_prod.sh` 维护），否则 Compose 会回退到 `latest` 而非当前发布版本：

```bash
ssh server
cd /opt/smartcore
# 读取当前发布的镜像标签
source /var/lib/smartcore-deploy/state
# 使用相同镜像标签重建容器
SMARTCORE_IMAGE_TAG="$CURRENT" docker compose \
    --project-name deploy \
    --project-directory deploy \
    --env-file deploy/.env \
    --file deploy/docker-compose.yml \
    up -d --no-build caddy tunnel-boundary app
```

此操作不删除数据或卷，仅使 tunnel-boundary 拒绝公网 API 请求（飞书回调保持可用）。

**备选方案**：恢复启用公网访问前的环境配置备份：

```bash
ssh server
cd /opt/smartcore
cp deploy/.env.bak-20261016-public deploy/.env
# 然后按上述步骤重建容器
```

### 内网

- Tailscale 上的 `/work`、`/screen`、全部 `/api/*`、`/agent/*`、健康检查和 SSH。
- OpenClaw Gateway：服务器 host user service；Adapter 由 Compose 管理。
- Pi：通过 `deploy/pi/install_to_pi.sh` 从 `app/raspberryPi/yolo` 同步源码。

全部架构、集成和设备说明见 [docs/README.md](./docs/README.md)。
