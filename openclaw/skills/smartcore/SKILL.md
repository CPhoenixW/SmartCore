---
name: smartcore
description: Thin OpenClaw bridge to SmartCore agent tools on the server.
---

# SmartCore OpenClaw Skill

Use this skill when the user asks about schedules, reminders, ideas, or SmartCore-managed data.

## Boundaries

- Call `GET /agent/tools` first when tool shape is uncertain.
- Use only authenticated `/agent/*` endpoints with `X-SmartCore-Agent-Token`.
- Never read SQLite, backups, or `.env` directly.
- Do not use old tool names such as `query_events` or `create_event`.

## Tool Order

1. Discover tools: `GET /agent/tools`
2. Read/query: `evtQuery`
3. Write directly: `evtCreate`, `evtUpdate`, `evtDelete`, `ideaCapture`, `ideaToEvt`
4. Feedback: `sendText`, `sendCard`, `screenPush`

## Rules

- Clear requests execute immediately; do not ask for mechanical confirmation cards.
- Ambiguous requests should get one short clarifying question.
- Keep request bodies small and stable.
- Feishu replies should stay short.

## Deprecated

Do not call `query_events`, `create_event`, `update_event`, or `delete_event`. Those old contracts are removed.
