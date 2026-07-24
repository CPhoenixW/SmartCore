# Computer monitor

电脑端常驻监视器的独立边界，当前尚未实现。它应通过 Server HTTP/WebSocket 契约
读取状态，不导入 `app.server`，并拥有独立的构建、测试和发布流程。

现有 `frontend/` 是由 Server 托管的 Web 工作台，不迁入这里。
