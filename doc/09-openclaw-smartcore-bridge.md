# OpenClaw SmartCore Bridge

## Goal

SmartCore should become the deterministic system layer for OpenClaw:

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

## Agent API

OpenClaw calls SmartCore through authenticated HTTP APIs. The first supported
surface is:

- `GET /agent/tools`
- `POST /agent/db/query_events`
- `POST /agent/feedback/send_text`
- `POST /agent/feedback/send_query_result_card`
- `POST /agent/feedback/send_operation_success_card`
- `POST /agent/feedback/send_reminder_card`

`/agent/tools` is the contract OpenClaw uses to discover tool names, endpoints,
input schemas, output schemas, risk levels, and confirmation requirements.

Database write APIs must be added behind the same contract, but destructive or
bulk actions must require confirmation.

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

