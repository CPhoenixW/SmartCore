---
name: smartcore
description: Thin OpenClaw bridge to SmartCore agent tools on the server.
---

# SmartCore OpenClaw Skill

Use this skill when the user asks about schedules, reminders, ideas, or SmartCore-managed data.

## Boundaries

- Call `GET /agent/tools` first when tool shape is uncertain.
- Before the first authenticated `/agent/*` command, load the task scope file path supplied in the prompt: `export SMARTCORE_AGENT_SCOPE="$(cat <task-scope-file>)"`. Then use `X-SmartCore-Agent-Scope: $SMARTCORE_AGENT_SCOPE`. Never print, copy, or paste its value.
- Treat `/agent/tools` as the source of truth for tool names, paths, schemas, and aliases.
- Never read SQLite, backups, Docker volumes, or `.env` directly.

## Tool Order

1. Discover tools: `GET /agent/tools`
2. Read/query: `evtQuery`
3. Write directly: `evtCreate`, `evtUpdate`, `evtComplete`, `evtDelete`,
   `ideaCapture`, `ideaToEvt`
4. Return one concise user-facing final answer; the Adapter delivers it to Feishu.

## Media Ideas

- These rules apply only when the forwarded event contains `attachments`. A plain-text
  request keeps the normal schedule, reminder, query, and daily-report behaviour.
- Inspect attachment metadata first. Never read a document or its task-local file path.
  For a document-only message, call `ideaCapture` once per attachment with the filename
  (without its extension) as title, `srcType=media`, and that attachment's `uploadId`.
  Preserve meaningful user text as a short note. Do not call OCR for documents.
- Every image must call `mediaImageOcr` exactly once, including an image with no user text.
  Save the returned `ocrEvidence` for that upload. Use only the OCR results and optional
  user text to decide the Idea. Do not inspect `agentPath` directly.
- After all image OCR calls succeed, call `ideaCapture` with a factual Chinese title,
  every attachment `uploadId`, `srcType=media`, a valid Markdown description of at most
  100 Chinese characters, and an `ocrEvidence` object mapping every image uploadId to the
  evidence returned by its OCR call. Image capture without evidence is invalid and must
  be corrected, never bypassed.
- When images and documents occur together, capture one Idea containing every attachment;
  OCR every image and never read a document. An explicit schedule, reminder, or DDL request
  takes precedence, but image OCR still runs before the requested event operation.
- Do not invent facts, paste raw OCR output, mention internal IDs, or narrate tool use.
- Start the final reply with `# <summary title>`. Keep the body concise; the adapter
  uses that heading only as the Feishu card title and removes it from the card body.

### Existing Idea media jobs

- An `idea_media_edit` event preprocesses one image for an existing Idea. It must never
  call `ideaCapture`, query schedules, or mutate events.
- Call `mediaImageOcr` once with both the supplied `uploadId` and `jobId`.
- On success, create one factual Chinese Markdown summary of at most 100 characters and
  call `ideaMediaJobComplete` once with `jobId`, `summary`, and the returned `ocrEvidence`.
- On failure, call `ideaMediaJobFail` once with a concise error and stop. Never retry OCR.
- The backend job state is authoritative and idempotent. Do not try to bypass or reset it.

The preferred DB paths are `/agent/db/query_events`, `/agent/db/create_event`, and
`/agent/db/update_event`. Until canonical delete enforces user scope, use `/agent/evtDelete`
with both the agent token and signed scope; do not call `/agent/db/delete_event`.

## Query Rules

- Run event queries with the bundled helper; do not construct `curl` commands:
  `python3 skills/smartcore/scripts/query_events.py ...`
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
- This task always produces a Chinese report, regardless of the model's default language.
- Return only the finished report. Never output analysis, filtering lists, tool narration,
  English planning text, raw event rows, IDs, or preambles such as “Now let me”.
- Use only facts from this task's query result. Never reuse a project, blocker, outcome, or
  tomorrow plan remembered from another conversation or date. If a technical detail is not
  recorded, write `记录中未提供技术细节` instead of guessing.

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

📅 **[YYYY年MM月DD日] 工作日报**

### 📝 本日工作概述
> [用 1-2 句话高度概括核心工作内容与状态切换]

### 🚀 今日主要成果与技术进展
- **[模块名称]**
  - **进展**：[具体做成了什么]
  - **技术要点/避坑**：[数据库描述中存在的代码、版本、功能包或踩坑]

### ⚠️ 遇到问题与阻碍 (Blockers)
- **[问题名称]**：[具体阻碍及现象]

### 📅 明日规划
- [针对今日阻碍的下一步行动]
- [记录中已有的其他计划事项]

- Do not mutate events and do not call the daily-summary persistence endpoint.
  The Adapter saves the final answer before delivering it.
- The first character of the final answer must be `📅`. The four `###` headings above must
  each appear exactly once and in the same order. The adapter rejects any other structure.

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
