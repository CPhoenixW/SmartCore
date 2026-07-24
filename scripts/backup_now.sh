#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python - <<'PY'
from app.server.backup.snapshot import run_local_backup
from app.server.backup.sync_to_pi import run_sync

archive = run_local_backup()
print(f"Created local snapshot: {archive}")
run_sync()
print("Synced backups to Raspberry Pi")
PY
