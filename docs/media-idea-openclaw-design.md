# OpenClaw media idea intake

## Accepted behaviour

1. Plain text continues through OpenClaw unchanged: schedules, reminders, queries, and daily reports still work.
2. OpenClaw, not the Feishu callback or browser, decides how an attachment-bearing message is handled.
3. A document-only message is stored without reading its content. Each attachment is captured as an Idea named from its filename; optional user text is retained as a note.
4. An image with no meaningful text is handled the same way as a document: store it and name the Idea from its filename. It must not trigger OCR or a text-model request.
5. An image with meaningful text calls the scoped `mediaImageOcr` tool (DeepSeek OCR 2). The media OpenClaw model is `deepseek-v4-pro`; it combines only the OCR result and user text, writes one Markdown description of at most 100 characters, and captures the attachments.
6. An explicit scheduling/reminder request wins over media capture. The agent must not make up a schedule from an image.
7. The browser creates the same forwarded OpenClaw event after upload. It shows queued processing and refreshes the Idea list; it never receives model credentials.

## Contract and security

- `POST /agent/media/ocr` accepts one temporary upload id. It validates the signed task scope, the upload owner, image MIME type, and the vision size limit before reading a server-only file and invoking `deepseek-ocr-2`.
- `POST /api/idea/media-process` is browser-authenticated. It validates ownership of all upload ids, issues a short-lived `web` agent scope, and forwards only metadata and task-local attachment paths to the existing adapter.
- Agent scopes have explicit `feishu` and `web` purposes. A web scope has no bot/chat and cannot be used for Feishu delivery endpoints.
- Original files live in the existing private Idea media volume. Attachment reads remain owner-authorized through `/api/idea/attachments/{attachmentId}`.

## UI states

- Uploading, queued, completed and failed states are visible in the composer.
- Markdown is rendered through an escaping local renderer; raw HTML is never inserted.
- Images use the existing authorized thumbnail/download endpoint and lightbox; documents are download-only.

## Migration and rollback

No schema migration is required: `idea`, `ideaUpload`, and `ideaAttachment` already model the required one-to-many relation. Existing records remain untouched. Roll back by promoting `c9983e6`; it restores the previous media routing while preserving newly stored attachments and Ideas.

## Test matrix

- Plain text schedule query remains forwarded to the default agent model.
- Image with text exposes OCR only to the scoped owner and uses the media model.
- Image without text and document-only messages do not call OCR.
- Cross-user OCR and browser-process requests are rejected.
- Heading is extracted from final markdown into the Feishu card title and removed from the card body.
- Browser media dispatch, Markdown rendering, i18n labels, image preview and document download build successfully.
