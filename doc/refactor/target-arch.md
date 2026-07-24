# 重构目标归档

2026-07 重构将 SmartCore 收敛为服务器主控系统：

- Server 保存数据、执行业务、调度提醒并承载飞书/OpenClaw/Web。
- Raspberry Pi 只检测状态并调用设备 API。
- 电脑和手机只通过 Tailscale 使用 HTTP/WebSocket。
- 公网只开放飞书回调，内部服务不直接暴露。

这些目标已落地。当前结构见 [多端项目结构](../25-multi-device-project-layout.md)。
