# Raspberry Pi 通信协议 v2

Pi 是无入站端口的边缘客户端：本地识别状态，通过 Tailscale 向 Server 上报；
Server 不主动连接 Pi。

## 配置

Pi 使用 `/etc/smartcore-pi.env` 或 `yolo/.smartcore.env`：

```bash
SMARTCORE_SERVER=http://server-tailnet-name:8000
SMARTCORE_DEVICE_ID=pi
SMARTCORE_DEVICE_TOKEN=replace-with-device-token
SMARTCORE_HEARTBEAT_SECONDS=10
SMARTCORE_SNAPSHOT_SECONDS=60
SMARTCORE_RETENTION_HOURS=72
SMARTCORE_LOG_DIR=/home/phoenix/yolo/logs
```

Token 只放在 `X-SmartCore-Device-Token` 请求头和设备本地环境文件中。

## 心跳

`POST /dev/heartbeat`，请求体：

```json
{
  "devId": "pi",
  "currentTime": "2026-07-24T15:00:00+08:00",
  "present": true,
  "persons": [{"personId":"user","name":"User","confidence":0.94,"bbox":[1,2,3,4]}],
  "stateConfidence": 0.91,
  "state": "working",
  "meta": {"camera":"cam0","model":"yolo11n+face"}
}
```

`state` 只能是 `working`、`away`、`unknown` 或 `offline`。Server 以接收时间为准
记录状态，并在响应的 `data.photoRequest` 中返回一个待处理照片请求。失败时 Pi 继续
本地识别，按 2、5、10、30、60 秒退避重试。

## 按需照片

```text
POST /api/device/{devId}/photoRequest       登录用户创建请求
GET  /dev/photo/request?devId={devId}       Pi 主动轮询（可选）
POST /dev/photo/{requestId}                 Pi 上传 multipart 图片
POST /dev/photo/{requestId}/failed          Pi 报告拍摄失败
GET  /api/device/photoRequest/{requestId}   登录用户查询结果
GET  /api/device/photoRequest/{requestId}/image
```

Pi 必须按 `requestId` 去重。上传表单包含 `devId`、`capturedAt`、可选
`recognition` JSON 和 `image`；默认最大 10 MiB。图片只能通过鉴权 API 读取，不由
Caddy 公开。

## 本地数据

Pi 每分钟保存受限权限的 JPEG 与同名 JSON，按小时分目录，并按
`SMARTCORE_RETENTION_HOURS` 清理。`known_faces/`、`captures/`、`output/`、`logs/`、
`.venv/`、模型和环境文件均不进入 Git。

源码与服务定义位于 `app/raspberryPi/yolo`。部署使用：

```bash
SMARTCORE_PI_SERVER_URL=http://server-tailnet-name:8000 ./deploy/pi/install_to_pi.sh
```

验收：Pi 服务为 active；连续心跳可见；过期后 Server 显示 unknown；照片请求只
上传一次；日志和请求中不出现 token 或人脸原图内容。
