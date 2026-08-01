# Computer Monitor

`macos/` 是无界面的 Swift LaunchAgent，`windows/` 是无界面的 .NET 用户任务。两者
使用同一配对、心跳、分钟桶和 Codex report 协议：采集客观电脑状态、前台应用和过滤后的
窗口标题，按分钟离线排队，并使用 Computer 设备 token 上传。Server 统一决定工作块边界、
项目投入和日报内容；客户端不运行大模型。

两个客户端都不采集完整 URL/路径、正文、键盘内容、剪贴板或截图。可选结构化上下文只
包含域名、IDE 工作区和文档名；敏感应用始终只记录应用身份。Windows 的构建、安装、
配对和命令见 [`windows/README.md`](./windows/README.md)。

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
前台应用，但普通应用的窗口标题为空。ChatGPT 桌面端会从本机运行日志取得当前会话 ID，
再映射会话标题元数据；不读取 rollout 文件或聊天正文，也不依赖辅助功能权限。
