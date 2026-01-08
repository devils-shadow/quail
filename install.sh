#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/quail"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: install.sh must be run as root." >&2
  exit 1
fi

if [[ "${SCRIPT_DIR}" != "${INSTALL_DIR}" ]]; then
  if [[ ! -d "${INSTALL_DIR}" ]]; then
    echo "ERROR: expected Quail repo at ${INSTALL_DIR}." >&2
    echo "TODO: clone this repository to ${INSTALL_DIR} before running install." >&2
    exit 1
  fi
fi

if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y python3-venv python3-pip postfix
else
  echo "ERROR: unsupported package manager. TODO: install python3-venv, python3-pip, postfix." >&2
  exit 1
fi

if ! id -u quail >/dev/null 2>&1; then
  useradd --system --home /var/lib/quail --shell /usr/sbin/nologin quail
fi

install -d -o quail -g quail -m 0750 /var/lib/quail /var/lib/quail/eml /var/lib/quail/att
install -d -m 0755 /etc/quail
if [[ ! -f /etc/quail/config.env ]]; then
  install -m 0644 "${INSTALL_DIR}/config/config.example.env" /etc/quail/config.env
fi

if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
  python3 -m venv "${INSTALL_DIR}/venv"
fi

"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

if [[ ! -f /etc/postfix/virtual ]]; then
  printf '%s\n' "# Quail catch-all mapping for m.cst.ro" > /etc/postfix/virtual
fi
if ! grep -Fxq "@m.cst.ro quail" /etc/postfix/virtual; then
  printf '%s\n' "@m.cst.ro quail" >> /etc/postfix/virtual
fi

if command -v postconf >/dev/null 2>&1; then
  if [[ -f /etc/quail/config.env ]]; then
    # shellcheck disable=SC1091
    set -a
    source /etc/quail/config.env
    set +a
  fi
  max_size_mb="${QUAIL_MAX_MESSAGE_SIZE_MB:-10}"
  max_size_bytes=$((max_size_mb * 1024 * 1024))
  virtual_alias_domains="$(postconf -h virtual_alias_domains || true)"
  if [[ -z "${virtual_alias_domains}" ]]; then
    postconf -e "virtual_alias_domains = m.cst.ro"
  elif [[ "${virtual_alias_domains}" != *"m.cst.ro"* ]]; then
    echo "WARNING: virtual_alias_domains is already set; update manually to include m.cst.ro." >&2
  fi

  virtual_alias_maps="$(postconf -h virtual_alias_maps || true)"
  if [[ -z "${virtual_alias_maps}" ]]; then
    postconf -e "virtual_alias_maps = hash:/etc/postfix/virtual"
  elif [[ "${virtual_alias_maps}" != *"/etc/postfix/virtual"* ]]; then
    echo "WARNING: virtual_alias_maps is already set; update manually to include /etc/postfix/virtual." >&2
  fi

  message_size_limit="$(postconf -h message_size_limit || true)"
  if [[ -z "${message_size_limit}" ]]; then
    postconf -e "message_size_limit = ${max_size_bytes}"
  elif [[ "${message_size_limit}" != "${max_size_bytes}" ]]; then
    echo "WARNING: message_size_limit is already set; update manually to ${max_size_bytes} bytes." >&2
  fi
else
  echo "ERROR: postconf not found; ensure postfix is installed." >&2
  exit 1
fi

if ! grep -q "^quail\s" /etc/postfix/master.cf; then
  cat "${INSTALL_DIR}/postfix/mastercf_pipe.snippet" >> /etc/postfix/master.cf
fi

postmap /etc/postfix/virtual
if command -v systemctl >/dev/null 2>&1; then
  systemctl reload postfix || systemctl restart postfix
fi

install -m 0644 "${INSTALL_DIR}/systemd/quail.service" /etc/systemd/system/quail.service
install -m 0644 "${INSTALL_DIR}/systemd/quail-purge.service" /etc/systemd/system/quail-purge.service
install -m 0644 "${INSTALL_DIR}/systemd/quail-purge.timer" /etc/systemd/system/quail-purge.timer

systemctl daemon-reload
systemctl enable --now quail.service
systemctl enable --now quail-purge.timer

echo "Quail install complete."
