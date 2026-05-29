#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <snapshot.sqlite.gz>" >&2
  echo "Error: backup file must be explicitly specified." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_FILE="$1"

export BACKUP_FILE
python - <<'PY'
import os
from pathlib import Path

from app.backup.snapshot import restore_snapshot
from app.config import get_settings

backup_file = Path(os.environ["BACKUP_FILE"])
settings = get_settings()
saved = restore_snapshot(backup_file, settings.database_path)
if saved is not None:
    print(f"Saved current database to: {saved}")
print(f"Restored database from: {backup_file}")
PY
