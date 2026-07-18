#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v npm >/dev/null 2>&1 || {
    echo "npm is required" >&2
    exit 1
}
command -v uv >/dev/null 2>&1 || {
    echo "uv is required" >&2
    exit 1
}

npm install \
    --package-lock-only \
    --ignore-scripts \
    --no-audit \
    --no-fund \
    --prefix frontend

uv pip compile \
    pyproject.toml \
    --output-file requirements.lock \
    --no-annotate \
    --no-header \
    --python-version 3.11 \
    --python-platform x86_64-manylinux_2_28

uv pip compile \
    pyproject.toml \
    --extra dev \
    --output-file requirements-dev.lock \
    --no-annotate \
    --no-header \
    --python-version 3.11 \
    --python-platform x86_64-manylinux_2_28

echo "Updated frontend/package-lock.json, requirements.lock, and requirements-dev.lock"
