# SmartCore

SmartCore 是一个服务器主控的个人事务系统。服务器保存数据并负责调度、飞书、
OpenClaw 和 Web 工作台；树莓派负责工位状态检测；电脑监视器作为独立客户端演进。

## 目录

```text
app/server/             FastAPI 与核心业务
app/raspberryPi/yolo/   Pi 识别和心跳服务
app/computer/macos/     Swift/AppKit 电脑使用监视器
frontend/               服务器托管的 Vue 工作台
deploy/                 Docker 与网络配置
scripts/                验证、发布、备份和恢复
```

依赖方向固定为 `端侧客户端 -> Server API/WebSocket`。端侧代码不得导入
`app.server` 或直接访问数据库。

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check app/server tests
cd frontend && npm ci && npm test && npm run build
swift test --package-path app/computer/macos
```

服务器入口：

```bash
uvicorn app.server.main:app --host 127.0.0.1 --port 8000
```

## 发布

正常发布使用已验证候选镜像，不直接修改生产目录：

```bash
git push origin dev
ssh server 'cd /opt/smartcore-dev && ./scripts/deploy_dev.sh'
ssh server 'cd /opt/smartcore && ./scripts/promote_prod.sh'
```

生产目录为 `/opt/smartcore`，候选目录为 `/opt/smartcore-dev`。提升脚本会备份
SQLite、切换已验证镜像、检查健康，并在失败时恢复上一版本。

回滚：

```bash
ssh server 'cd /opt/smartcore && ./scripts/deploy_prod.sh --rollback'
```

## 网络与安全

- 公网仅允许 `POST /feishu/event`，由 Caddy/Cloudflare Tunnel 转发。
- `/work`、`/screen`、内部 API 和健康检查只通过 Tailscale 访问。
- 密钥只存放在服务器或设备本地 `.env`；数据库、备份、人脸样本和模型权重不进 Git。
- Python 与前端依赖分别锁定在 `requirements*.lock` 和 `frontend/package-lock.json`。

当前架构见 [docs/architecture.md](./docs/architecture.md)，部署细节见
[deploy.md](./deploy.md)，文档索引见 [docs/README.md](./docs/README.md)。参与开发的
模型和维护者先阅读 [AGENTS.md](./AGENTS.md)。
