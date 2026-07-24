#!/usr/bin/env bash
set -euo pipefail

SRC=/var/lib/smartcore-pi/logs
DST=/home/phoenix/yolo/logs
ENV_FILE=/etc/smartcore-pi.env
SERVICE=/etc/systemd/system/smartcore-yolo.service
SERVICE_SRC=/home/phoenix/yolo/systemd/smartcore-yolo.service

mkdir -p "${DST}"

if [[ -d "${SRC}" ]] && [[ "$(ls -A "${SRC}" 2>/dev/null || true)" ]]; then
  echo "迁移 ${SRC} -> ${DST}"
  rsync -a "${SRC}/" "${DST}/"
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "需要 sudo 更新系统配置并重启服务"
  echo "请运行: sudo bash $0"
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  if grep -q '^SMARTCORE_LOG_DIR=' "${ENV_FILE}"; then
    sed -i 's|^SMARTCORE_LOG_DIR=.*|SMARTCORE_LOG_DIR=/home/phoenix/yolo/logs|' "${ENV_FILE}"
  else
    echo 'SMARTCORE_LOG_DIR=/home/phoenix/yolo/logs' >> "${ENV_FILE}"
  fi
  if grep -q '^SMARTCORE_RETENTION_HOURS=' "${ENV_FILE}"; then
    sed -i 's|^SMARTCORE_RETENTION_HOURS=.*|SMARTCORE_RETENTION_HOURS=72|' "${ENV_FILE}"
  else
    echo 'SMARTCORE_RETENTION_HOURS=72' >> "${ENV_FILE}"
  fi
else
  install -m 640 -o root -g phoenix /home/phoenix/yolo/systemd/smartcore-pi.env "${ENV_FILE}"
fi

install -m 644 "${SERVICE_SRC}" "${SERVICE}"
systemctl daemon-reload
systemctl restart smartcore-yolo.service

echo
systemctl status smartcore-yolo.service --no-pager | head -20
