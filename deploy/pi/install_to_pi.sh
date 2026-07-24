#!/usr/bin/env bash
# Deploy SmartCore Pi integration to ~/yolo on the Pi host (ssh alias Pi).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${ROOT}/app/raspberryPi/yolo"
PI_HOST="${PI_SSH_HOST:-Pi}"
YOLO_DIR="${PI_YOLO_DIR:-/home/phoenix/yolo}"
ENV_FILE="${YOLO_DIR}/.smartcore.env"
SERVER_URL="${SMARTCORE_PI_SERVER_URL:-}"
TOKEN=""

if [[ -f /opt/smartcore/deploy/.env ]]; then
  TOKEN="$(grep -E '^DEVICE_API_TOKEN=' /opt/smartcore/deploy/.env | cut -d= -f2- || true)"
fi

echo "Syncing SmartCore client files to ${PI_HOST}:${YOLO_DIR} ..."
ssh "${PI_HOST}" "mkdir -p ${YOLO_DIR}"
rsync -az \
  --exclude '.smartcore.env' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude 'captures/' \
  --exclude 'known_faces/' \
  --exclude 'logs/' \
  --exclude 'output/' \
  --exclude 'models/*.onnx' \
  --exclude 'yolo*.pt' \
  "${SOURCE_DIR}/" "${PI_HOST}:${YOLO_DIR}/"

if [[ -n "${TOKEN}" && -n "${SERVER_URL}" ]]; then
  ssh "${PI_HOST}" "cat > ${ENV_FILE}" <<EOF
SMARTCORE_BASE_URL=${SERVER_URL}
SMARTCORE_DEVICE_TOKEN=${TOKEN}
SMARTCORE_DEV_ID=pi
SMARTCORE_POST_TIMEOUT=5
EOF
elif ! ssh "${PI_HOST}" "test -f ${ENV_FILE}"; then
  echo "No complete Pi configuration found; create ${ENV_FILE} from .env.example on ${PI_HOST}." >&2
  exit 1
fi

ssh "${PI_HOST}" "mkdir -p ~/.config/systemd/user"
scp "${SOURCE_DIR}/systemd/smartcore-yolo.user.service" \
  "${PI_HOST}:~/.config/systemd/user/smartcore-yolo.service"
ssh "${PI_HOST}" "systemctl --user daemon-reload && systemctl --user enable smartcore-yolo.service && systemctl --user restart smartcore-yolo.service || true"
ssh "${PI_HOST}" "systemctl --user status smartcore-yolo.service --no-pager || true"

echo "Run ping test on Pi:"
ssh "${PI_HOST}" "${YOLO_DIR}/.venv/bin/python ${YOLO_DIR}/smartcore_ping.py || true"
