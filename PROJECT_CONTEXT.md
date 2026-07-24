# SmartCore 项目上下文

更新日期：2026-07-24。

## 当前状态

SmartCore 已采用三端结构：

- `app/server`：唯一权威服务，负责数据库、业务、调度、飞书、OpenClaw、设备 API。
- `app/raspberryPi/yolo`：摄像头识别、状态心跳和按需照片上传。
- `app/computer`：未来电脑端常驻监视器；当前为空边界。
- `frontend`：服务器托管的 Vue 工作台，不属于原生电脑监视器。

生产运行在 `server:/opt/smartcore`，候选构建在 `/opt/smartcore-dev`。生产使用
Docker Compose，应用入口为 `app.server.main:app`。

## 系统边界

```text
Feishu -> public /feishu/event -> Server -> OpenClaw Adapter
Pi ----------------------------> Server device API
Vue / Computer / Screen -------> Server HTTP/WebSocket
Server scheduler --------------> Screen or Feishu
```

- Server 是唯一数据库写入方。
- Pi 和电脑端只消费版本化协议，不导入服务器内部代码。
- 公网入口只接受飞书回调；管理界面和内部 API 走 Tailscale。
- OpenClaw 不读取 SQLite 或业务卷，只调用受限 Agent API。

## 主要入口

- FastAPI：`app/server/main.py`
- 配置：`app/server/config.py`
- 数据库：`app/server/db/`
- 业务：`app/server/new_core/`
- 调度：`app/server/scheduler/`
- 设备：`app/server/device/`、`app/server/user_device/`
- Pi：`app/raspberryPi/yolo/`
- Vue：`frontend/`

## 开发与发布

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app/server tests
cd frontend && npm test && npm run build
```

代码先推送到 `dev`，服务器运行 `scripts/deploy_dev.sh` 构建并验证候选；确认后在
生产目录运行 `scripts/promote_prod.sh`。不得在 `/opt/smartcore` 直接开发或修改配置。

## 数据与安全

- 生产数据、备份和 `.env` 必须留在服务器卷或设备本地。
- Pi 的 `known_faces/` 是生物特征数据，不同步到 Git 或服务器。
- 数据库迁移必须保留现有记录；任何重置都需要用户明确授权。
- 部署前备份，部署后核对 revision、容器健康、`/healthz` 和关键只读链路。

详细说明以 [README.md](./README.md)、[deploy.md](./deploy.md) 和
[doc/README.md](./doc/README.md) 为准。
