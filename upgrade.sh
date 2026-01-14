#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/quail"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE_INTERACTIVE=0
FORCE_NON_INTERACTIVE=0

for arg in "$@"; do
  case "${arg}" in
    --interactive)
      FORCE_INTERACTIVE=1
      ;;
    --non-interactive)
      FORCE_NON_INTERACTIVE=1
      ;;
    *)
      echo "ERROR: unknown option ${arg}" >&2
      exit 1
      ;;
  esac
done

INTERACTIVE=0
if [[ ${FORCE_NON_INTERACTIVE} -eq 1 ]]; then
  INTERACTIVE=0
elif [[ ${FORCE_INTERACTIVE} -eq 1 ]]; then
  INTERACTIVE=1
elif [[ -t 0 && -z "${CI:-}" ]]; then
  INTERACTIVE=1
fi

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\/&|]/\\&/g'
}

set_env_var() {
  local key="$1"
  local value="$2"
  local file="/etc/quail/config.env"
  local escaped
  escaped="$(escape_sed "${value}")"
  if grep -q "^${key}=" "${file}"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "${file}"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${file}"
  fi
}

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

reset_pin_now=0
if [[ ${INTERACTIVE} -eq 1 ]]; then
  read -r -p "Change admin PIN? [y/N] " input
  if [[ "${input}" =~ ^[Yy]$ ]]; then
    while true; do
      read -r -p "New QUAIL_ADMIN_PIN (4-9 digits): " pin_input
      if [[ -z "${pin_input}" ]]; then
        echo "PIN cannot be empty." >&2
        continue
      fi
      if [[ ! "${pin_input}" =~ ^[0-9]+$ ]] || [[ ${#pin_input} -lt 4 ]] || [[ ${#pin_input} -gt 9 ]]; then
        echo "PIN must be 4-9 digits." >&2
        continue
      fi
      QUAIL_ADMIN_PIN="${pin_input}"
      set_env_var "QUAIL_ADMIN_PIN" "${QUAIL_ADMIN_PIN}"
      reset_pin_now=1
      break
    done
  fi
fi
if [[ -f /etc/quail/config.env ]]; then
  if ! grep -q "^QUAIL_ENABLE_WS=" /etc/quail/config.env; then
    printf '\nQUAIL_ENABLE_WS=true\n' >> /etc/quail/config.env
  fi
fi
if [[ -z "${QUAIL_DOMAINS:-}" ]]; then
  echo "WARNING: QUAIL_DOMAINS is not set in /etc/quail/config.env." >&2
  echo "Upgrades will continue, but new installs require this value to be configured." >&2
fi

if [[ "${QUAIL_RESET_PIN:-false}" == "true" || ${reset_pin_now} -eq 1 ]]; then
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
