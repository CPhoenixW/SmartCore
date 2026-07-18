# Deploy

## Git

remote: origin
branch: main

## Validation

test: `.venv/bin/python -m pytest`
lint: `.venv/bin/python -m ruff check app tests`

## Server

ssh: server
prod_repo: /opt/smartcore
dev_repo: /opt/smartcore-dev
deploy_dir: /opt/smartcore/deploy
deploy_command: `docker compose up -d --build`
healthcheck: `curl -fsS http://100.65.243.93:8000/healthz`
status: `docker compose ps`
logs: `docker logs --tail 80 deploy-app-1`

## OpenClaw

version: 2026.6.5
install: user-local prefix under `/root/.openclaw`
path: `/root/.openclaw/bin`
gateway: `127.0.0.1:18789`
gateway_service: `systemctl --user status openclaw-gateway.service`
gateway_token_file: `/root/.openclaw/smartcore-gateway-token`
smartcore_agent_token_file: `/root/.openclaw/smartcore-agent-api-token`
verify: `openclaw --version`
doctor: `openclaw doctor`
gateway_status: `openclaw gateway status`
feishu_setup: `openclaw channels login --channel feishu`
gateway_restart: `openclaw gateway restart`

OpenClaw is the natural-language and orchestration layer. SmartCore remains the
data, reminder, card, audit, and deployment authority. OpenClaw may call only
SmartCore Agent APIs and Feedback APIs; it must not connect directly to the
SmartCore database file or Docker volumes.

The OpenClaw Gateway remains a host user service. Its SmartCore Adapter is built
from `deploy/adapter.Dockerfile` and managed by the SmartCore Compose project.
Adapter secrets live only in `deploy/adapter.env`; the mounted OpenClaw home and
workspace let the Adapter invoke the host-managed OpenClaw installation without
granting it access to SmartCore data volumes.

## Guardrails

never_commit:
- .env
- deploy/.env
- passwd.txt
- *.sqlite
- data/
- backups/
- timetable.csv
- __pycache__/
- .pytest_cache/
- .ruff_cache/

preserve_on_server:
- /opt/smartcore/deploy/.env
- /opt/smartcore/data
- /opt/smartcore/backups
- /opt/smartcore-dev
- /root/.openclaw
- docker volumes: smartcore-data, smartcore-backups, caddy-data, caddy-config

## Server Development Workflow

Use this workflow when Cursor or another coding agent edits code on the server:

1. SSH to `server`.
2. Work only in `dev_repo` (`/opt/smartcore-dev`), never directly in `prod_repo`.
3. In `dev_repo`, keep `main` current with `git pull --ff-only origin main`.
4. Run validation in `dev_repo`: `.venv/bin/python -m pytest` and `.venv/bin/python -m ruff check app tests`.
5. Commit and push from `dev_repo`.
6. In `prod_repo`, verify `git status --short` is clean.
7. In `prod_repo`, pull fast-forward from `origin/main`.
8. In `deploy_dir`, run `deploy_command`.
9. Run `status`, `healthcheck`, and `logs`.

`prod_repo` is production-only. Uncommitted experiments, Cursor worktrees, and
temporary files belong in `dev_repo`.

## Release Procedure

1. Confirm `test` and `lint` pass locally.
2. Confirm `git status --short` contains only intended files and none from `never_commit`.
3. Commit intended files.
4. Push to `remote` / `branch`.
5. SSH to `server`.
6. In `prod_repo`, verify the server worktree is safe with `git status --short`.
7. Pull fast-forward: `git pull --ff-only origin main`.
8. In `deploy_dir`, run `deploy_command`.
9. Run `status`.
10. Run `healthcheck`.
11. Check `logs` for startup errors.

## OpenClaw First SmartCore Loop

Feishu text messages and card callbacks must flow through OpenClaw when
`OPENCLAW_EVENTS_ENDPOINT` is configured:

```text
Feishu event
  -> SmartCore Feishu Gateway validates and deduplicates
  -> SmartCore forwards a normalized event to OpenClaw
  -> OpenClaw calls SmartCore /agent/db/* APIs
  -> OpenClaw calls SmartCore /agent/feedback/* APIs
  -> SmartCore sends Feishu cards or text
```

SmartCore reminders stay local and reliable:

```text
SmartCore scheduler scans DB every minute
  -> SmartCore sends reminder card
  -> Feishu card action returns to SmartCore Feishu Gateway
  -> SmartCore forwards the action to OpenClaw
  -> OpenClaw decides whether to snooze, complete, modify, or continue the task
```

## Rollback

If deployment fails after a new commit reaches the server:

1. Do not delete Docker volumes or production data.
2. Inspect the previous commit with `git log --oneline -5`.
3. Temporarily return the server to the last known good commit if needed:

```bash
cd /opt/smartcore
git checkout <good_commit_sha>
cd /opt/smartcore/deploy
docker compose up -d --build
curl -fsS http://100.65.243.93:8000/healthz
```

4. Create a normal revert or fix commit on `main` from the local repository to restore branch consistency.
