# Weather forecast and scheduler

## Acceptance criteria

- SmartCore refreshes a Qiantang District, Hangzhou forecast from Open-Meteo every
  30 minutes and keeps the latest successful forecast when the provider is
  temporarily unavailable.
- Authenticated users can read the cached next 24 hours from `GET /api/weather`.
- Overview shows a compact current condition and selected points from the next
  24 hours, with loading, empty, stale, and error states.
- At 22:00 Asia/Shanghai, every active user with an active primary Feishu binding
  receives one deduplicated next-day weather message.
- Daily summaries are generated and delivered at 23:59 Asia/Shanghai.

## Design

Weather retrieval is deterministic integration work, so the application
scheduler calls Open-Meteo directly rather than spending an OpenClaw model
request every 30 minutes. OpenClaw remains responsible for natural-language
event work and daily summaries.

`weatherForecast` stores one global normalized snapshot. Failed refreshes record
an error without deleting the last good payload. The browser endpoint is
authenticated but the forecast itself is shared, because it contains no user
data. The 22:00 job explicitly targets Feishu and does not depend on the user's
screen-reminder preference.

Configuration:

- `WEATHER_ENABLED`
- `WEATHER_REFRESH_MINUTES`
- `WEATHER_DAILY_HOUR`
- `WEATHER_DAILY_MINUTE`
- `WEATHER_TIMEZONE`
- `WEATHER_LOCATION_NAME`
- `WEATHER_LATITUDE`
- `WEATHER_LONGITUDE`
- `WEATHER_API_URL`
- `DAILY_SUMMARY_MINUTE`

## Migration, security, and rollback

SQLAlchemy creates the additive `weatherForecast` table. Existing rows and
authentication data are unchanged. The external request contains only fixed
location coordinates and no credentials or user data.

Rollback disables `WEATHER_ENABLED`, restores the previous image, and sets the
daily summary hour/minute back to the prior values. The additive cache table can
remain safely.

## Validation

- Unit tests cover Open-Meteo normalization, stale-cache preservation, scheduler
  registration, deduplicated Feishu delivery, and authenticated API access.
- Ruff, backend pytest, Vitest, frontend build, container health, and
  non-destructive production weather/API checks are required.
