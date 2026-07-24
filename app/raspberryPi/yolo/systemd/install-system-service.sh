#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=smartcore-yolo.service
SERVICE_SRC=/home/phoenix/yolo/systemd/smartcore-yolo.service
ENV_SRC=/home/phoenix/yolo/systemd/smartcore-pi.env
LOCAL_ENV=/home/phoenix/yolo/.smartcore.env
ENV_DST=/etc/smartcore-pi.env
LOG_DIR=/home/phoenix/yolo/logs

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 sudo 运行: sudo bash $0" >&2
  exit 1
fi

install -d -m 700 -o phoenix -g phoenix "${LOG_DIR}"

if [[ -f "${ENV_DST}" ]]; then
  if grep -q '^SMARTCORE_LOG_DIR=' "${ENV_DST}"; then
    sed -i 's|^SMARTCORE_LOG_DIR=.*|SMARTCORE_LOG_DIR=/home/phoenix/yolo/logs|' "${ENV_DST}"
  else
    echo 'SMARTCORE_LOG_DIR=/home/phoenix/yolo/logs' >> "${ENV_DST}"
  fi
  if grep -q '^SMARTCORE_RETENTION_HOURS=' "${ENV_DST}"; then
    sed -i 's|^SMARTCORE_RETENTION_HOURS=.*|SMARTCORE_RETENTION_HOURS=72|' "${ENV_DST}"
  else
    echo 'SMARTCORE_RETENTION_HOURS=72' >> "${ENV_DST}"
  fi
  echo "已更新 ${ENV_DST} 中的 SMARTCORE_LOG_DIR / SMARTCORE_RETENTION_HOURS（保留 token）"
else
  install -m 640 -o root -g phoenix "${ENV_SRC}" "${ENV_DST}"
  echo "已创建 ${ENV_DST}"
fi

install -m 644 "${SERVICE_SRC}" "/etc/systemd/system/${SERVICE_NAME}"

PHOENIX_UID="$(id -u phoenix)"
RUNTIME_DIR="/run/user/${PHOENIX_UID}"
if [[ -d "${RUNTIME_DIR}" ]]; then
  sudo -u phoenix env XDG_RUNTIME_DIR="${RUNTIME_DIR}" \
    systemctl --user disable --now smartcore-yolo.service 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo
systemctl status "${SERVICE_NAME}" --no-pager | head -20
