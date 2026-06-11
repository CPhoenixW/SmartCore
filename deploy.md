# Deploy

## Git

remote: origin
branch: main

## Validation

test: `.venv/bin/python -m pytest`
lint: `.venv/bin/python -m ruff check app tests`

## Server

ssh: server
repo: /opt/smartcore
deploy_dir: /opt/smartcore/deploy
deploy_command: `docker compose up -d --build`
healthcheck: `curl -fsS http://100.65.243.93:8000/healthz`
status: `docker compose ps`
logs: `docker logs --tail 80 deploy-app-1`

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
- docker volumes: smartcore-data, smartcore-backups, caddy-data, caddy-config

## Release Procedure

1. Confirm `test` and `lint` pass locally.
2. Confirm `git status --short` contains only intended files and none from `never_commit`.
3. Commit intended files.
4. Push to `remote` / `branch`.
5. SSH to `server`.
6. In `repo`, verify the server worktree is safe with `git status --short`.
7. Pull fast-forward: `git pull --ff-only origin main`.
8. In `deploy_dir`, run `deploy_command`.
9. Run `status`.
10. Run `healthcheck`.
11. Check `logs` for startup errors.

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
