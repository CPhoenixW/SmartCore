# Computer Monitor

`macos/` 是无界面的 Swift LaunchAgent。它采集客观电脑状态和前台应用，按分钟离线
排队，并使用 computer 设备 token 上传；不采集窗口标题、URL、键盘内容、剪贴板或
截图，也不需要辅助功能权限。

```bash
swift test --package-path app/computer/macos
app/computer/macos/scripts/install.sh
```

新设备先在 `/work` 的“设备 -> Computer”创建配对，把 JSON 通过标准输入交给
`SmartCoreMonitor pair`，再回到工作台确认。`SmartCoreMonitor status` 只显示本地配对
状态，不输出 token。安装脚本保留现有配置、本地 token 和 SQLite 队列；旧开发版的
Keychain token 会在安装时一次性迁移。
