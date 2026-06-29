#!/bin/sh
set -eu

systemctl stop xdownload.service 2>/dev/null || true
systemctl disable xdownload.service 2>/dev/null || true
rm -f /etc/systemd/system/xdownload.service
systemctl daemon-reload
