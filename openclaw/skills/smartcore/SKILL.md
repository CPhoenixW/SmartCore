---
name: smartcore
description: Thin OpenClaw bridge to SmartCore agent tools on the server.
---

# SmartCore OpenClaw Skill

Use this skill when the user asks about schedules, reminders, ideas, or SmartCore-managed data.

## Boundaries

- Call `GET /agent/tools` first when tool shape is uncertain.
- Use only authenticated `/agent/*` endpoints with `X-SmartCore-Agent-Token` and the per-message `X-SmartCore-Agent-Scope` supplied in the OpenClaw prompt.
- Treat `/agent/tools` as the source of truth for tool names, paths, schemas, and aliases.
- Never read SQLite, backups, Docker volumes, or `.env` directly.

## Tool Order

1. Discover tools: `GET /agent/tools`
2. Read/query: `evtQuery`
3. Write directly: `evtCreate`, `evtUpdate`, `evtDelete`, `ideaCapture`, `ideaToEvt`
4. Return one concise user-facing final answer; the Adapter delivers it to Feishu.

The preferred DB paths are `/agent/db/query_events`, `/agent/db/create_event`,
`/agent/db/update_event`, and `/agent/db/delete_event`. The old short paths remain
available only as compatibility aliases.

## Query Rules

- For 今天、明天、今晚、本周等相对时间，always send an explicit `timeRange.start`
  and `timeRange.end` using the `request.timezone` and `request.now` values from the
  forwarded event.
- Set `includeLinkedPlans` to `true` for schedule queries. DDL-generated plan events
  are real schedule entries and include a `ddlLink` object identifying the parent DDL.
- Read query results from `data.events`. Use `data.count`, `data.totalMatched`, and
  `data.truncated` when deciding whether to summarize or ask the user to narrow the query.
- Use `evtId` returned by SmartCore. Never invent ids.
- Query candidates before modifying or cancelling an ambiguous event.

Example query:

```json
{
  "stat": "todo",
  "timeRange": {
    "start": "2026-07-07T00:00:00+08:00",
    "end": "2026-07-07T23:59:59+08:00"
  },
  "includeLinkedPlans": true,
  "limit": 100
}
```

## Write Rules

- Clear requests execute immediately; do not ask for mechanical confirmation cards.
- Ambiguous requests should get one short clarifying question.
- `life` is accepted as an alias of `plan`; returned records use the database value `plan`.
- DDL uses `endTime` or the compatibility alias `ddlAt`.
- Plan uses `stTime` or the compatibility alias `dueAt`.
- Keep request bodies small and stable.
- Check `ok`, `stat`, and `errors` on every response before reporting success.

## Reply Rules

- Do not call `sendFeishuText`, `sendFeishuCard`, or `/agent/feedback/*` while handling
  a forwarded event.
- Return exactly one concise user-facing final answer. The Adapter sends that text
  through SmartCore using the signed scope.
- Never include internal reasoning, tool output, tokens, IDs, or delivery instructions
  in the final answer.
