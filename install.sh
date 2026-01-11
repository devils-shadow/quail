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
  apt-get install -y python3-venv python3-pip postfix rsyslog
else
  echo "ERROR: unsupported package manager. TODO: install python3-venv, python3-pip, postfix, rsyslog." >&2
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

if command -v postconf >/dev/null 2>&1; then
  if [[ -f /etc/quail/config.env ]]; then
    # shellcheck disable=SC1091
    set -a
    source /etc/quail/config.env
    set +a
  fi
  domains_raw="${QUAIL_DOMAINS:-m.cst.ro}"
  IFS=',' read -r -a domain_list <<< "${domains_raw}"
  quail_domains=()
  for domain_entry in "${domain_list[@]}"; do
    domain="$(echo "${domain_entry}" | xargs)"
    if [[ -n "${domain}" ]]; then
      quail_domains+=("${domain}")
    fi
  done
  if [[ ${#quail_domains[@]} -eq 0 ]]; then
    quail_domains=("m.cst.ro")
  fi
  quail_domains_string="${quail_domains[*]}"
  max_size_mb="${QUAIL_MAX_MESSAGE_SIZE_MB:-10}"
  max_size_bytes=$((max_size_mb * 1024 * 1024))
  virtual_alias_domains="$(postconf -h virtual_alias_domains || true)"
  if [[ -z "${virtual_alias_domains}" ]]; then
    postconf -e "virtual_alias_domains = ${quail_domains_string}"
  else
    missing_domain=0
    for domain in "${quail_domains[@]}"; do
      if [[ "${virtual_alias_domains}" != *"${domain}"* ]]; then
        missing_domain=1
        break
      fi
    done
    if [[ ${missing_domain} -eq 1 ]]; then
      echo "WARNING: virtual_alias_domains is already set; update manually to include ${quail_domains_string}." >&2
    fi
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

  transport_maps="$(postconf -h transport_maps || true)"
  if [[ -z "${transport_maps}" ]]; then
    postconf -e "transport_maps = hash:/etc/postfix/transport"
  elif [[ "${transport_maps}" != *"/etc/postfix/transport"* ]]; then
    echo "WARNING: transport_maps is already set; update manually to include /etc/postfix/transport." >&2
  fi
else
  echo "ERROR: postconf not found; ensure postfix is installed." >&2
  exit 1
fi

if [[ ! -f /etc/postfix/virtual ]]; then
  printf '%s\n' "# Quail catch-all mapping for Quail domains" > /etc/postfix/virtual
fi
for domain in "${quail_domains[@]}"; do
  entry="@${domain} quail"
  if ! grep -Fxq "${entry}" /etc/postfix/virtual; then
    printf '%s\n' "${entry}" >> /etc/postfix/virtual
  fi
done

if ! grep -q "^quail\s" /etc/postfix/master.cf; then
  cat "${INSTALL_DIR}/postfix/mastercf_pipe.snippet" >> /etc/postfix/master.cf
fi

if [[ ! -f /etc/postfix/transport ]]; then
  printf '%s\n' "# Quail transport mapping" > /etc/postfix/transport
fi
for domain in "${quail_domains[@]}"; do
  entry="${domain} quail:"
  if ! grep -Fxq "${entry}" /etc/postfix/transport; then
    printf '%s\n' "${entry}" >> /etc/postfix/transport
  fi
done

postmap /etc/postfix/virtual
postmap /etc/postfix/transport
if command -v systemctl >/dev/null 2>&1; then
  systemctl reload postfix || systemctl restart postfix
  systemctl enable --now rsyslog
fi

install -m 0644 "${INSTALL_DIR}/systemd/quail.service" /etc/systemd/system/quail.service
install -m 0644 "${INSTALL_DIR}/systemd/quail-purge.service" /etc/systemd/system/quail-purge.service
install -m 0644 "${INSTALL_DIR}/systemd/quail-purge.timer" /etc/systemd/system/quail-purge.timer

systemctl daemon-reload
systemctl enable --now quail.service
systemctl enable --now quail-purge.timer

echo "Quail install complete."
