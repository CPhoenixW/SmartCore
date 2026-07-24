# 总体架构

SmartCore 是服务器主控的个人事务系统。Server 是唯一权威节点；Pi、Web、手机副屏
和未来电脑监视器都是客户端。

```text
Feishu -> Cloudflare/Caddy -> Server /feishu/event -> OpenClaw Adapter
Pi -----------------------> Server device API
Vue / Computer / Screen --> Server HTTP/WebSocket
Server scheduler ---------> Screen or Feishu
```

## 原则

- 所有业务数据、规则、调度和审计归 Server。
- 公网只开放飞书回调；其他入口只走 Tailscale。
- Pi 本地识别 `working/away/unknown`，不访问数据库。
- OpenClaw 负责自然语言与编排，只调用受限 Agent API。
- 确定性提醒不依赖 LLM；外部服务失败不能阻断核心调度。
- 数据库使用 SQLite，并在发布和定时任务中创建一致性快照。

代码边界见 [25-multi-device-project-layout.md](./25-multi-device-project-layout.md)。
