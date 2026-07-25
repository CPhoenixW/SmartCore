# SmartCore Agent Guide

This file is the fast entry point for coding agents. Read it before changing the repository,
then open the relevant document from `docs/README.md`.

## System In One Minute

SmartCore is a server-authoritative personal work system:

```text
Feishu -> public callback -> Server -> OpenClaw Adapter
Pi / Vue / Phone Screen ------------> Server API or WebSocket
Server scheduler -------------------> Screen or Feishu
```

- `app/server` owns SQLite, authorization, business rules, scheduling, integrations, and Web.
- `app/raspberryPi/yolo` is an outbound-only recognition/status client.
- `app/computer/macos` is the headless macOS usage monitor and local offline queue.
- `frontend` is the Vue workbench served at `/work` after build.
- `openclaw` contains the Adapter and SmartCore skill; it never reads the database directly.

The Server is the only database writer. Clients must not import `app.server` or select their own
data owner.

## Source Of Truth

Use this precedence when information disagrees:

1. Executable tests and the route/model implementation.
2. `GET /agent/tools` from the assembled application for the deployed Agent contract.
3. Current domain documents under `docs/`.
4. `CHANGELOG.md`, `docs/delivery-history.md`, and Git history for rationale only.

Do not implement from an old commit, acceptance note, or compatibility alias without checking the
current route registration in `app/server/main.py`.

## Task Map

| Task | Primary code | Focused tests |
|---|---|---|
| App assembly/config | `app/server/main.py`, `app/server/config.py` | `tests/smoke/test_health_and_layout.py` |
| Login/admin/ownership | `app/server/auth/`, `api/auth_routes.py`, `api/admin_routes.py` | `tests/unit/test_auth.py`, `tests/api/test_auth_users.py` |
| Events/relations | `new_core/models.py`, `event_relations.py`, `crud.py`, `api/routes.py` | `tests/unit/test_event_relations.py`, `tests/unit/test_event_search_time.py` |
| Reminders/scheduler | `new_core/reminder_service.py`, `notify.py`, `scheduler/` | `tests/unit/test_event_relations.py`, `tests/contract/test_agent_api.py` |
| Feishu | `app/server/feishu/`, `api/admin_routes.py` | `tests/api/test_feishu_*.py`, `tests/unit/test_feishu_cards.py` |
| OpenClaw/Agent API | `app/server/agent/`, `openclaw/adapter/`, `openclaw/skills/` | `tests/contract/test_agent_api.py`, `tests/unit/test_openclaw_adapter.py` |
| Idea/media | `api/idea_media_routes.py`, `api/routes.py`, `new_core/crud.py` | `tests/api/test_ideas.py`, `tests/contract/test_agent_api.py` |
| User devices/Pi | `user_device/`, `device/`, `app/raspberryPi/yolo/` | `tests/api/test_devices.py`, `tests/unit/test_device_state.py` |
| Phone screen | `screen/` | `tests/api/test_devices.py`, `tests/api/test_feishu_ingress.py` |
| Daily summary/weather | `new_core/daily_summary_service.py`, `weather/`, `scheduler/` | `tests/api/test_reports_weather.py` |
| Schema/migrations | `db/sql/`, `db/session.py`, startup compatibility | `tests/migrations/test_schema_migrations.py` |
| Vue workbench | `frontend/src/views`, `components`, `api` | matching files under `frontend/tests/` |
| Deploy/backup | `deploy/`, `scripts/`, `deploy.md` | local checks plus candidate health validation |

## Invariants

- Every user-owned read and write derives `userId` from a verified browser session, device token,
  Feishu binding, or Agent scope. Ignore caller-supplied ownership fields.
- Ordinary users operate only on themselves. Admin active-user switching preserves the real actor
  in the signed session and audit log.
- Event types are `plan`, `ddl`, `course`, and `remind`. Subtype ownership comes from `evtBase`.
- A Plan owns start-minus-10-minute and end-minus-10-minute push reminders.
- A DDL may own multiple Plans and standalone reminders. Cross-user relations are invalid.
- Clear, authorized Agent requests execute directly. Queries and writes must be user-scoped.
- Feishu replies use the bot/chat that authenticated the inbound event; never fall back across
  users.
- Media files remain private and owner-scoped. Documents are storage-only; images are staged into
  the isolated OpenClaw workspace for native multimodal analysis.
- The scheduler remains deterministic and independent from OpenClaw availability.
- Public ingress is only `POST /feishu/event`; internal surfaces rely on the Tailscale boundary.

## Compatibility Hazards

- `app/server/main.py` registers several Agent routers with overlapping paths. Registration order
  determines which `/agent/tools`, `/agent/db/*`, and legacy alias handler runs. Test the assembled
  app before removing or reordering routers.
- In the assembled app, relation query/create/update routes are scope-protected, but
  `/agent/db/delete_event` first resolves to the token-only v2 router. Treat this as a known
  security debt; do not copy that pattern into new endpoints.
- Modern paths are `/agent/db/*` and `/agent/feedback/*`; `evtQuery`, `evtCreate`, `evtUpdate`,
  `sendText`, and similar names are compatibility aliases.
- Both `lifeDevice` and the older operational `device` records exist. Generic pairing/dispatch and
  Pi state/photo flows touch different parts of this boundary.
- `relation_compat.py` and startup relation maintenance protect existing databases. Do not remove
  them without a migration and production-data compatibility proof.
- Browser auth currently uses an HMAC-signed Cookie containing active and actor IDs. A
  `userSession` model exists but is not the request-authentication authority.
- Pi photo Server/Web endpoints are internal-network routes and do not all declare a browser
  session dependency. Do not expose them publicly or describe them as owner-authenticated.

More detail is in `docs/api-contracts.md` and `docs/decisions.md`.

## Validation

Use risk-proportional checks. The normal full set is:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app/server tests
cd frontend && npm test && npm run build
```

Run the narrowest relevant backend and frontend tests while iterating, then expand when changing
shared models, ownership, route assembly, scheduling, or contracts. A deployable change must also
pass candidate container startup and `/healthz` as described in `deploy.md`.

Backend tests are grouped under `tests/unit`, `tests/api`, `tests/contract`, `tests/migrations`, and
`tests/smoke`. The same groups are registered as strict pytest markers, so focused runs may use
commands such as `.venv/bin/pytest -q -m contract`.

## Safety

- Never commit `.env`, tokens, databases, backups, attachments, captures, face samples, logs, or
  model weights.
- Never reset or replace production data without explicit user authorization. Schema work must
  preserve current records or include an explicit migration and rollback analysis.
- Do not edit `/opt/smartcore` directly or deploy unless the task explicitly includes deployment.
- Do not bypass the `dev` candidate and `promote_prod.sh` workflow for production.
- Preserve unrelated worktree changes and avoid destructive Git operations.

## Documentation

Keep current facts in the existing domain document. Do not add a permanent document for every
feature or PR. Record a new lasting architectural choice in `docs/decisions.md` and a concise
delivered milestone in `docs/delivery-history.md`; detailed discussion belongs in the PR and Git
history.
