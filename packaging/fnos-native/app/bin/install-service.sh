#!/bin/sh
set -eu

APP_DIR="/var/apps/xdownload/target"
DATA_DIR="/var/apps/xdownload/data"
DOWNLOAD_DIR="${DATA_DIR}/downloads"
QUEUE_FILE="${DATA_DIR}/queue.json"
SERVICE_FILE="/etc/systemd/system/xdownload.service"

mkdir -p "$DOWNLOAD_DIR"

sed \
  -e "s#__APP_DIR__#${APP_DIR}#g" \
  -e "s#__DOWNLOAD_DIR__#${DOWNLOAD_DIR}#g" \
  -e "s#__QUEUE_FILE__#${QUEUE_FILE}#g" \
  "$APP_DIR/bin/xdownload.service.in" > "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable xdownload.service
systemctl restart xdownload.service
