# Cloudflared 与 OpenClaw Adapter Compose 整合设计

## 目标

- `docker compose` 统一管理 SmartCore app、两个 Caddy 边界、Cloudflared 和 OpenClaw Adapter。
- 保持现有 Feishu 公网回调地址和 Adapter 监听地址不变。
- 迁移时不输出或提交 Tunnel、Agent、Events Token。
- Adapter 失败可恢复原 systemd 服务，Cloudflared 失败可恢复原独立容器。

## 边界

- OpenClaw Gateway 仍由宿主机 user systemd 管理，不迁入 Compose。
- DERP 与 SmartCore 无关，保持独立。
- Adapter 使用 host network，以访问宿主机 `127.0.0.1:18789` OpenClaw Gateway。
- Adapter 只挂载现有 `/root/.openclaw` 和工作区；SQLite volume 不对其开放。
- Cloudflared 保持 Docker 默认 bridge 网络，继续访问现有 Tunnel 边界。

## 验收标准

1. Compose 中新增 `cloudflared` 和 `openclaw-adapter`。
2. 两个服务的密钥只来自服务器上 gitignored 的 env 文件。
3. Adapter 镜像通过 `/healthz`，并能执行挂载的 OpenClaw CLI。
4. Cloudflared 新容器建立 Tunnel 连接后才移除旧容器。
5. Adapter 新容器健康后才停用原 systemd 服务。
6. 一键部署同时版本化 app 与 Adapter 镜像，失败时恢复两者。
7. 生产 `/healthz`、`/work/login`、设备心跳和 SQLite 完整性保持正常。

## 数据与回滚

- 无数据库或 API 迁移。
- Adapter 日志迁入 Docker named volume。
- Adapter 回滚：停止 Compose 服务并重新启动原 systemd 服务。
- Cloudflared 回滚：停止 Compose 服务并重新启动保留的旧容器配置。
