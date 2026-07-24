# Idea 与媒体

媒体能力统一使用私有上传、受限 OCR、OpenClaw 提炼和 owner-scoped 附件读取。
浏览器与飞书共享同一组数据模型和安全边界。

## 现行流程

```text
Feishu text/image/file ----> SmartCore ingress ----> private upload
Web upload ----------------> upload API ----------> private upload
                                                       |
                                                       v
OpenClaw scoped task -> image OCR -> concise summary -> Idea + attachments
                                                       |
                                                       v
                                      /work preview and download
```

- 纯文字继续走普通日程、提醒、查询或 Idea 流程。
- 图片、PDF、TXT 和 ZIP 可作为附件；ZIP 不解压、不执行，文档不读取内容。
- 飞书富文本中的文字和全部受支持附件作为同一个任务转发。
- 每张图片都经过一次 `mediaImageOcr`（DeepSeek OCR 2）；用户文字只是摘要上下文。
- OCR 最多 128 tokens、60 秒硬超时且不自动重试。后端按 media job 幂等，重复工具
  调用不会产生第二次上游 OCR 请求。
- OpenClaw 媒体模型把 OCR 与用户文字合成事实性中文 Markdown 摘要，最多 100 字。
- 文档只存储，文件名在没有有效标题时作为回退。

## 数据与状态

- `idea`：标题、Markdown 描述、handled、revision 和来源。
- `ideaAttachment`：已绑定 Idea 的正式附件。
- `ideaUpload`：用户绑定的临时上传。
- `ideaMediaJob`：`queued -> processing -> ready|failed -> consumed`。

图片任务保存受限 OCR 结果、摘要和服务端 evidence。evidence 绑定用户、upload 和
过期时间，浏览器不能读取或回传。`ideaCapture` 与媒体任务完成接口会再次核对 scope、
owner、MIME 和 job 状态。

## 浏览器 API

| API | 用途 |
|---|---|
| `POST /api/idea/uploads` | 上传临时文件 |
| `POST /api/idea/media-jobs` | 为单张图片创建或复用任务 |
| `GET /api/idea/media-jobs/{jobId}` | 查询 owner-scoped 状态和安全错误 |
| `POST /api/idea/media-jobs/{jobId}/retry` | 对失败任务发起显式重试 |
| `POST /api/idea/media-process` | 将浏览器附件作为 web scope 任务转发 |
| `POST /api/idea` | 原子创建 Idea 与附件 |
| `PATCH /api/idea/{ideaId}` | 按 revision 原子编辑元数据和附件差量 |
| `GET /api/idea/attachments/{attachmentId}` | 鉴权预览或下载 |
| `DELETE /api/idea/{ideaId}` | 删除 Idea 并进入统一文件清理流程 |

编辑请求用 `expectedRevision` 防止并发覆盖，并用 `addUploadIds` 与
`removeAttachmentIds` 描述附件变化。省略数组表示不修改附件。任何 owner、任务状态、
类型、数量或 revision 校验失败都不能提交部分更新。

## 飞书与 Agent

飞书下载附件后只把任务局部引用和私有 Adapter 路径传给 OpenClaw，不暴露存储路径
给用户。Agent 相关接口包括媒体 OCR、Idea capture、media-job complete/fail；精确
schema 由 `GET /agent/tools` 提供。

一条富媒体消息要么形成一个一致的 Idea/附件结果，要么保持可诊断的失败状态。
不允许回调处理器绕过 OpenClaw 直接根据 OCR 写 Idea，也不允许模型提交任意服务器
路径或 URL。

## 存储与安全

- 文件位于 `IDEA_MEDIA_DIR` 对应的私有 volume，不由 Caddy 静态公开。
- 允许 JPEG、PNG、WebP、PDF、TXT 和 ZIP；默认单文件上限由
  `IDEA_MEDIA_MAX_BYTES` 控制，图片另受 `VISION_MAX_IMAGE_BYTES` 限制。
- 服务端校验 MIME/扩展名并生成不可猜测存储名；展示文件名不能参与路径拼接。
- 下载设置安全的 `Content-Disposition` 和 `nosniff`；Markdown 禁止 raw HTML。
- 图片可在鉴权 lightbox 中查看和下载；文档只提供下载。
- 数据库先提交，之后再做有界文件删除；仍被数据库引用的附件不得由回滚/清理删除。
- 日志只记录任务、附件 ID、类型、大小和结果，不记录附件内容、OCR evidence、scope
  或供应商原始响应。

## 前端状态

新建和编辑均显示同一个附件管理器。现有附件移除在保存前可撤销；取消编辑不改变
Idea。新文件有 uploading、processing、ready、failed 稳定状态，图片未 ready 时
不能保存。失败可重试或移除，生成摘要必须先展示并允许用户编辑，不能静默拼接到
描述中。

回滚应用不会删除现有 Idea/附件行。若要停用模型处理，可关闭媒体入口；已保存附件
仍应保持可读。
