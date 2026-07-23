# OpenClaw output and media contract

## Feishu ingress contract

- `im.message.receive_v1` rich-text (`message_type=post`) input is accepted in
  the receive-event shape `{"title": ..., "content": [[...]], "content_v2": [[...]]}`.
- The locale-wrapped send shape `{"post": {"zh_cn": ...}}` remains accepted for
  compatibility, but is not assumed to be the receive-event shape.
- Text, every image key, and every supported file key are extracted before the
  event is forwarded to OpenClaw. Images are downloaded privately by SmartCore.
- Ingress parsing logs `event_id`, `message_id`, message type, and only media/text
  counts; it never logs attachment bytes or credentials.
- Unsupported messages are persisted to `msgLog` with an `unsupported:*` status
  so a callback that returned HTTP 200 remains diagnosable and deduplicated.

## Acceptance criteria

### Daily report

- The scheduled report is always a Chinese finished report. Internal analysis, tool output,
  English planning text, event IDs, and delivery instructions are never persisted or sent.
- The first line is exactly `📅 **YYYY年MM月DD日 工作日报**` for the requested date.
- The four required sections appear exactly once and in order: overview, outcomes,
  blockers, and tomorrow plan.
- Commute, punch-card, departure, ticket-grabbing, and equivalent life/logistics records
  are excluded. A cancelled DDL linked to a done plan is excluded as database noise.
- Claims must come from the queried event title, status, and description. Missing technical
  details are stated as unavailable; the agent must not reuse facts from another day/session.
- The adapter extracts only the valid report portion and validates it before persistence.
  One isolated retry is allowed; an invalid second result is marked failed and is not sent as
  a successful report.

### Image and document ideas

- Every image is stored and passed once through `mediaImageOcr` (DeepSeek OCR 2), whether
  or not accompanying text exists. User text is optional context for the final summary.
- OCR generation is capped at 128 tokens with a 60-second hard timeout and no automatic
  retries. This keeps extraction focused, prevents unbounded waits, and avoids duplicate cost.
- OpenClaw uses DeepSeek V4 Pro to combine the OCR result and user text into one factual
  Markdown description of at most 100 Chinese characters.
- `mediaImageOcr` returns short-lived, owner-bound evidence. Agent-side `ideaCapture`
  rejects an image upload without valid OCR evidence, so prompt drift cannot silently skip OCR.
- PDF/TXT/ZIP files are storage-only. They are never read or sent to OCR and need no OCR
  evidence. Their filename is used when no meaningful title is supplied.
- Plain text remains the normal schedule, reminder, query, and Idea workflow.

### Idea attachment preview

- Image thumbnails open a full-screen preview; the preview closes by backdrop, close button,
  or Escape.
- Every image can be downloaded from both the attachment row and the enlarged preview.
- Document attachments remain one-click downloads through the authenticated attachment URL.

## Security and rollback

- OCR evidence is HMAC-signed with the existing server auth secret, contains only user ID,
  upload ID, and expiry, and is never persisted in the browser.
- Attachment reads and OCR remain owner-scoped. Documents cannot be submitted to OCR.
- There is no schema or historical-data migration. Rollback is a deployment of the previous
  application revision; existing Idea and attachment rows remain valid.

## Test matrix

- Daily report: valid Chinese output, leaked analysis before a valid report, wrong headings,
  wrong date, and invalid retry.
- Media: image with text, image without text, multiple images, document-only, forged/expired/
  cross-user OCR evidence, and document OCR rejection.
- UI: thumbnail enlargement, close controls, authenticated image download, document download,
  Markdown detail rendering, and Chinese/English labels.
