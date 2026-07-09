# Course, Plan, and Reminder Relations

## Relationship model

```text
appUser
  └─ evtBase
       ├─ planEvt
       │    ├─ remindEvt (start minus 10 minutes)
       │    ├─ remindEvt (end minus 10 minutes)
       │    ├─ ddlPlan ── ddlEvt
       │    └─ coursePlan ── courseEvt
       ├─ ddlEvt
       ├─ courseEvt
       └─ remindEvt
```

`evtBase` remains the common event record. Its supported `evtType` values are `plan`, `ddl`, `course`, and `remind`.

## Semester-based course expansion

A `courseEvt` is a recurring template. It no longer needs a manually entered course end date. The scheduling inputs are:

- `semesterStart`: the first calendar date of the semester and the anchor for week 1.
- `startWeek`: first active teaching week, default 1.
- `endWeek`: last active teaching week, default 16.
- `weekDay`: ISO weekday, Monday=1 through Sunday=7.
- `weekMode`: `all`, `odd`, or `even`.
- `stTime` and `endTime`: local class clock times.

SmartCore finds the Monday of the week containing `semesterStart`, then calculates each occurrence in chronological week order. An occurrence before the semester start date is skipped. The last computed occurrence is retained in the legacy `courseEvt.endDate` field for backward compatibility, but clients should not ask users to enter it.

The `coursePlan` relation records:

- `courseEvtId`: course template.
- `planEvtId`: generated actionable class plan.
- `occurrenceDate`: local class date.
- `sequenceNo`: chronological position in the series.

| Value | Weekday |
|---:|---|
| 1 | Monday / 星期一 |
| 2 | Tuesday / 星期二 |
| 3 | Wednesday / 星期三 |
| 4 | Thursday / 星期四 |
| 5 | Friday / 星期五 |
| 6 | Saturday / 星期六 |
| 7 | Sunday / 星期日 |

## Plan reminders

Every `planEvt`, including manually created plans, DDL-linked plans, and course-generated plans, owns two `remindEvt` records:

1. `plan_start_10m`: ten minutes before the plan starts.
2. `plan_end_10m`: ten minutes before the plan ends.

Reminder rows are stored as `evtBase(evtType='remind')` plus `remindEvt`. They are push-only and are excluded from normal schedule and screen queries. Plan time or duration changes recalculate both reminder trigger times.

## Search behavior

Event and course search supports ordinary text plus temporal terms:

- dates: `2026-09-15`, `2026/09/15`, `2026年9月15日`;
- clock times: `08:00`, `8点`, `8点半`;
- weekdays: `星期二`, `周二`, `Tuesday`;
- relative dates: `今天`, `明天`, `后天`, `昨天`;
- semester and week metadata such as `第2周`.

The update page switches its selected day when the search contains an explicit full date.

## API behavior

### Work API

- `GET /api/evt?date=YYYY-MM-DD&text=08:00` returns matching actionable events for one local day.
- `GET /api/courseEvt?text=星期二` searches course templates and generated occurrence times.
- `POST /api/courseEvt` creates a semester-based course and expands its occurrences.
- `PATCH /api/evt/{courseEvtId}` updates the course and synchronizes its generated plans.
- `POST /api/courseEvt/{courseEvtId}/sync` explicitly reapplies the course template.
- `GET /api/remindEvt` exposes reminders for diagnostics only.

Course creation example:

```json
{
  "courseName": "机器人学",
  "semesterStart": "2026-09-07",
  "weekDay": 2,
  "startWeek": 1,
  "endWeek": 16,
  "weekMode": "all",
  "stTime": "08:00",
  "endTime": "09:40"
}
```

Legacy `stDate` is accepted as an alias for `semesterStart`; legacy `endDate` is accepted only for compatibility.

### OpenClaw

OpenClaw should refresh `GET /agent/tools` after deployment. Tool contract version:

```text
2026-07-09-semester-course-v5
```

Course creation requires `courseName`, `semesterStart`, `weekDay`, `stTime`, and `endTime`; `startWeek` and `endWeek` default to 1 and 16. Chinese and English weekday names and integer values 1–7 are accepted. Agent event queries also match dates, weekdays, and clock times.

## Migration and backfill

On startup SmartCore:

1. Migrates `evtBase` to accept `remind`.
2. Creates `coursePlan` and `remindEvt` when missing.
3. Adds missing reminder relations to existing plans.
4. Expands legacy courses that have no generated plans.
5. Marks completed historical course occurrences done.

Customized individual class plans are not overwritten during ordinary startup or scheduler ticks. Editing the course template or invoking the sync endpoint intentionally reapplies its semester/week schedule.
