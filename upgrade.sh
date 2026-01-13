#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/quail"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: upgrade.sh must be run as root." >&2
  exit 1
fi

if [[ "${SCRIPT_DIR}" != "${INSTALL_DIR}" ]]; then
  if [[ ! -d "${INSTALL_DIR}" ]]; then
    echo "ERROR: expected Quail repo at ${INSTALL_DIR}." >&2
    echo "TODO: clone this repository to ${INSTALL_DIR} before running upgrade." >&2
    exit 1
  fi
fi

if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
  python3 -m venv "${INSTALL_DIR}/venv"
fi

if [[ -f /etc/quail/config.env ]]; then
  # shellcheck disable=SC1091
  set -a
  source /etc/quail/config.env
  set +a
fi
if [[ -z "${QUAIL_DOMAINS:-}" ]]; then
  echo "WARNING: QUAIL_DOMAINS is not set in /etc/quail/config.env." >&2
  echo "Upgrades will continue, but new installs require this value to be configured." >&2
fi

if [[ "${QUAIL_RESET_PIN:-false}" == "true" ]]; then
  if [[ -z "${QUAIL_ADMIN_PIN:-}" ]]; then
    echo "NOTICE: QUAIL_RESET_PIN is true, but QUAIL_ADMIN_PIN is not set." >&2
    echo "Set QUAIL_ADMIN_PIN in /etc/quail/config.env to reset the admin PIN." >&2
  elif [[ ! "${QUAIL_ADMIN_PIN}" =~ ^[0-9]+$ ]] || [[ ${#QUAIL_ADMIN_PIN} -lt 4 ]] || [[ ${#QUAIL_ADMIN_PIN} -gt 9 ]]; then
    echo "NOTICE: QUAIL_ADMIN_PIN must be 4-9 digits to reset the admin PIN." >&2
  else
    "${INSTALL_DIR}/venv/bin/python" - <<'PY'
import os

from quail import db, settings
from quail.security import hash_pin

pin = os.getenv("QUAIL_ADMIN_PIN", "")
db_path = settings.get_settings().db_path
db.init_db(db_path)
if pin:
    db.set_setting(db_path, "admin_pin_hash", hash_pin(pin))
PY
    echo "NOTICE: Admin PIN updated from QUAIL_ADMIN_PIN." >&2
  fi
fi

"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

systemctl daemon-reload
systemctl restart quail.service
systemctl restart quail-purge.timer

echo "Quail upgrade complete."
