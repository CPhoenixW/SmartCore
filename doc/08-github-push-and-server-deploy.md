# GitHub 推送与服务器部署手册

本文档描述 SmartCore 从本地开发、推送 GitHub，到服务器拉取、重建和验证的完整流程。

## 基本信息

- 本地仓库：`/Users/phoenixw/SmartCore`
- 服务器 SSH 别名：`server`
- 服务器仓库：`/opt/smartcore`
- 生产 Compose 目录：`/opt/smartcore/deploy`
- 生产 Compose 文件：`/opt/smartcore/deploy/docker-compose.yml`
- 应用容器名：`deploy-app-1`
- 当前生产端口：由 `deploy/.env` 的 `APP_BIND` 决定，例如 `100.65.243.93:8000`
- 健康检查：`/healthz`

## 部署前检查

在本地仓库执行：

```bash
cd /Users/phoenixw/SmartCore
git status --short
```

确认：

- 只包含本次准备发布的代码、文档或测试修改。
- 不要提交本地数据文件，例如 `timetable.csv`。
- 不要提交真实密钥、`.env`、数据库文件或备份文件。

运行测试和 lint：

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check app tests
```

只有在测试和 lint 通过后再推送。

## 本地提交与推送 GitHub

查看当前分支：

```bash
git branch --show-current
```

SmartCore 当前默认发布分支是 `main`。如需发布到生产，通常应在 `main` 上操作。

暂存指定文件，不要使用 `git add .`：

```bash
git add app/path/to/file.py tests/test_xxx.py doc/xxx.md
```

再次确认暂存内容：

```bash
git status --short
git diff --cached --stat
```

提交：

```bash
git commit -m "简短说明本次修改"
```

推送到 GitHub：

```bash
git push origin main
```

推送后可以确认本地提交：

```bash
git rev-parse --short HEAD
```

记下输出的提交号，后面要和服务器确认一致。

## 服务器拉取代码

登录服务器：

```bash
ssh server
```

进入仓库：

```bash
cd /opt/smartcore
```

确认服务器工作区干净：

```bash
git status --short
```

如果服务器上出现未提交修改，先不要拉取。需要判断这些修改是否为生产配置、临时调试或误改代码。正常情况下，服务器代码工作区应保持干净。

拉取最新 `main`：

```bash
git pull --ff-only origin main
```

确认服务器提交号与本地一致：

```bash
git rev-parse --short HEAD
```

## 生产重建与启动

注意：不要在 `/opt/smartcore` 根目录直接执行 `docker compose up`，因为 compose 文件在 `deploy/` 目录。

进入生产 Compose 目录：

```bash
cd /opt/smartcore/deploy
```

重建并启动：

```bash
docker compose up -d --build
```

查看容器状态：

```bash
docker compose ps
```

期望看到：

- `deploy-app-1` 状态为 `Up`
- `deploy-caddy-1` 状态为 `Up`
- `deploy-tunnel-boundary-1` 状态为 `Up`

## 健康检查

先查看端口绑定：

```bash
docker compose ps
```

如果 `app` 端口显示类似：

```text
100.65.243.93:8000->8000/tcp
```

则使用该地址检查：

```bash
curl -fsS http://100.65.243.93:8000/healthz
```

成功时应返回：

```json
{"status":"ok"}
```

也可以从容器日志确认启动完成：

```bash
docker logs --tail 80 deploy-app-1
```

期望看到：

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
GET /healthz HTTP/1.1" 200 OK
```

## 一条命令部署

确认本地已经推送后，可以从本地执行：

```bash
ssh server 'cd /opt/smartcore && git pull --ff-only origin main && cd deploy && docker compose up -d --build && docker compose ps'
```

然后按实际 `APP_BIND` 地址执行健康检查：

```bash
ssh server 'curl -fsS http://100.65.243.93:8000/healthz'
```

如果服务器的 Tailscale IP 变化，先在服务器查看 `deploy/.env` 中的 `APP_BIND`：

```bash
ssh server 'cd /opt/smartcore/deploy && grep "^APP_BIND=" .env'
```

## 回滚流程

如果部署后发现问题，先查看最近提交：

```bash
cd /opt/smartcore
git log --oneline -5
```

回到上一个已知可用提交：

```bash
git checkout <good_commit_sha>
cd deploy
docker compose up -d --build
```

验证健康检查通过后，再决定是否在本地创建 revert 提交：

```bash
cd /Users/phoenixw/SmartCore
git revert <bad_commit_sha>
git push origin main
```

生产环境临时 `git checkout <sha>` 只用于止血。最终仍应通过 `main` 上的 revert 或修复提交恢复一致状态。

## 常见问题

### `no configuration file provided: not found`

原因：在 `/opt/smartcore` 根目录执行了 `docker compose`。

解决：

```bash
cd /opt/smartcore/deploy
docker compose up -d --build
```

### `curl 127.0.0.1:8000/healthz` 失败

原因：生产端口可能没有绑定到 loopback，而是绑定到 Tailscale IP，例如 `100.65.243.93`。

解决：

```bash
cd /opt/smartcore/deploy
docker compose ps
curl -fsS http://<APP_BIND>:8000/healthz
```

### `git pull --ff-only` 失败

原因：服务器工作区有本地提交或本地修改，无法快进。

处理原则：

- 不要直接 `git reset --hard`，避免误删服务器上的重要修改。
- 先执行 `git status --short` 和 `git diff` 看清楚改动。
- 如果确认是无用临时改动，再手动清理。
- 如果是生产配置，应移到 `deploy/.env`，不要放进代码文件。

### 容器启动后接口不通

检查容器状态：

```bash
cd /opt/smartcore/deploy
docker compose ps
docker logs --tail 120 deploy-app-1
```

常见原因：

- `deploy/.env` 缺少必要环境变量。
- 数据库路径或 volume 配置错误。
- 飞书或 LLM 密钥配置错误。
- 代码启动时报 import 或配置异常。

## 发布检查清单

每次发布前后按下面顺序走：

1. 本地 `git status --short` 干净或只有本次改动。
2. 本地 `pytest` 通过。
3. 本地 `ruff check app tests` 通过。
4. `git add` 只暂存目标文件。
5. `git commit`。
6. `git push origin main`。
7. 服务器 `git pull --ff-only origin main`。
8. 服务器 `cd /opt/smartcore/deploy && docker compose up -d --build`。
9. `docker compose ps` 确认容器 `Up`。
10. `curl /healthz` 返回 `{"status":"ok"}`。
11. `docker logs --tail 80 deploy-app-1` 无启动异常。
