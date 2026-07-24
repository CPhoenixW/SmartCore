# 多端项目结构

## 目标

SmartCore 按部署单元组织代码，而不是把不同设备的实现放进同一个运行时包：

```text
app/
  computer/             # 电脑端常驻监视器，当前仅定义边界
  raspberryPi/
    yolo/                # 摄像头、识别、心跳和 systemd 服务
  server/                # FastAPI、数据库、调度、飞书和核心业务
frontend/                # 由 server 托管的 Vue 工作台
```

`app/server` 是唯一权威节点。它拥有数据库和业务规则，对外提供 HTTP 与
WebSocket 契约。`app/raspberryPi` 和未来的 `app/computer` 都是客户端，只通过
这些契约通信，不导入服务器内部模块，也不直接读写数据库。

## 边界规则

### Server

- Python 包入口为 `app.server.main:app`。
- 保存数据库、执行业务规则和调度任务。
- 管理认证、设备注册、飞书、OpenClaw 和通知。
- `frontend/` 仍由 Server 构建和托管，因此不属于原生电脑监视器。

### Raspberry Pi

- 采集摄像头画面，在本地计算 `working`、`away` 或 `unknown`。
- 仅向 Server 上报心跳和按请求上传当前照片。
- `.env`、人脸样本、抓拍、日志、虚拟环境和模型权重是设备本地状态。
- 模型不进入 Git；使用 `yolo/scripts/fetch_models.sh` 下载并校验。

### Computer

- 用于后续独立的常驻状态监视器，而不是复制 Vue 工作台。
- 只消费稳定 API/WebSocket 契约，并拥有自己的构建、测试和发布生命周期。
- 在需求明确前不预设 Electron、Tauri 或原生框架。

## 依赖方向

```text
computer --------> server contracts <-------- raspberryPi/yolo
                         ^
                         |
                 frontend web client
```

端侧代码不能反向依赖 `app.server`。未来出现跨端共享结构时，应先把它定义为
版本化协议（例如 OpenAPI schema 或 JSON schema），而不是建立共享业务包，避免
设备发布节奏与服务器实现耦合。

## 敏感资产

从 Raspberry Pi 导入源码时，不纳入 Git 的内容包括：设备 token、`.venv`、
`known_faces/`、`captures/`、`output/`、`logs/`、缓存和备份。人脸样本属于生物
特征数据，必须只保留在设备上。生产 token 应通过设备本地环境文件配置。
