# Pi 服务速查

- 主程序：`detect_usb.py`
- 环境：`/etc/smartcore-pi.env` 或 `.smartcore.env`
- 心跳：`POST /dev/heartbeat`
- 服务：`systemd/smartcore-yolo.service`
- 模型：运行 `scripts/fetch_models.sh`

设备只向 Server 发起请求，不开放入站端口。`.env`、人脸样本、抓拍、日志、
虚拟环境和模型权重均为设备本地资产，不得提交或同步到服务器。

完整协议见仓库 `doc/10-pi-server-communication-v2.md`。
