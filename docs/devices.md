# 设备、Raspberry Pi 与 Mac

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

新设备在工作台“设备 -> Computer”创建配对，将配对 JSON 通过标准输入交给
`SmartCoreMonitor pair`，在工作台确认后由客户端激活。安装脚本把签名可执行文件放在
`~/Library/Application Support/SmartCoreMonitor/bin`，并注册登录自启和异常重启。
设备管理页按 RaspberryPi、Computer、Screen 和 Feishu Bot 四类隔离配对、管理与参数。
Server 可结合当前 Plan、电脑状态与同用户新鲜 Pi 状态生成带 reason codes 的确定性
判断，但不输出效率、分心或任务内容推断。启用 `COMPUTER_ANALYSIS_ENABLED` 后，调度器
每小时第 5 分钟排队上一完整小时的 AI 注释，并在 `Asia/Shanghai` 每日 23:59 排队工作日志；
OpenClaw 只读取脱敏聚合上下文并使用 `qwen3.7-plus`，结果写入追加分析表。分析失败或
OpenClaw 不可用不影响原始上传，失败记录会在下一次调度重试。
