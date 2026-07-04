# 提醒确认、延时与过期体验验收

## 背景

当前提醒已经能推送到电脑端和副屏 WebSocket，但手机端 Fully Kiosk Browser 可能因为 WebView 省电、自动播放、后台网络或页面未保持前台等设置导致表现不稳定。产品侧需要把提醒从“单纯弹出”升级为“可确认、可延时、可过期归档”的闭环，保证即使声音没有响，用户仍能在副屏右侧看到清楚的状态。

## 目标体验

- 手机副屏收到提醒后显示专门提醒页，不与普通今日事项混在一起。
- 提醒页提供两个主操作：
  - `已完成`：将对应事件状态改为 `done`。
  - `延时 10 分钟`：将 `lifeEvt.dueAt` 或 `ddlEvt.ddlAt` 后移 10 分钟，并允许下一次到点继续提醒。
- 如果提醒出现 60 秒内没有被确认或延时，则认为这个提醒在副屏上已经过期：
  - 提醒页自动收起。
  - 右侧提醒栏下三分之一显示该过期提醒。
  - 过期提醒使用红色文字。
- 右侧工作信息栏按三段式布局：
  - 上三分之一：最新提醒。
  - 中三分之一：当天其他事项，放不下可滚动。
  - 下三分之一：已过期未确认提醒，放不下可滚动。
- 不再把“最早的事项”强行作为最顶部大卡；最新提醒优先，其余今日事项进入中间区域。
- 飞书提醒也使用交互式卡片，包含 `已完成` 和 `延时 10 分钟` 按钮。
- 飞书卡片回调由 SmartCore 直接处理并修改数据库：
  - `reminderDone`：更新事件 `stat=done`，life 事件补 `doneAt`。
  - `reminderSnooze10`：更新事件提醒时间为当前时间后 10 分钟。

## Fully Kiosk Browser 使用建议

这些是部署后的设备设置建议，不作为后端测试条件：

- 允许 JavaScript、WebSocket 和本地存储。
- 关闭 Android 电池优化，保持 Wi-Fi 在休眠时不断开。
- 开启 Keep Screen On / Prevent Sleep。
- 开启 Reload on Network Reconnect 或类似网络恢复刷新。
- 如果需要声音，首次打开 `/screen` 后手动点一次页面，用于解锁浏览器音频策略；之后提醒音才能稳定播放。
- 若 Fully Kiosk 提供 Autoplay / Media Playback / Play Sounds 相关设置，应允许页面播放声音。

## 验收测试

- `tests/test_reminder_ack_snooze.py`
- `tests/test_screen_reminder_panel.py`
- `tests/test_new_arch_notify.py`
- `tests/test_feishu_agent_loop.py`
