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

Production runs as two Docker Compose services: the FastAPI app and Caddy. Caddy is the only public HTTPS entry; the web panel is reached over Tailscale on the app port.

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

4. Build and start:

   ```bash
   docker compose -f deploy/docker-compose.yml up -d --build
   ```

5. Confirm health over Tailscale:

   ```bash
   curl http://<server-tailscale-ip>:8000/healthz
   ```

   Expected response: `{"status":"ok"}`

### Network boundary

- **Public (Caddy :443):** only `POST /feishu/event` is forwarded to the app. All other paths return 404.
- **Internal (Tailscale):** web panel at `/dashboard/*`, plus `/healthz` and other app routes on port `8000`.

See [doc/04-network-security.md](./doc/04-network-security.md) for the full security model.

## Environment variables

Configuration is loaded from the process environment. In Docker Compose, use `deploy/.env` (copied from [deploy/env.example](./deploy/env.example)).

| Variable | Required | Description |
|----------|----------|-------------|
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
| `SEMESTER_START` | No | Semester start date (`YYYY-MM-DD`) for week calculations |
| `BACKUP_DIR` | No | Local backup directory (default: `backups/` or `/app/backups` in Docker) |
| `PI_USER` | For sync | SSH user on the Raspberry Pi |
| `PI_HOST` | For sync | Pi hostname or Tailscale name |
| `PI_BACKUP_DIR` | For sync | Remote backup directory on the Pi |
| `LOCAL_BACKUP_RETENTION_DAYS` | No | Local snapshot retention (default: `30`) |
| `PI_BACKUP_RETENTION_DAYS` | No | Remote snapshot retention (default: `90`) |

For local development without Docker, export variables in your shell or place a `.env` file in the project root. Pydantic Settings reads standard environment variable names (uppercase, as listed above).

**Never commit** `.env`, `passwd.txt`, SSH keys, or real Feishu credentials.

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

### Supported commands

Users can send these text commands to the bot:

| Command | Action |
|---------|--------|
| `今日` | Show today's plan |
| `明日` | Show tomorrow's plan |
| `本周DDL` | List assignments due this week |
| `添加作业 ...` | Add an assignment |
| `添加事项 ...` | Add a life event |
| `完成 ...` | Mark an item complete |
| `帮助` | Show help |

Invalid or unknown input returns the help message. Requests with a bad verification token, signature, or stale timestamp are rejected without running business logic.

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
