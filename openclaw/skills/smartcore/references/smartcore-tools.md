# SmartCore Tool Contract for OpenClaw

Always discover the live contract from `GET /agent/tools` when possible. This reference explains expected behavior.

## Database Tools

### query_events

Endpoint: `POST /agent/db/query_events`

Use for all schedule, course, assignment, deadline, and life-event lookups. Include explicit `time_range.start` and `time_range.end` for relative user language.

### create_event

Endpoint: `POST /agent/db/create_event`

Use for new events. Returns `pending_confirmation` for writes that require user confirmation.

### update_event

Endpoint: `POST /agent/db/update_event`

Use for changes to title, time, notes, or status. Query first when the target is ambiguous.

### delete_event

Endpoint: `POST /agent/db/delete_event`

Use for cancel/delete operations. Clarify before destructive actions and never delete without a clear target.

## Feedback Tools

### send_text

Endpoint: `POST /agent/feedback/send_text`

Use for short clarification questions or plain status updates.

### send_query_result_card

Endpoint: `POST /agent/feedback/send_query_result_card`

Use after `query_events` to present normalized events.

### send_operation_success_card

Endpoint: `POST /agent/feedback/send_operation_success_card`

Use after SmartCore reports an operation has been applied.

### send_reminder_card

Endpoint: `POST /agent/feedback/send_reminder_card`

Use only when OpenClaw intentionally asks SmartCore to render an actionable reminder card. Routine due-reminder scans remain inside SmartCore scheduler.

## Safety Rules

- SmartCore is the source of truth for data and Feishu cards.
- Never access SQLite, Docker volumes, backups, or `.env` files directly.
- Do not invent event ids. Use ids returned by `query_events`.
- Do not claim a write is complete when SmartCore returns `pending_confirmation`.
- Clarify before destructive actions when more than one candidate could match.
