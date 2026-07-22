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
3. Write directly: `evtCreate`, `evtUpdate`, `evtComplete`, `evtDelete`,
   `ideaCapture`, `ideaToEvt`
4. Return one concise user-facing final answer; the Adapter delivers it to Feishu.

## Image Ideas

- A forwarded message may contain `imageAnalysis`, produced from a Feishu image.
- When it is labelled `图片灵感输入`, save the analysis with `ideaCapture`, using
  `srcType=image`. An explicit request to create a plan, reminder, or DDL takes
  precedence over capturing an idea.

The preferred DB paths are `/agent/db/query_events`, `/agent/db/create_event`,
`/agent/db/update_event`, and `/agent/db/delete_event`. The old short paths remain
available only as compatibility aliases.

## Query Rules

- Run event queries with the bundled helper; do not construct `curl` commands:
  `python3 skills/smartcore/scripts/query_events.py --scope '<signed scope>' ...`
- For a single local day, including 今天、明天 or a specific calendar date, prefer
  `--date YYYY-MM-DD`. Resolve relative dates from the forwarded
  `request.timezone` and `request.now`.
- For a multi-day or partial-day range, send `--start` and `--end` as absolute
  ISO-8601 date-times with offsets.
- Never send `start_time`, `end_time`, `filter`, `filter.time_range`, or other
  undocumented fields. If SmartCore returns `ok: false`, correct the request from
  `errors`; never interpret a failed call as an empty schedule.
- Set `includeLinkedPlans` to `true` for schedule queries. DDL-generated plan events
  are real schedule entries and include a `ddlLink` object identifying the parent DDL.
- Set `includeCourseTemplates` to `false` for calendar queries so a recurring course
  template is not duplicated with its generated plan occurrence.
- Read query results only from `data.items`. Use `data.count` and `data.total`.
  Do not pipe a response through `head`, truncate it, or perform local date filtering.
- Use `evtId` returned by SmartCore. Never invent ids.
- Query candidates before modifying or cancelling an ambiguous event.
- Do not add `--status` unless the user explicitly asks for unfinished, completed,
  or cancelled items.

Single-day command:

```bash
python3 skills/smartcore/scripts/query_events.py \
  --scope '<signed scope from the current prompt>' \
  --date 2026-07-20
```

The helper sends this range contract internally:

```json
{
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
- When the user says a task is complete and provides an outcome, progress note,
  reflection, or lesson learned, use `evtComplete` with the exact `evtId` and a
  concise `summary`. It marks the event done and appends `完成总结：...` to the
  existing description.
- Do not use `evtUpdate` to replace the description when recording a completion
  summary. Query ambiguous candidates first, then call `evtComplete`.
- Keep request bodies small and stable.
- Check `ok`, `stat`, and `errors` on every response before reporting success.

## Scheduled Daily Summary

- A forwarded `daily_summary` event is read-only. Query exactly its `reportDate`
  with no status filter, `includeLinkedPlans=true`, and course templates hidden.
- Read every returned event's title, status, and description. Descriptions are
  the primary source for completion outcomes and reflections.

### Filtering & Anti-Noise Rules

- Skip auxiliary life/logistics events (commute, punch-card, transit) with no
  substantive work output.
- If a DDL is cancelled but its linked plan is done, the task completed on time.
  Do not report the cancelled DDL — it is database-level noise.
- Focus on business outcomes and duration, not rigid time billing.

### Content Extraction

- For completed tasks: extract core technical highlights (scripts, commands,
  features) and pitfalls/troubleshooting notes from descriptions.
- For unfinished/blocked tasks: extract the specific blocking reason and turn
  it into next-day action input.

### Output Template

Report in this exact structure using rich Markdown:

📅 [YYYY年MM月DD日] 工作日报

### 📝 本日工作概述
> [1-2 sentence high-level summary]

### 🚀 今日主要成果与技术进展
- **{module}**
  - **进展**: [accomplishment]
  - **技术要点/避坑**: [technical details]

### ⚠️ 遇到问题与阻碍 (Blockers)
- **{issue}**: [description]

### 📅 明日规划
- [next actions]

- Do not mutate events and do not call the daily-summary persistence endpoint.
  The Adapter saves the final answer before delivering it.

## Formatting Output

All final answers are rendered inside a Feishu interactive card via `lark_md`.
Use these freely — the Adapter handles the conversion:

- `#` / `##` headings
- `**bold**` and `*italic*`
- `-` unordered lists
- GFM tables (auto-converted to card column layouts)

## Reply Rules

- Do not call `sendFeishuText`, `sendFeishuCard`, or `/agent/feedback/*` while handling
  a forwarded event.
- Open the reply with a `#` heading that doubles as the card title.
- Return exactly one concise user-facing final answer. The Adapter sends that text
  through SmartCore using the signed scope.
- Use structured Markdown whenever it improves readability: headings, short
  paragraphs, bold, lists, and GFM tables.
- Never include internal reasoning, tool output, tokens, IDs, or delivery instructions
  in the final answer.
