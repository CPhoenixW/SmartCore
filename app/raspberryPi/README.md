# Raspberry Pi

`yolo/` 是 Pi 端工位状态服务：本地识别并上报心跳，不访问数据库、不调度提醒。

密钥、人脸样本、抓拍、日志、虚拟环境和模型权重只保留在设备上。部署入口为
[`deploy/pi/install_to_pi.sh`](../../deploy/pi/install_to_pi.sh)，协议见
[设备与 Raspberry Pi](../../docs/devices.md)。
