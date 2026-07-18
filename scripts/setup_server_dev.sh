#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_ROOT="${SMARTCORE_DEPLOY_ROOT:-/opt/smartcore}"
DEV_ROOT="${SMARTCORE_DEV_ROOT:-/opt/smartcore-dev}"

die() {
    printf '[smartcore-dev-setup] ERROR: %s\n' "$*" >&2
    exit 1
}

[[ "$ROOT" == "$EXPECTED_ROOT" ]] || die "run this script from $EXPECTED_ROOT (got $ROOT)"
[[ "$(git -C "$ROOT" branch --show-current)" == "main" ]] || die "production checkout must be on main"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || die "production checkout has uncommitted files"
[[ ! -e "$DEV_ROOT" ]] || die "target already exists: $DEV_ROOT"

git -C "$ROOT" fetch --prune origin main dev
if git -C "$ROOT" show-ref --verify --quiet refs/heads/dev; then
    git -C "$ROOT" worktree add "$DEV_ROOT" dev
else
    git -C "$ROOT" worktree add --track -b dev "$DEV_ROOT" origin/dev
fi

printf '[smartcore-dev-setup] created %s on dev\n' "$DEV_ROOT"
