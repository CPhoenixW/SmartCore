# 设备、Raspberry Pi、Mac 与 Windows

设备只有出站连接：客户端通过 Tailscale 调用 Server，Server 不主动连接 Pi，也不
公开摄像头或识别服务。

## 通用设备配对

1. 登录用户调用 `POST /api/device/pair/start` 创建短期配对。
2. 客户端用 code 调用 `POST /api/device/pair/{pairId}/claim`。
3. 用户在工作台调用 `POST /api/device/pair/{pairId}/confirm`。
4. 客户端本地确认后调用 `POST /api/device/pair/{pairId}/activate`，仅此响应返回一次
   `deviceToken`。
5. 客户端保存 token；Server 只保存哈希。删除/撤销设备会使 token 失效。

配对记录归属发起用户且会过期。客户端不能通过请求体选择 owner，未配对或已撤销
设备不能写状态、照片、事件或 receipt。

## 命令分发

- 用户向自己的设备调用 `POST /api/device/dispatch` 创建命令。
- 设备用 `GET /api/device/dispatch` 拉取待处理命令。
- 设备用 `POST /api/device/receipt` 确认结果。

每条命令包含 `dispatchId`、`kind`、`payload` 和 Server 派生的 `userId`。设备只能
读取和确认自己的记录；重复确认不会创建第二条业务结果。

## Pi 状态

部署脚本 `deploy/pi/install_to_pi.sh` 将 `app/raspberryPi/yolo` 同步到 Pi，并保留
设备本地的 `.smartcore.env`、模型、人脸样本、抓拍和日志。

当前轻量客户端使用：

```dotenv
SMARTCORE_BASE_URL=http://server-tailnet-name:8000
SMARTCORE_DEV_ID=pi
SMARTCORE_DEVICE_TOKEN=replace-with-device-token
SMARTCORE_POST_TIMEOUT=5
```

它将识别结果映射为 `working`、`away` 或 `offline` 后上报 `/dev/state`。需要携带
人物列表、客户端时间和照片请求的实现使用 `POST /dev/heartbeat`：

```json
{
  "devId": "pi",
  "currentTime": "2026-07-24T15:00:00+08:00",
  "present": true,
  "persons": [],
  "stateConfidence": 0.91,
  "state": "working",
  "meta": {"camera": "cam0"}
}
```

`state` 只接受 `working`、`away`、`unknown` 或 `offline`。Server 以接收时间记录
freshness，并把新状态广播给 `/work` 与 `/screen`。请求失败时 Pi 继续本地识别，
不能因为 Server 不可用而停止摄像头流程。

## 按需照片

```text
POST /api/device/{deviceId}/photoRequest       Server/Web 创建请求
GET  /dev/photo/request?devId={deviceId}       Pi 拉取请求（也可从 heartbeat 响应取得）
POST /dev/photo/{requestId}                    Pi 上传 multipart 图片
POST /dev/photo/{requestId}/failed             Pi 报告失败
GET  /api/device/photoRequest/{requestId}       Server/Web 查询状态
GET  /api/device/photoRequest/{requestId}/image Server/Web 读取图片
```

上传包含 `devId`、`capturedAt`、可选 recognition JSON 和 image。只允许 JPEG、PNG、
WebP，大小由 `DEVICE_PHOTO_MAX_BYTES` 控制。Pi 必须按 `requestId` 去重，设备 token
与 `devId` 必须匹配。图片存入私有目录，不由 Caddy 静态公开。当前 Server/Web 照片
路由依赖 Tailscale 网络边界，因此不能暴露到公网；通用用户设备接口另有 session
所有权校验。

## Pi 本地数据

`known_faces/`、`captures/`、`output/`、`logs/`、`.venv/`、模型和环境文件都不进入
Git。人脸样本属于生物特征数据，只能保留在设备本地。日志不得包含 token 或原始
人脸内容，并应按本地保留策略清理。

安装后至少验证：systemd user service 为 active、连续状态可见、过期状态显示为
unknown/offline、照片请求只上传一次、其他设备 token 无法冒用该 `deviceId`。

## Mac 使用监视器

`app/computer/macos` 是无界面的 Swift 用户级 LaunchAgent。每 20 秒读取前台应用和
任意键鼠输入空闲时间，并监听锁屏、休眠和唤醒；状态或应用变化时立即同步，每 30 秒
发送心跳，每分钟生成一个桶。输入空闲达到 2 分钟时进入 `idle`。状态为 `active`、
`idle`、`locked`、`sleeping`；旧版 `paused` 仍兼容，`offline` 由 Server 根据心跳超时
派生。只有 active slice 携带应用。

会话从活跃开始，短暂空闲继续；空闲达到 10 分钟、锁屏、休眠或暂停即结束。未确认
桶保存在本地 SQLite，每批最多上传 120 个，成功确认后删除，失败指数退避。队列按
`deviceId` 隔离，重新配对不会把旧身份数据发给新用户；token 存在应用支持目录的
owner-only `0600` 文件中。旧开发版 Keychain token 由安装脚本一次性迁移且不输出。

客户端默认通过 macOS 辅助功能权限采集过滤后的聚焦窗口标题。密码管理器、银行、
支付和系统认证场景始终只保留应用名。可选结构化上下文只提取浏览器域名、IDE 工作区
和文档文件名；完整 URL、文件路径、网页/文档正文、键盘内容、剪贴板和截图都不采集。
ChatGPT（`com.openai.codex`）的辅助功能树不暴露会话标题。客户端仅从桌面端运行日志读取
当前会话 ID，再映射本机的会话标题索引；读取不到时回退为应用窗口标题，不读取 rollout
文件或聊天正文。该兼容路径不依赖辅助功能权限。
使用 `SmartCoreMonitor structured-context on|off|status` 控制结构化字段，标题采集不受
该开关影响。`SmartCoreMonitor accessibility status|open` 可检查或打开辅助功能授权；
未授权时仍记录前台应用，但 active 窗口标题为空。测试与安装：

```bash
swift test --package-path app/computer/macos
app/computer/macos/scripts/install.sh
```

`SmartCoreMonitor codex-report` 从标准输入接收最多 100 条项目报告 JSON，并复用本机
Computer token 上传。它只承载项目名、结果状态、单段摘要、可选时间及 commit/PR/测试
证据，不读取或上传 Codex 对话、代码和推理；Server 以 task/date 幂等保存。

新设备在工作台“设备 -> Computer”创建配对，将配对 JSON 通过标准输入交给
`SmartCoreMonitor pair`，在工作台确认后由客户端激活。安装脚本把签名可执行文件放在
`~/Library/Application Support/SmartCoreMonitor/bin`，并注册登录自启和异常重启。
设备管理页按 Computer、RaspberryPi、Screen 和 Feishu Bot 四类隔离配对、管理与参数。
Server 可结合当前 Plan、电脑状态与同用户新鲜 Pi 状态生成带 reason codes 的确定性
判断，但不输出效率或分心结论。启用 `COMPUTER_WORK_BLOCK_ANALYSIS_ENABLED` 后，Server
每分钟根据 active、20 分钟 idle、锁屏/休眠/暂停和上下文变化维护连续工作块；小时任务
只保存客观快照。工作块开始、切换、结束或 Plan 语义需要更新时，Server 使用
正式版 `deepseek-v4-flash-0731` 做一次结构化分析；展示文本由 Server 限长清洗，
Schema 错误不会重复请求，且失败不默认回退到 OpenClaw
`qwen3.7-plus`，任务租约和退避不影响原始上传。工作日志不再作为独立的 Computer 日终
模型任务或前端卡片生成；Daily summary 直接使用 Codex 汇报、Computer 工作块和 Plan
证据。历史 `ComputerDailyWorkLog` 记录与兼容接口保留，但不会由调度器继续创建。
工作块累计 active 二十分钟时滚动更新同一标题与总结，以后每新增六十分钟 active 再更新；
只有新增活动证据才调用模型。`COMPUTER_ATTENTION_REMINDERS_ENABLED` 独立控制注意力提醒：
当前 Plan 下连续 idle 五分钟提醒；无 Plan 时需 open 工作块先累计 active 二十分钟。提醒只
说明电脑操作已暂停，不判断用户是否在使用手机；锁屏、休眠、暂停和离线均跳过。

## Windows 使用监视器

`app/computer/windows` 是无界面的 .NET 8 用户任务，功能与 macOS 客户端保持一致：每
20 秒读取前台窗口和输入空闲时间，每 30 秒发送心跳，每分钟生成桶；锁屏、睡眠、唤醒和
解锁由 Windows 会话/电源事件更新。Windows 前台窗口只通过 Win32 获取应用身份和标题，
不读取键盘、剪贴板、截图、网页正文、完整 URL 或完整文件路径。敏感应用和认证窗口沿用
macOS 的脱敏规则，结构化上下文默认关闭。

客户端使用同一 `/api/computer/activity/batch`、`/api/computer/heartbeat` 和
`/api/computer/codex-reports/batch` 协议，离线队列按 `deviceId` 隔离并在成功响应返回的
桶时间后删除。安装脚本 `app/computer/windows/scripts/install.ps1` 发布自包含 `win-x64`
程序并注册当前用户的登录任务；卸载只停止任务，保留本地配置、token 和队列。Windows
系统时区会映射为 Server 要求的 IANA 名称，无法映射时通过 `SMARTCORE_TIMEZONE` 显式
配置。
