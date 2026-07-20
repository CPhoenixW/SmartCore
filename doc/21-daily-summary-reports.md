# Daily summary reports

## Acceptance criteria

- At 23:59 Asia/Shanghai every day, the server scheduler dispatches one OpenClaw
  daily-summary event for each active SmartCore user with an active primary
  Feishu binding.
- OpenClaw queries that user's events for the report date without filtering by
  status, pays particular attention to each event description, and returns a
  concise Markdown summary of completed work, unfinished work, reflections, and
  useful next actions.
- The Adapter persists the successful final answer before sending it to the
  scoped Feishu chat.
- A signed-in user can view only their own reports at
  `/work/daily-summary`, move between dates, select a date, and search report
  content.
- OpenClaw has a scoped completion endpoint that marks an owned event `done` and
  appends a completion reflection to its description without replacing existing
  context.
- Dispatch retries and duplicate scheduler calls do not create duplicate daily
  report records or duplicate completion notes.

## Data model and migration

Add `dailySummary` with a unique `(userId, reportDate)` key, report content,
generation status, error text, and timestamps. Startup uses
`CREATE TABLE IF NOT EXISTS`; existing event and user data is unchanged.

## API contracts

- `GET /api/daily-summaries?date=YYYY-MM-DD&text=...`
  returns the authenticated user's matching reports.
- `POST /agent/daily-summary` accepts `{reportDate, content, stat}` from the
  Adapter and is protected by both the agent token and signed user/bot/chat
  scope.
- `POST /agent/db/complete_event` accepts
  `{evtId, summary}` and appends `完成总结：...` to the owned event
  description while marking it done.

## Scheduler and delivery

The existing in-process APScheduler remains the scheduling authority. A cron job
at 23:59 Asia/Shanghai creates or reuses a queued report row and forwards a
synthetic, scoped event to the configured OpenClaw Adapter. The Adapter invokes
OpenClaw, saves a successful result through SmartCore, then sends the same text
to Feishu. Users without an active primary binding are skipped.

The 23:59 job is controlled by:

- `DAILY_SUMMARY_ENABLED`
- `DAILY_SUMMARY_HOUR`
- `DAILY_SUMMARY_MINUTE`
- `DAILY_SUMMARY_TIMEZONE`

## Security boundaries

- Scheduler scopes are signed server-side and identify exactly one SmartCore
  user, bot, and Feishu chat.
- Report reads use the browser session user ID.
- Report writes and completion writes reject cross-user event IDs.
- Tokens, bot credentials, chat IDs, and scope values are never returned to the
  frontend or written to logs.
- OpenClaw receives no direct database or Docker-volume access.

## Failure and rollback

Rejected Adapter dispatches mark the report `failed`. OpenClaw or persistence
failure sends the existing generic failure reply and leaves no completed report.
The frontend distinguishes missing, queued, failed, and completed states.

Rollback disables `DAILY_SUMMARY_ENABLED` and deploys the previous images. The
new table is additive and may remain unused; no existing records need reversal.

## Test matrix

- Scheduler registration, 23:59 timezone, per-user primary binding selection,
  deduplication, and dispatch failure.
- Adapter success persists before Feishu delivery; Adapter failure marks the
  report failed.
- Normal-user report read, search, and cross-user isolation.
- Completion reflection append, idempotency, status change, and cross-user
  rejection.
- OpenClaw skill wording and daily-summary prompt contract.
- Ruff, full pytest, Vitest, frontend build, candidate health, production
  `/healthz`, OpenAPI routes, configured cron job, and non-destructive report
  read.
