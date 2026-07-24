# Computer Monitor

`macos/` 是 Swift/AppKit 菜单栏开发版。它采集客观电脑状态，按分钟离线排队，并用
computer 设备 token 上传到 SmartCore；不采集键盘内容、URL、剪贴板或截图。

```bash
swift test --package-path app/computer/macos
swift run --package-path app/computer/macos SmartCoreMonitor
```

在 `/work` 的“设备 -> 电脑使用”创建配对，将 JSON 粘贴到菜单栏的
`Pair Device...`，回到工作台确认，然后授予辅助功能权限。当前版本仅用于开发运行，
没有安装器、登录项或签名发布。
