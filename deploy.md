# SmartCore 发布

## 环境

| 用途 | 位置 | 分支 |
|---|---|---|
| 候选构建 | `server:/opt/smartcore-dev` | `dev` |
| 生产 | `server:/opt/smartcore` | `main` |

生产配置、数据库和备份只保留在服务器，不进入 Git。

## 发布流程

1. 本地验证并推送 `dev`。
2. 服务器构建候选镜像，运行后端、前端、容器和隔离健康检查。
3. 提升脚本将已验证提交快进到 `main`，备份 SQLite，并切换 App 与 Adapter 镜像。

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app/server tests
cd frontend && npm test && npm run build
git push origin dev

ssh server 'cd /opt/smartcore-dev && ./scripts/deploy_dev.sh'
ssh server 'cd /opt/smartcore && ./scripts/promote_prod.sh'
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

- 公网：仅 `/feishu/event`。
- 内网：Tailscale 上的 `/work`、`/screen`、API 和健康检查。
- OpenClaw Gateway：服务器 host user service；Adapter 由 Compose 管理。
- Pi：通过 `deploy/pi/install_to_pi.sh` 从 `app/raspberryPi/yolo` 同步源码。

全部架构、集成和设备说明见 [docs/README.md](./docs/README.md)。
