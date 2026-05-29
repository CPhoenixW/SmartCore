# 网络边界与安全

本文档描述 SmartCore v1 的网络访问边界和安全策略。

## 网络分区

系统分为两个访问区域：

1. **公网区域**

   只有飞书开放平台可以访问的 HTTPS 回调路径。

2. **Tailscale 内部区域**

   只有你的手机、电脑、树莓派和服务器可以访问的内部服务。

## 公网入口

公网入口由 Caddy 提供 HTTPS。

公网只允许访问：

```text
POST /feishu/event
```

这个路径用于接收飞书事件，例如用户给机器人发消息、点击按钮等。

公网不允许访问：

```text
/admin
/dashboard
/api
/docs
/backup
/metrics
/data
```

如果需要调试 FastAPI 的 OpenAPI 文档，应该只在开发环境或 Tailscale 内部开放。

## Caddy 职责

Caddy 负责：

- 自动申请和续期 HTTPS 证书。
- 接收公网请求。
- 只转发飞书事件路径。
- 拒绝其他公网路径。

推荐思路：

```text
https://your-domain.com/feishu/event -> app:8000/feishu/event
其他路径 -> 404 或 403
```

内部 Web 面板不要挂在公网域名上。

## 飞书请求校验

FastAPI 在处理 `/feishu/event` 时必须做校验。

至少需要校验：

- verification token。
- event signature 或 encrypt key 机制。
- 请求时间戳，避免重放攻击。
- 飞书事件类型是否在允许列表内。

如果校验失败：

- 不执行任何业务逻辑。
- 返回拒绝结果。
- 记录安全日志。

## Tailscale 内部访问

内部访问用于：

- Web 管理面板。
- 内部 API。
- 备份同步。
- 日志查看。
- 后续设备执行器。

访问路径示例：

```text
手机浏览器 -> http://server-tailnet-name:8000
电脑浏览器 -> http://server-tailnet-name:8000
服务器 -> ssh pi@raspberry-pi-tailnet-name
服务器 -> rsync backups/ pi@raspberry-pi-tailnet-name:/home/pi/smartcore-backups
```

## 密钥管理

不要提交到 Git：

- `passwd.txt`。
- `.env`。
- 飞书 app secret。
- 飞书 verification token。
- 飞书 encrypt key。
- SSH private key。
- SQLite 数据库。
- 备份文件。

可以提交到 Git：

- `env.example`。
- `Caddyfile` 模板。
- `docker-compose.yml` 模板。
- 文档。
- 课表 CSV 模板。

## SSH 与树莓派

服务器同步备份到树莓派时，推荐：

- 使用 SSH key。
- 禁止在脚本里写明文密码。
- 树莓派上创建专用备份目录。
- 只给备份目录必要权限。

部署变量示例：

```text
PI_USER=pi
PI_HOST=raspberrypi
PI_BACKUP_DIR=/home/pi/smartcore-backups
```

如果你使用 `passwd.txt` 作为本地配置文件，它应该只存在于部署机器上，并加入 `.gitignore`。

## 最小权限原则

v1 的安全边界应遵循：

- 飞书只能进入飞书事件处理器。
- 手机和电脑可以访问 Web 面板。
- 树莓派只接收备份，不访问主数据库。
- 数据库只被服务器上的 app 访问。
- 备份恢复只能手动执行，不提供公网按钮。

