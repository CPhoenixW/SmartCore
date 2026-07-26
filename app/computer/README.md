# Computer Monitor

`macos/` 是无界面的 Swift LaunchAgent。它采集客观电脑状态、前台应用和过滤后的窗口
标题，按分钟离线排队，并使用 computer 设备 token 上传。可选结构化上下文只包含域名、
IDE 工作区和文档名；敏感应用只记录应用名，不采集完整 URL/路径、正文、键盘内容、
剪贴板或截图。

```bash
swift test --package-path app/computer/macos
app/computer/macos/scripts/install.sh
```

新设备先在 `/work` 的“设备 -> Computer”创建配对，把 JSON 通过标准输入交给
`SmartCoreMonitor pair`，再回到工作台确认。`SmartCoreMonitor status` 只显示本地配对
状态，不输出 token。安装脚本保留现有配置、本地 token 和 SQLite 队列；旧开发版的
Keychain token 会在安装时一次性迁移。用 `SmartCoreMonitor structured-context on|off`
控制结构化上下文采集，`SmartCoreMonitor status` 同时显示辅助功能授权状态和当前二进制
路径。若未授权，运行 `SmartCoreMonitor accessibility open` 打开 macOS 辅助功能设置，
添加并启用该路径下的 `SmartCoreMonitor`。标题只在 `active` 状态采集；未授权时仍记录
前台应用，但窗口标题为空。
