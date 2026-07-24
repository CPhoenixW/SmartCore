# 网络与安全边界

## 网络

- 公网：Caddy 和 Cloudflare Tunnel 只转发 `POST /feishu/event`。
- Tailscale：`/work`、`/screen`、内部 API、设备 API、健康检查和 SSH。
- 数据层：SQLite、媒体和备份卷只挂载到所需容器，不提供静态公网访问。

Pi 仅主动连接 Server，不开放摄像头或识别服务端口。OpenClaw Adapter 只能调用
Agent API，不读取 SQLite、生产数据卷或备份目录。

## 鉴权

- 飞书：verification token、签名/加密和时间戳校验，并按事件 ID 去重。
- Web：登录 session 与用户所有权校验。
- Pi：独立设备 token，通过 `X-SmartCore-Device-Token` 传递。
- OpenClaw：独立 Agent token 与事件 scope。

## 密钥与数据

不得提交 `.env`、token、SSH 私钥、数据库、备份、抓拍、人脸样本、日志或模型权重。
日志只记录必要的 ID、状态和错误，不记录 token、附件内容或生物特征数据。

生产配置保存在 `/opt/smartcore/deploy/*.env`；Pi 配置保存在设备本地环境文件。
任何恢复、清库或 token 轮换都必须显式执行并留下审计。
