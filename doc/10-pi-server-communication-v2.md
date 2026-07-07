# Raspberry Pi 与 SmartCore Server 通信架构 v2

本文档描述树莓派侧需要实现的通信、异步照片请求和本地 24 小时识别日志。

## 1. 总体架构

```text
摄像头 / 人脸识别
        |
        v
Pi recognition loop
  |-- 每 10 秒 POST /dev/heartbeat
  |-- 每 60 秒保存 1 张图像 + 1 份 JSON
  |-- 从 heartbeat 响应读取 photoRequest
  |-- 必要时 GET /dev/photo/request 主动轮询
  `-- 按 requestId POST /dev/photo/{requestId}

SmartCore server
  |-- 校验 X-SmartCore-Device-Token
  |-- 写 deviceStateLog
  |-- WebSocket 推送最新状态给 /screen
  |-- 持久化 devicePhotoRequest
  `-- 保存按需上传的照片到 /app/data/device_photos
```

服务器不会主动连接树莓派。照片获取采用“服务器建单、Pi 拉取任务、Pi 回传结果”的异步模式，因此不会受到 NAT、防火墙或 Pi 端口暴露的影响。

## 2. 环境变量

树莓派建议使用 `/etc/smartcore-pi.env`：

```bash
SMARTCORE_SERVER=http://100.65.243.93:8000
SMARTCORE_DEVICE_ID=pi
SMARTCORE_DEVICE_TOKEN=replace-with-device-token
SMARTCORE_LOG_DIR=/var/lib/smartcore-pi/logs
SMARTCORE_HEARTBEAT_SECONDS=10
SMARTCORE_SNAPSHOT_SECONDS=60
SMARTCORE_RETENTION_HOURS=24
```

服务器 `deploy/.env` 至少应包含：

```bash
DEVICE_API_TOKEN=replace-with-the-same-device-token
DEVICE_HEARTBEAT_INTERVAL_SECONDS=10
DEVICE_PHOTO_REQUEST_TTL_SECONDS=300
DEVICE_PHOTO_MAX_BYTES=10485760
DEVICE_PHOTO_DIR=/app/data/device_photos
```

Token 只能放在请求头中，不要写入 JSON、文件名或普通日志：

```text
X-SmartCore-Device-Token: <token>
```

## 3. 10 秒心跳

### 请求

```http
POST /dev/heartbeat
Content-Type: application/json
X-SmartCore-Device-Token: <token>
```

```json
{
  "devId": "pi",
  "currentTime": "2026-07-07T21:30:10+08:00",
  "present": true,
  "persons": [
    {
      "personId": "phoenix",
      "name": "Phoenix",
      "confidence": 0.94,
      "bbox": [114, 72, 328, 406]
    }
  ],
  "stateConfidence": 0.91,
  "state": "working",
  "meta": {
    "camera": "cam0",
    "model": "face-v3",
    "fps": 8.2
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `devId` | 是 | 固定设备 ID，建议 `pi` |
| `currentTime` | 是 | Pi 当前 ISO 8601 时间，必须带时区 |
| `present` | 是 | 是否检测到人 |
| `persons` | 是 | 人物识别结果列表；无人时传空数组 |
| `stateConfidence` | 是 | 对当前状态判断的置信度，0 到 1 |
| `state` | 否 | `working` / `away` / `unknown` / `offline`；缺省时由 `present` 推导 |
| `meta` | 否 | 模型、摄像头、性能等扩展信息 |

只识别一个人时也可以传 `person` 对象，服务器会转成单元素 `persons`。

### 响应

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "serverTime": "2026-07-07T21:30:10.234567+08:00",
    "nextHeartbeatSeconds": 10,
    "state": {
      "deviceId": "pi",
      "state": "working",
      "confidence": 0.91,
      "seenAt": "2026-07-07T21:30:10.234100+08:00",
      "meta": {
        "protocolVersion": 2,
        "reportedAt": "2026-07-07T21:30:10+08:00",
        "present": true,
        "persons": []
      }
    },
    "photoRequest": null
  }
}
```

Pi 应以 `time.monotonic()` 调度 10 秒周期，避免系统时钟校准造成重复或漏发。HTTP 超时建议 5 秒；失败时继续本地识别，并采用 2、5、10、30、60 秒退避重试。

## 4. 异步照片请求

### 4.1 服务器创建请求

Web 管理端或服务器内部调用：

```http
POST /api/device/pi/photoRequest
Content-Type: application/json
```

```json
{
  "reason": "检查当前工位状态",
  "ttlSeconds": 300
}
```

服务器返回 `requestId` 和 `pending` 状态。

### 4.2 Pi 获取请求

优先从每次 `/dev/heartbeat` 响应中的 `data.photoRequest` 获取。也可以主动轮询：

```http
GET /dev/photo/request?devId=pi
X-SmartCore-Device-Token: <token>
```

同一个 `pending` 请求可能在多次心跳中重复出现。Pi 必须使用 `requestId` 去重，并且同一请求只能上传一次。

### 4.3 Pi 上传照片

```http
POST /dev/photo/{requestId}
Content-Type: multipart/form-data
X-SmartCore-Device-Token: <token>
```

表单字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `devId` | text | `pi` |
| `capturedAt` | text | 拍摄时间，ISO 8601，带时区 |
| `recognition` | text | JSON 字符串，可选 |
| `image` | file | JPEG、PNG 或 WebP，默认最大 10 MiB |

示例：

```bash
curl -X POST "$SMARTCORE_SERVER/dev/photo/$REQUEST_ID" \
  -H "X-SmartCore-Device-Token: $SMARTCORE_DEVICE_TOKEN" \
  -F "devId=pi" \
  -F "capturedAt=2026-07-07T21:31:00+08:00" \
  -F 'recognition={"present":true,"persons":[{"name":"Phoenix","confidence":0.94}]}' \
  -F "image=@/tmp/current.jpg;type=image/jpeg"
```

如果拍摄失败：

```http
POST /dev/photo/{requestId}/failed
Content-Type: application/json
X-SmartCore-Device-Token: <token>
```

```json
{
  "devId": "pi",
  "error": "camera timeout"
}
```

### 4.4 服务器查询结果

```text
GET /api/device/photoRequest/{requestId}
GET /api/device/pi/photoRequests?limit=50
GET /api/device/photoRequest/{requestId}/image
```

服务器保存的是“按需请求照片”。Pi 本地每分钟日志不会自动上传。

## 5. Pi 本地 24 小时日志

### 5.1 采样频率

- 识别循环可以持续运行。
- 每 10 秒发送一次状态心跳。
- 每 60 秒落盘一次图像和识别 JSON。
- 保留最近 24 小时，清理任务每 10 分钟运行一次。

### 5.2 目录结构

```text
/var/lib/smartcore-pi/logs/
  2026-07-07/
    21/
      20260707T213000+0800.jpg
      20260707T213000+0800.json
      20260707T213100+0800.jpg
      20260707T213100+0800.json
```

JSON 示例：

```json
{
  "capturedAt": "2026-07-07T21:30:00+08:00",
  "present": true,
  "state": "working",
  "stateConfidence": 0.91,
  "persons": [
    {
      "personId": "phoenix",
      "name": "Phoenix",
      "confidence": 0.94,
      "bbox": [114, 72, 328, 406]
    }
  ],
  "camera": "cam0",
  "model": "face-v3"
}
```

图像与 JSON 必须使用相同的文件名主干。先写临时文件，再使用 `os.replace()` 原子替换，避免断电留下半张图或半份 JSON。

### 5.3 清理策略

清理时以文件修改时间为准：

```python
cutoff = time.time() - 24 * 3600
for path in log_root.rglob("*"):
    if path.is_file() and path.stat().st_mtime < cutoff:
        path.unlink(missing_ok=True)
```

删除过期文件后，再从最深层目录向上删除空目录。日志目录权限建议为 `0700`，图像和 JSON 为 `0600`。

## 6. 推荐的 Pi 主循环

```python
while running:
    frame = camera.latest_frame()
    result = recognizer.infer(frame)

    if monotonic() >= next_snapshot:
        save_snapshot_and_json(frame, result)
        cleanup_older_than_24_hours()
        next_snapshot += 60

    if monotonic() >= next_heartbeat:
        response = post_heartbeat(result)
        request = response.get("photoRequest")
        if request and request["requestId"] not in completed_request_ids:
            upload_current_frame(request, frame, result)
        next_heartbeat += 10
```

不要为心跳重新启动一次模型推理；心跳应读取识别线程维护的“最新结果快照”。摄像头采集、识别、网络发送和磁盘落盘建议分成独立线程或 asyncio task，避免网络抖动阻塞识别。

## 7. systemd 建议

`/etc/systemd/system/smartcore-pi.service`：

```ini
[Unit]
Description=SmartCore Raspberry Pi device client
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
EnvironmentFile=/etc/smartcore-pi.env
WorkingDirectory=/opt/smartcore-pi
ExecStart=/opt/smartcore-pi/.venv/bin/python /opt/smartcore-pi/smartcore_device_client.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smartcore-pi.service
journalctl -u smartcore-pi.service -f
```

## 8. 联调顺序

1. 确保 Pi 与服务器均在线并加入同一 Tailnet。
2. 在服务器和 Pi 配置相同的 `DEVICE_API_TOKEN`。
3. Pi 手工发送一次 `/dev/heartbeat`。
4. 在服务器检查 `GET /api/devState`。
5. 创建 `/api/device/pi/photoRequest`。
6. 等待下一次心跳，确认 Pi 收到 `photoRequest`。
7. 确认请求状态变成 `uploaded`。
8. 打开 `/api/device/photoRequest/{requestId}/image`。
9. 检查 Pi 日志目录中每分钟有一组 JPG/JSON。
10. 将系统时间临时推进或使用测试目录，验证超过 24 小时的文件会被清理。
