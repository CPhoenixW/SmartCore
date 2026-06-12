# OpenClaw SmartCore Bridge

## Goal

SmartCore should become the deterministic system layer for OpenClaw. In the
方案 B deployment SmartCore still owns the Feishu webhook. OpenClaw receives
normalized events from SmartCore and calls SmartCore tools to operate data:

```text
Feishu messages and card callbacks
  -> SmartCore Feishu Gateway
  -> OpenClaw
  -> SmartCore Agent APIs
  -> SmartCore Feedback APIs
  -> Feishu
```

SmartCore keeps ownership of data, reminders, Feishu card templates, audit logs,
operation confirmation, and deployment. OpenClaw owns natural-language
understanding, task decomposition, and multi-step orchestration.

## Runtime Modes

- With `OPENCLAW_EVENTS_ENDPOINT` configured, SmartCore forwards accepted Feishu
  text messages and card callbacks to OpenClaw. SmartCore must not run local
  natural-language parsing for those events.
- Without `OPENCLAW_EVENTS_ENDPOINT`, SmartCore may use the legacy local parser
  path for local development and emergency fallback only. New production
  natural-language behavior belongs in OpenClaw.

## Feishu Gateway

When `OPENCLAW_EVENTS_ENDPOINT` is configured, SmartCore must forward every
accepted Feishu text message and card callback to OpenClaw after verification and
deduplication. SmartCore must not run its local natural-language parser for those
events. The forwarded event must include:

- stable event id and source (`feishu`)
- event type (`message` or `card_action`)
- user and chat identifiers
- text or card action payload
- original Feishu payload for debugging
- SmartCore thread/context identifiers

If forwarding fails, SmartCore should acknowledge Feishu to avoid retry storms,
record the failure, and expose it in logs or the operation panel.

OpenClaw event payloads must include a `request` object:

```json
{
  "timezone": "Asia/Shanghai",
  "now": "2026-06-12T10:00:00+08:00"
}
```

Card buttons on reminder cards should carry an intent payload such as
`complete_event` or `delay_event`. SmartCore forwards that card action to
OpenClaw; OpenClaw decides which SmartCore tool to call next.

## Agent API

OpenClaw calls SmartCore through authenticated HTTP APIs. The first supported
surface is:

- `GET /agent/tools`
- `POST /agent/db/query_events`
- `POST /agent/db/create_event`
- `POST /agent/db/update_event`
- `POST /agent/db/delete_event`
- `POST /agent/feedback/send_text`
- `POST /agent/feedback/send_query_result_card`
- `POST /agent/feedback/send_operation_success_card`
- `POST /agent/feedback/send_reminder_card`

`/agent/tools` is the contract OpenClaw uses to discover tool names, endpoints,
input schemas, output schemas, risk levels, and confirmation requirements.

Database write APIs must return SmartCore pending-operation results when the
operation needs confirmation. Destructive or bulk actions must require
confirmation. OpenClaw must never edit tests, fixtures, database files, Docker
volumes, or backups directly.

### OpenClaw Tool Rules

OpenClaw should use SmartCore tools as follows:

- Query: call `/agent/db/query_events` with explicit `time_range.start` and
  `time_range.end` whenever the user gives relative dates such as 今天, 明天, 今晚.
- Create/update/delete: call the matching `/agent/db/*` endpoint and present the
  returned pending operation via SmartCore feedback cards.
- Feedback: call `/agent/feedback/*`; do not construct Feishu card JSON inside
  OpenClaw unless SmartCore adds a dedicated passthrough tool later.
- Ambiguity: ask a clarifying question or query candidates first. Do not invent
  event ids or schedule data.

## Reminder Loop

SmartCore keeps the automatic reminder loop. It scans the database on its own
schedule and sends reminder cards itself. Reminder card buttons must return to
the SmartCore Feishu Gateway, then be forwarded to OpenClaw as `card_action`
events so OpenClaw can decide whether to snooze, complete, modify, cancel, or
continue the task.

OpenClaw must not be required for the minute-by-minute due-reminder scan.

## Security

OpenClaw must never access the SQLite database file, Docker volumes, or backup
directories directly. It must only call SmartCore APIs with an agent token.

SmartCore should log all OpenClaw-originated tool calls with actor, source event,
request body, result status, and operation id when applicable.
