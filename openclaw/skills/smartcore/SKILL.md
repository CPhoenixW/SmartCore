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
- Every handled Feishu event must end with `sendText` or `sendCard` so the user gets feedback.
- Pass routing context from the forwarded event: use `chat_id` / `receiveId` from `event.chat_id` or `event.chat.chat_id`.

## Feedback payloads

`sendText` body:

```json
{
  "text": "已记录：明天晚上洗衣服",
  "chat_id": "oc_xxx"
}
```

`sendCard` body:

```json
{
  "chat_id": "oc_xxx",
  "card": { "type": "template", "data": {} }
}
```

If `chat_id` is omitted, SmartCore falls back to `FEISHU_DEFAULT_CHAT_ID`.

## Deprecated

Do not call `query_events`, `create_event`, `update_event`, or `delete_event`. Those old contracts are removed.
