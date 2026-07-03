#!/usr/bin/env bash
# Deploy SmartCore Pi integration to ~/yolo on the Pi host (ssh alias Pi).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PI_HOST="${PI_SSH_HOST:-Pi}"
YOLO_DIR="${PI_YOLO_DIR:-/home/phoenix/yolo}"
ENV_FILE="${YOLO_DIR}/.smartcore.env"
TOKEN=""

if [[ -f /opt/smartcore/deploy/.env ]]; then
  TOKEN="$(grep -E '^DEVICE_API_TOKEN=' /opt/smartcore/deploy/.env | cut -d= -f2- || true)"
fi

echo "Syncing SmartCore client files to ${PI_HOST}:${YOLO_DIR} ..."
ssh "${PI_HOST}" "mkdir -p ${YOLO_DIR}"
scp "${ROOT}/deploy/pi/smartcore_client.py" "${PI_HOST}:${YOLO_DIR}/smartcore_client.py"
scp "${ROOT}/deploy/pi/smartcore_ping.py" "${PI_HOST}:${YOLO_DIR}/smartcore_ping.py"

ssh "${PI_HOST}" "cat > ${ENV_FILE}" <<EOF
SMARTCORE_BASE_URL=http://100.65.243.93:8000
SMARTCORE_DEVICE_TOKEN=${TOKEN}
SMARTCORE_DEV_ID=pi
SMARTCORE_POST_TIMEOUT=5
EOF

ssh "${PI_HOST}" "grep -q 'smartcore_client' ${YOLO_DIR}/detect_usb.py" 2>/dev/null || \
  ssh "${PI_HOST}" "python3 - <<'PY'
from pathlib import Path
path = Path('${YOLO_DIR}/detect_usb.py')
text = path.read_text(encoding='utf-8')
needle = 'from smartcore_client import postDevState'
if needle not in text:
    insert = '\nfrom smartcore_client import postDevState\n'
    if 'def main' in text:
        text = text.replace('def main', insert + 'def main', 1)
    else:
        text = insert + text
    marker = '# smartcore: post state each loop'
    if marker not in text:
        text = text.replace(
            'while True:',
            'while True:\\n        # smartcore: post state each loop\\n        try:\\n            postDevState(status)\\n        except Exception:\\n            pass',
            1,
        )
    path.write_text(text, encoding='utf-8')
PY"

ssh "${PI_HOST}" "mkdir -p ~/.config/systemd/user"
scp "${ROOT}/deploy/pi/smartcore-yolo.service" "${PI_HOST}:~/.config/systemd/user/smartcore-yolo.service"
ssh "${PI_HOST}" "systemctl --user daemon-reload && systemctl --user enable smartcore-yolo.service && systemctl --user restart smartcore-yolo.service || true"
ssh "${PI_HOST}" "systemctl --user status smartcore-yolo.service --no-pager || true"

echo "Run ping test on Pi:"
ssh "${PI_HOST}" "${YOLO_DIR}/.venv/bin/python ${YOLO_DIR}/smartcore_ping.py || true"
