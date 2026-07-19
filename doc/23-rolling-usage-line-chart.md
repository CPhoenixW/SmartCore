# Rolling device usage line chart

## Acceptance criteria

- Device usage shows the latest 12 hourly buckets, including the previous date
  when the window crosses midnight.
- The chart is a line with visible keyboard-focusable points; each point exposes
  its hour range and usage minutes.
- Summary totals and peak time describe the same rolling 12-hour window.
- The existing today endpoint remains compatible.

## API and data

- Add `GET /api/devState/usage/recent?devId=...&timezone=...&hours=12`.
- The response contains ordered `points` with `startAt`, `endAt`, and `minutes`,
  plus `windowStart`, `windowEnd`, totals, peak point, confidence, and samples.
- No schema or stored-data changes.

## Validation and rollback

- Test a rolling window that crosses midnight and the legacy today response.
- Test line-point positioning and the frontend API request.
- Run Ruff, pytest, Vitest, frontend build, `/healthz`, and a production
  read-only API smoke check. Browser checks remain excluded.
- Roll back by redeploying the previous image.
