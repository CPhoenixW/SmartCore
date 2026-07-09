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

`evtBase` remains the common event record. Its supported `evtType` values are:

- `plan`: an actionable item with an absolute start time and duration.
- `ddl`: a deadline.
- `course`: a recurring course template.
- `remind`: a push-only reminder linked to one plan.

## Course expansion

A `courseEvt` is a template, not one individual class. When it is created or its recurrence fields are updated, SmartCore calculates all matching dates between `stDate` and `endDate` and creates one `planEvt` for each class.

The `coursePlan` relation records:

- `courseEvtId`: the course template.
- `planEvtId`: one generated class plan.
- `occurrenceDate`: the local class date.
- `sequenceNo`: chronological position in the course series.

Weekday values follow ISO convention:

| Value | Weekday |
|---:|---|
| 1 | Monday / 星期一 |
| 2 | Tuesday / 星期二 |
| 3 | Wednesday / 星期三 |
| 4 | Thursday / 星期四 |
| 5 | Friday / 星期五 |
| 6 | Saturday / 星期六 |
| 7 | Sunday / 星期日 |

`weekMode` values are `all`, `odd`, and `even`. If `SEMESTER_START` is configured, odd/even and start/end week calculations are anchored to the week containing that date. Otherwise the course start date is the anchor.

## Plan reminders

Every `planEvt`, including manually created plans, DDL-linked plans, and course-generated plans, owns two `remindEvt` records:

1. `plan_start_10m`: trigger ten minutes before the plan starts.
2. `plan_end_10m`: trigger ten minutes before the plan ends.

Reminder rows are stored as `evtBase(evtType='remind')` plus `remindEvt`. They are not displayed as schedule items. The scheduler reads them and pushes them through the user's selected reminder channel.

When a plan time or duration changes, its reminder trigger times are recalculated. When a plan is cancelled, its pending reminders are cancelled. Fired reminders store `firedAt` and are not sent again.

## API behavior

### Work API

- `GET /api/evt?date=YYYY-MM-DD` returns actionable events for one local day.
- `GET /api/courseEvt` returns course templates with generated occurrence summaries.
- `POST /api/courseEvt` creates a course and expands its occurrences.
- `PATCH /api/evt/{courseEvtId}` updates the course and synchronizes its generated plans.
- `POST /api/courseEvt/{courseEvtId}/sync` explicitly regenerates the course occurrence relation.
- `GET /api/remindEvt` exposes reminders for diagnostics; normal pages do not load this endpoint.

### OpenClaw

OpenClaw should refresh `GET /agent/tools` after deployment. Tool contract version:

```text
2026-07-09-course-reminder-v4
```

Creating a course requires `courseName`, `stDate`, `endDate`, `weekDay`, `stTime`, and `endTime`. Chinese or English weekday names and integer values 1–7 are accepted.

Queries include linked plans by default so a date query returns actual class plans rather than only the course template. Reminder events remain hidden unless `includeReminders=true`.

## Migration and backfill

On startup SmartCore:

1. Migrates the `evtBase` event type constraint to accept `remind`.
2. Creates `coursePlan` and `remindEvt` tables if missing.
3. Adds missing reminder relations to existing plans.
4. Expands legacy courses that do not yet have any generated plans.
5. Marks past generated class occurrences complete so old classes do not appear as overdue work.

Existing customized course occurrences are not overwritten during ordinary startup or scheduler ticks. Explicitly editing the course template or invoking its sync endpoint intentionally reapplies the template schedule.
