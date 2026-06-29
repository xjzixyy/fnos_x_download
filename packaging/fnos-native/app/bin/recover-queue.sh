#!/bin/sh
set -eu

APP_DIR="/var/apps/xdownload/target"
DATA_DIR="/var/apps/xdownload/data"
DOWNLOAD_DIR="${XDOWNLOAD_DOWNLOAD_DIR:-${DATA_DIR}/downloads}"
QUEUE_FILE="${XDOWNLOAD_QUEUE_FILE:-${DATA_DIR}/queue.json}"
URL_FILE="${1:-${APP_DIR}/recovery/urls.txt}"

XDOWNLOAD_DOWNLOAD_DIR="$DOWNLOAD_DIR" \
XDOWNLOAD_QUEUE_FILE="$QUEUE_FILE" \
/usr/bin/python3 "$APP_DIR/recovery/recover_queue.py" "$URL_FILE"
