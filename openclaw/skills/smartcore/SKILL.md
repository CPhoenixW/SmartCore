---
name: smartcore
description: Use SmartCore as the authoritative student secretary backend from OpenClaw, with DeepSeek as the model provider and SmartCore APIs as the only data/feedback surface.
---

# SmartCore OpenClaw Skill

Use this skill when a user asks about schedules, classes, assignments, deadlines, life events, reminders, study planning, or changes to SmartCore-managed data.

## Runtime Roles

- OpenClaw owns natural-language understanding, multi-step planning, ambiguity handling, and orchestration.
- DeepSeek is the model backend for reasoning.
- SmartCore owns Feishu gateway handling, database CRUD, confirmation, scheduler reminders, card rendering, audit logs, backups, and the dashboard.

## Non-Negotiable Boundaries

- You must call `GET /agent/tools` before relying on tool shape when the active session lacks the current contract.
- You must call SmartCore only through authenticated `/agent/*` APIs.
- You must never access SQLite files, Docker volumes, backups, `.env`, or production secrets directly.
- You must not construct Feishu card JSON; use `/agent/feedback/` tools so SmartCore renders cards.
- You must not bypass SmartCore pending-operation confirmation for create, update, or delete actions.

## Required Tool Rules

- Before calling any `/agent/*` endpoint, follow the exact JSON bodies in `references/smartcore-tools.md`.
- Query requests must use `/agent/db/query_events`.
- For relative dates such as 今天, 明天, 今晚, 本周, compute explicit `filter.time_range.start` and `filter.time_range.end` using the event `request.timezone` and `request.now`; do not send top-level `start_time` or `end_time`.
- Create requests must use `/agent/db/create_event`.
- Update requests must use `/agent/db/update_event`; query candidates first unless the target id is known, then use either `selector.id` or `selector.refs` exactly as documented.
- Delete/cancel requests must use `/agent/db/delete_event`; query candidates and clarify before destructive actions.
- Feedback must use `/agent/feedback/send_text`, `/agent/feedback/send_query_result_card`, `/agent/feedback/send_operation_success_card`, or `/agent/feedback/send_reminder_card`.
- When SmartCore returns `pending_confirmation`, present or explain that SmartCore has created a confirmation step. Do not claim the write is applied until SmartCore confirms it.

## Common Flows

User asks: 今天有什么安排

1. Convert today to explicit `time_range.start` and `time_range.end`.
2. Call `query_events` with `event_type: all` and open statuses.
3. Send the result with `send_query_result_card`.

User asks: 今晚八点提醒我写作业

1. Convert 今晚八点 to an ISO-8601 `start_at`.
2. Call `create_event` with `event_type: schedule` or `deadline` depending on wording.
3. If `pending_confirmation` is returned, tell the user to confirm through SmartCore's card/flow.

User asks: 把晚上的事推迟一小时

1. Query tonight's candidates first.
2. If exactly one candidate is plausible, call `update_event` with the candidate id and new time.
3. If multiple candidates match, ask a clarifying question before updating.

Card action arrives with `smartcore_action: openclaw_card_intent`

1. Read the `intent`, `event_id`, and `event_type` from the card action value.
2. For `complete_event`, call `update_event` with the appropriate status patch.
3. For `delay_event` or `modify_event`, clarify the desired new time unless the card payload gives one.

See `references/smartcore-tools.md` for the tool contract and examples.
