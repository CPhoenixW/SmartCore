#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${REPO_ROOT}/openclaw/adapter/adapter.py"
TARGET_DIR="${OPENCLAW_ADAPTER_DIR:-/opt/smartcore-openclaw-adapter}"
TARGET="${TARGET_DIR}/adapter.py"

if [[ ! -f "${SOURCE}" ]]; then
  echo "missing adapter source: ${SOURCE}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"
install -m 755 "${SOURCE}" "${TARGET}"
echo "deployed ${SOURCE} -> ${TARGET}"
