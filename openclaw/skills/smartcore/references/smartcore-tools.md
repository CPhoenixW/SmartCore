# SmartCore Tool Contract for OpenClaw

Always prefer the live contract from `GET /agent/tools`, but use this file for exact request shapes and field meanings. All calls must include:

```http
X-SmartCore-Agent-Token: <contents of /root/.openclaw/smartcore-agent-api-token>
Content-Type: application/json
```

Base URL in production is normally `http://100.65.243.93:8000` from OpenClaw.

## Shared Rules

- Do not put `user_id`, `chat_id`, `timezone`, `start_time`, or `end_time` at the top level unless the endpoint schema says so.
- For relative dates, compute explicit ISO-8601 ranges using the forwarded event's `request.now` and `request.timezone`.
- Preferred time filter shape is `filter.time_range.start` and `filter.time_range.end`.
- `filter.start_time` and `filter.end_time` are accepted only as a legacy fallback; do not prefer them.
- Use `source_event_id` with the forwarded event id, for example `feishu:om_xxx`.
- Use `raw_text` with the original user text.
- Writes return `pending_confirmation`; do not say a write has been applied until SmartCore confirms/applies it.

## Public Event Types

Use only these `event_type` values:

- `course`: class/course instance.
- `schedule`: life schedule item with a start time.
- `deadline`: assignment or DDL.
- `plan`: planned work block.
- `all`: query only; never use for create/update/delete event payloads.

## Tool Discovery

### GET /agent/tools

Use when the current session may not know the live contract.

Request body: none.

Response shape:

```json
{
  "tools": [
    {
      "name": "query_events",
      "endpoint": "/agent/db/query_events",
      "method": "POST",
      "risk": "read",
      "confirmation_required": false,
      "input_schema": {}
    }
  ]
}
```

## Database Tools

### POST /agent/db/query_events

Use for all schedule, course, assignment, deadline, and life-event lookups.

Request body:

```json
{
  "filter": {
    "event_type": "all",
    "status": ["pending", "active"],
    "time_range": {
      "start": "2026-06-15T00:00:00+08:00",
      "end": "2026-06-16T00:00:00+08:00"
    },
    "keyword": "optional text",
    "limit": 20
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "我礼拜一有什么课？"
}
```

Fields:

- `filter.event_type`: `all`, `course`, `schedule`, `deadline`, or `plan`. Default intent should be `all` unless user asks specifically for classes/DDL/etc.
- `filter.status`: usually `["pending", "active"]`; omit only when you intentionally want SmartCore defaults.
- `filter.time_range.start`: inclusive ISO-8601 lower bound.
- `filter.time_range.end`: exclusive-ish ISO-8601 upper bound for day/week windows; use next day at `00:00` for a single local day.
- `filter.keyword`: optional case-insensitive text match over title/type/status/time/location.
- `filter.limit`: optional max result count; SmartCore caps at 50.
- `source_event_id`: normalized incoming event id.
- `raw_text`: original user utterance.

Response body:

```json
{
  "ok": true,
  "action": "query_event",
  "status": "applied",
  "data": {
    "events": [
      {
        "ref": "c1",
        "event_type": "course",
        "title": "Linux系统及应用",
        "status": "active",
        "start_at": "2026-06-15T08:05:00+08:00",
        "end_at": "2026-06-15T10:00:00+08:00",
        "time_label": "2026-06-15 08:05-10:00",
        "location": "optional room"
      }
    ]
  },
  "errors": []
}
```

Important:

- The `ref` values (`c1`, `c2`, ...) are temporary candidate references for the same query filter. If you want to update/delete a result using `refs`, repeat the exact same `filter` inside the selector.
- If a query returns many unrelated results, tighten `event_type`, `time_range`, or `keyword`; do not guess.
- For user-facing results, normally call `send_query_result_card` with `data.events`.

### POST /agent/db/create_event

Use for new events. SmartCore creates a pending operation rather than directly applying writes.

Request body:

```json
{
  "payload": {
    "event": {
      "event_type": "schedule",
      "title": "做数据库 PPT",
      "start_at": "2026-06-15T20:00:00+08:00",
      "end_at": "2026-06-15T21:00:00+08:00",
      "location": "optional place",
      "notes": "optional notes"
    }
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "周一晚上八点提醒我做数据库 PPT"
}
```

Fields:

- `payload.event.event_type`: required; one of `course`, `schedule`, `deadline`, `plan`.
- `payload.event.title`: required.
- `payload.event.start_at`: required for normal timed events. For an unscheduled schedule/deadline, set `unscheduled: true` and omit `start_at`.
- `payload.event.end_at`: optional; useful for `course` and `plan` blocks.
- `payload.event.location`: optional, mostly useful for courses.
- `payload.event.notes`: optional.
- `payload.event.unscheduled`: optional boolean, only when the user explicitly wants an item without a time.

Response body:

```json
{
  "ok": true,
  "action": "create_event",
  "status": "pending_confirmation",
  "operation_id": 123,
  "data": {"preview": {}}
}
```

After this, tell the user SmartCore has prepared a confirmation. Do not claim it is saved until confirmed.

### POST /agent/db/update_event

Use for changes to title, time, notes, status, or similar fields. If the target is ambiguous, query first.

Preferred selector by known id:

```json
{
  "payload": {
    "selector": {
      "event_type": "schedule",
      "id": 42
    },
    "patch": {
      "title": "做数据库 PPT 终稿",
      "start_at": "2026-06-15T20:30:00+08:00",
      "end_at": "2026-06-15T21:30:00+08:00",
      "notes": "optional new notes"
    }
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "把数据库 PPT 改到八点半"
}
```

Selector by query result `ref`:

```json
{
  "payload": {
    "selector": {
      "filter": {
        "event_type": "schedule",
        "status": ["pending", "active"],
        "time_range": {
          "start": "2026-06-15T00:00:00+08:00",
          "end": "2026-06-16T00:00:00+08:00"
        },
        "keyword": "数据库 PPT",
        "limit": 10
      },
      "refs": ["c1"]
    },
    "patch": {
      "start_at": "2026-06-15T20:30:00+08:00"
    }
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "把数据库 PPT 改到八点半"
}
```

Fields:

- `payload.selector.event_type` plus `payload.selector.id`: use when you know a stable numeric id.
- `payload.selector.filter`: the exact filter used to produce `ref` candidates.
- `payload.selector.refs`: for update, exactly one ref is required.
- `payload.patch.title`: optional new title.
- `payload.patch.start_at`: optional new start/due time.
- `payload.patch.end_at`: optional new end time.
- `payload.patch.notes`: optional notes.
- `payload.patch.status`: optional status such as `done` or `cancelled` when supported by the target type.

Response body is `pending_confirmation` with an `operation_id`.

### POST /agent/db/delete_event

Use for cancel/delete operations. Query and clarify first unless the target is exact.

By known id:

```json
{
  "payload": {
    "selector": {
      "event_type": "schedule",
      "id": 42
    }
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "取消周一晚上的数据库 PPT"
}
```

By refs, multiple allowed:

```json
{
  "payload": {
    "selector": {
      "filter": {
        "event_type": "schedule",
        "status": ["pending", "active"],
        "time_range": {
          "start": "2026-06-15T00:00:00+08:00",
          "end": "2026-06-16T00:00:00+08:00"
        },
        "keyword": "数据库 PPT",
        "limit": 10
      },
      "refs": ["c1"]
    }
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "取消数据库 PPT"
}
```

Response body is `pending_confirmation` with an `operation_id`.

## Feedback Tools

### POST /agent/feedback/send_text

Use for short clarification questions, status updates, or fallback replies.

Request body:

```json
{
  "target": {"chat_id": "oc_xxx"},
  "text": "你是想改哪一个事项？"
}
```

### POST /agent/feedback/send_query_result_card

Use after `query_events` when presenting event lists.

Request body:

```json
{
  "target": {"chat_id": "oc_xxx"},
  "data": {
    "events": [
      {
        "event_type": "course",
        "title": "Linux系统及应用",
        "time_label": "2026-06-15 08:05-10:00",
        "location": "实验楼 302"
      }
    ]
  }
}
```

Use exactly the `events` list returned by `query_events` when possible.

### POST /agent/feedback/send_operation_success_card

Use only after SmartCore reports a write has been applied, not when it merely returns `pending_confirmation`.

Request body:

```json
{
  "target": {"chat_id": "oc_xxx"},
  "data": {
    "action_name": "create_event",
    "payload": {
      "action": "create_event",
      "payload": {
        "event": {
          "event_type": "schedule",
          "title": "做数据库 PPT"
        }
      }
    }
  }
}
```

### POST /agent/feedback/send_reminder_card

Usually SmartCore's scheduler sends reminder cards itself. Use this only when OpenClaw intentionally asks SmartCore to render an actionable reminder card.

Request body:

```json
{
  "target": {"chat_id": "oc_xxx"},
  "data": {
    "title": "做数据库 PPT",
    "event_type": "schedule",
    "scheduled_label": "2026-06-15 20:00",
    "minutes_until": 30,
    "notes": "optional notes",
    "event_id": 42
  }
}
```

## Common End-to-End Patterns

### Query tomorrow's classes

1. Compute tomorrow's local day range.
2. Call `query_events`:

```json
{
  "filter": {
    "event_type": "course",
    "status": ["pending", "active"],
    "time_range": {
      "start": "2026-06-15T00:00:00+08:00",
      "end": "2026-06-16T00:00:00+08:00"
    },
    "limit": 20
  },
  "source_event_id": "feishu:om_xxx",
  "raw_text": "我礼拜一有什么课？"
}
```

3. If events exist, call `send_query_result_card`. If none exist, call `send_text` with a concise empty-result reply.

### Modify an ambiguous item

1. Query candidates with time range and keyword.
2. If exactly one likely candidate is returned, call `update_event` using `selector.filter` plus `refs: ["c1"]`.
3. If multiple plausible candidates are returned, call `send_text` to ask which one.

## Safety Rules

- SmartCore is the source of truth for data and Feishu cards.
- Never access SQLite, Docker volumes, backups, or `.env` files directly.
- Do not invent event ids. Use numeric ids only if SmartCore returned them; otherwise use `refs` with the original query `filter`.
- Do not claim a write is complete when SmartCore returns `pending_confirmation`.
- Clarify before destructive actions when more than one candidate could match.
