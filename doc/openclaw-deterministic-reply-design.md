# OpenClaw 确定性回复设计

## 原因

OpenClaw 已成功生成最终文本，但模型没有按提示调用 SmartCore 反馈接口。
Adapter 只记录 `finalAssistantVisibleText`，因此飞书只有“已收到，正在处理…”而
没有最终回复。提示词属于软约束，不能作为消息投递保证。

## 方案

- OpenClaw 只负责查询、修改数据并生成一段最终用户文本。
- Adapter 从 OpenClaw JSON 结果中提取最终文本。
- Adapter 使用服务器上的 Agent token 文件和事件携带的签名 scope，固定调用
  `POST /agent/feedback/send_text`。
- OpenClaw 失败或没有最终文本时，Adapter 发送简短失败提示，避免消息永久停在
  “处理中”。
- Adapter 不允许模型直接调用反馈接口，避免最终文本与工具回复重复发送。

## 验收标准

1. 成功结果恰好发送一次最终文本。
2. OpenClaw 非零退出或缺少最终文本时发送一次失败提示。
3. 缺少 token、scope 或 SmartCore 拒绝请求时记录错误，不输出 token。
4. 回复目标只能由签名 scope 决定，Adapter 不传 chat ID、用户 ID 等目标字段。
5. Adapter 单元测试覆盖成功、OpenClaw 失败和回复接口失败。
6. 生产端到端验证必须看到回调、OpenClaw 完成、反馈接口 200 和飞书最终消息。

## 数据、接口与回滚

- 不修改数据库、现有 API 合约或 UI。
- 继续使用现有 `/agent/feedback/send_text`。
- 回滚只需恢复上一 Adapter/app 镜像。
- 生产凭据仍只存在服务器文件和容器挂载中。
