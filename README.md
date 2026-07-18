# SmartCore

SmartCore is a personal student secretary system. The v1 goal is to run a server-controlled schedule, assignment, reminder, Feishu bot, internal web panel, and backup workflow with low external API usage.

See the architecture documents in [doc/](./doc/README.md).

## Development

The project uses Python FastAPI, SQLite, SQLAlchemy, APScheduler, and pytest.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Security

Do not commit real secrets, databases, or backups. `passwd.txt`, `.env`, `data/`, and `backups/` are ignored by Git.

## Deployment

Production runs as one Docker Compose project: the FastAPI app, Caddy, the
Cloudflare Tunnel boundary, Cloudflared, and the OpenClaw Adapter. The OpenClaw
Gateway and DERP remain host infrastructure. The web panel is reached over
Tailscale on the app port, not through the tunnel boundary.

Normal changes are pushed to `dev`. The server builds and fully verifies a candidate
while reusing Docker dependency layers:

```bash
ssh server
cd /opt/smartcore-dev
./scripts/deploy_dev.sh
```

After checking the isolated dev app, promote the exact verified image to `main` and
production without rebuilding:

```bash
cd /opt/smartcore
./scripts/promote_prod.sh
```

Promotion fast-forwards `main`, backs up SQLite, switches the app and Adapter images,
checks health, and restores the previous images automatically on failure. To roll back
the latest successful release:

```bash
./scripts/deploy_prod.sh --rollback
```

Python and frontend dependencies are locked in `requirements.lock`,
`requirements-dev.lock`, and `frontend/package-lock.json`. Update them intentionally with
`./scripts/update_dependency_locks.sh`; ordinary source-only builds reuse the cached
dependency layers.

### Prerequisites

- Docker and Docker Compose on the server
- A public domain with DNS pointing to the server (for Caddy HTTPS and the Feishu callback URL)
- Tailscale on your devices for internal access to the web panel at `http://<server-tailscale-ip>:8000/dashboard/`

### Steps

1. Clone the repository on the server (for example under `/opt/smartcore`).
2. Copy the environment template and fill in real values on the server only:

   ```bash
   cp deploy/env.example deploy/.env
   # Edit deploy/.env — never commit this file
   ```

3. Validate the Compose file:

   ```bash
   docker compose -f deploy/docker-compose.yml config
   ```

4. For the initial installation only, build and start:

   ```bash
   docker compose -f deploy/docker-compose.yml up -d --build
   ```

5. Confirm health over Tailscale:

   ```bash
   curl http://<server-tailscale-ip>:8000/healthz
   ```

   Expected response: `{"status":"ok"}`

### Network boundary

- **Public HTTPS (Caddy :443):** only `POST /feishu/event` is forwarded to the app. All other paths return 404.
- **Cloudflare Tunnel (`tunnel-boundary`):** the tunnel daemon on the host should target `http://172.17.0.1:8000` (docker bridge gateway). The boundary Caddy container listens on host `${TUNNEL_BOUNDARY_BIND:-172.17.0.1}:8000` and forwards only `/feishu/event`; other paths return 404. The FastAPI app is **not** bound on `0.0.0.0:8000`.
- **Internal (Tailscale):** set `APP_BIND` in `deploy/.env` to the server's Tailscale IPv4 (see [deploy/env.example](./deploy/env.example)). Then reach the web panel at `/dashboard/*`, plus `/healthz` and other app routes on `http://<server-tailscale-ip>:8000`.

See [doc/04-network-security.md](./doc/04-network-security.md) for the full security model.

## Environment variables

Configuration is loaded from the process environment. In Docker Compose, use `deploy/.env` (copied from [deploy/env.example](./deploy/env.example)).

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_BIND` | No | Host IP for publishing app port `8000` (default `127.0.0.1`; production: server Tailscale IPv4) |
| `TUNNEL_BOUNDARY_BIND` | No | Host IP for tunnel boundary on port `8000` (default `172.17.0.1`, docker bridge gateway) |
| `DOMAIN` | Yes (prod) | Public domain for Caddy HTTPS and the Feishu callback host |
| `CADDY_ADMIN_EMAIL` | Yes (prod) | Email for Let's Encrypt certificate registration |
| `APP_NAME` | No | Application display name (default: `SmartCore`) |
| `DEBUG` | No | Enable debug mode (default: `false`) |
| `DATABASE_URL` | No | SQLite URL (default in Docker: `sqlite:////app/data/smartcore.sqlite`) |
| `FEISHU_APP_ID` | Yes (bot) | Feishu app ID |
| `FEISHU_APP_SECRET` | Yes (bot) | Feishu app secret |
| `FEISHU_VERIFICATION_TOKEN` | Yes (bot) | Event subscription verification token |
| `FEISHU_ENCRYPT_KEY` | If encrypted | Encrypt key when event subscription uses encryption |
| `FEISHU_DEFAULT_CHAT_ID` | Recommended | Default chat ID for proactive reminders |
| `FEISHU_REPLAY_MAX_AGE_SECONDS` | No | Max event timestamp age (default: `300`) |
| `SCHEDULER_ENABLED` | No | Enable background reminder scan and dispatch (default: `false`) |
| `SCHEDULER_INTERVAL_SECONDS` | No | Background scheduler scan interval in seconds (default: `60`) |
| `LLM_PROVIDER` | Yes (NLU) | `tokendance`; identifies the unified natural-language gateway |
| `LLM_API_KEY` | Yes (NLU) | TokenDance API key; keep only in server `deploy/.env` |
| `LLM_BASE_URL` | No | Defaults to `https://tokendance.space/gateway/v1` |
| `LLM_MODEL` | No | Defaults to `deepseek-v4-flash` |
| `LLM_MAX_RETRIES` | No | SDK retry count, default `2`; HTTP request timeout is disabled |
| `DEEPSEEK_API_KEY` | Compatibility | Accepted only as a fallback key when `LLM_API_KEY` is empty |
| `DASHBOARD_BASE_URL` | For cards | Tailscale dashboard base URL used by Feishu card modify links |
| `SEMESTER_START` | No | Semester start date (`YYYY-MM-DD`) for week calculations |
| `BACKUP_DIR` | No | Local backup directory (default: `backups/` or `/app/backups` in Docker) |
| `PI_USER` | For sync | SSH user on the Raspberry Pi |
| `PI_HOST` | For sync | Pi hostname or Tailscale name |
| `PI_BACKUP_DIR` | For sync | Remote backup directory on the Pi |
| `LOCAL_BACKUP_RETENTION_DAYS` | No | Local snapshot retention (default: `30`) |
| `PI_BACKUP_RETENTION_DAYS` | No | Remote snapshot retention (default: `90`) |

For local development without Docker, export variables in your shell or place a `.env` file in the project root. Pydantic Settings reads standard environment variable names (uppercase, as listed above).

**Never commit** `.env`, `passwd.txt`, SSH keys, or real Feishu credentials.

## Natural-language routing

All model requests owned by SmartCore use the centralized client in `app/llm/gateway.py`:

```text
Web event/course natural-language input
  -> POST /api/llm/parse
  -> OpenAI-compatible client
  -> https://tokendance.space/gateway/v1
  -> deepseek-v4-flash
```

The gateway client has no HTTP request time limit. Parsing errors and gateway errors are returned explicitly instead of being silently converted into an empty result.

Feishu events are still forwarded to the separately deployed OpenClaw service when `OPENCLAW_EVENTS_ENDPOINT` is configured. OpenClaw owns its own model runtime, so that external deployment must also be configured to use the same TokenDance base URL and model if Feishu understanding must follow the same route.

## Feishu bot setup

1. Create a custom bot app in the [Feishu Open Platform](https://open.feishu.cn/).
2. Enable bot capability and note the **App ID** and **App Secret**.
3. Under **Event Subscriptions**, set the request URL to:

   ```text
   https://<DOMAIN>/feishu/event
   ```

4. Copy the **Verification Token** into `FEISHU_VERIFICATION_TOKEN`.
5. If the subscription uses encryption, copy the **Encrypt Key** into `FEISHU_ENCRYPT_KEY`.
6. Subscribe to the `im.message.receive_v1` event (or the events your deployment needs).
7. Set `FEISHU_DEFAULT_CHAT_ID` to the chat where proactive reminders should be sent. You can find chat IDs via Feishu API or admin tools.
8. Deploy and verify: Feishu sends a URL verification challenge; the app must respond successfully before events flow.

## Backup and restore

SmartCore keeps SQLite snapshots locally and optionally syncs them to a Raspberry Pi over `rsync` via SSH. See [doc/05-backup-restore.md](./doc/05-backup-restore.md) for the full design.

### Manual backup

From the project root (with the virtualenv active or inside the app container):

```bash
./scripts/backup_now.sh
```

This creates a compressed snapshot named `smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz` under `BACKUP_DIR`, prunes local files older than `LOCAL_BACKUP_RETENTION_DAYS`, and runs rsync to the Pi when `PI_USER`, `PI_HOST`, and `PI_BACKUP_DIR` are configured.

### Scheduled backup

Recommended schedule (host cron on the server):

```text
0 3 * * * cd /opt/smartcore && ./scripts/backup_now.sh
```

Ensure SSH key-based auth to the Pi is configured; do not store private keys in Git.

### Restore

**Stop the app before restoring** to avoid concurrent writes.

```bash
docker compose -f deploy/docker-compose.yml stop app
./scripts/restore_backup.sh /path/to/smartcore-2026-05-29-030000.sqlite.gz
docker compose -f deploy/docker-compose.yml start app
```

The restore script requires an explicit snapshot path; it will not run without one. It saves the current database as `smartcore.sqlite.before-restore` before replacing it.

After restore, check today's plan, timetable, and pending reminders for consistency.
