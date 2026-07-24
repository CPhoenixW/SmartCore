# 设备职责

| 设备 | 职责 | 禁止事项 |
|---|---|---|
| Server | 数据库、业务、调度、飞书、OpenClaw、API、Web | 不公开内部 API/数据卷 |
| Raspberry Pi | 摄像头识别、心跳、按需照片、本地日志、备份接收 | 不写数据库、不发提醒 |
| Computer | 开发、Web 工作台；未来常驻监视器 | 不成为权威节点 |
| Phone Screen | 展示状态与提醒，接收 WebSocket | 不保存主数据 |
| Feishu | 移动输入、卡片操作、离开工位提醒 | 不直接访问内部 API |

所有设备通过 Tailscale 访问 Server；只有飞书平台通过公网回调进入。Pi 与 Computer
端只依赖 Server 协议，不能导入 `app.server` 内部模块。

部署目录分别为 `app/server`、`app/raspberryPi` 和 `app/computer`。
