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

"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

systemctl daemon-reload
systemctl restart quail.service
systemctl restart quail-purge.timer

echo "Quail upgrade complete."
