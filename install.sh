#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/quail"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE_TEST=0
FORCE_INTERACTIVE=0
FORCE_NON_INTERACTIVE=0

for arg in "$@"; do
  case "${arg}" in
    --smoke-test)
      SMOKE_TEST=1
      ;;
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
  packages=(python3-venv python3-pip postfix rsyslog)
  if [[ ${SMOKE_TEST} -eq 1 ]]; then
    packages+=(swaks)
  fi
  apt-get install -y "${packages[@]}"
else
  echo "ERROR: unsupported package manager. TODO: install python3-venv, python3-pip, postfix, rsyslog." >&2
  exit 1
fi

install -d -m 0755 /etc/quail
if [[ ! -f /etc/quail/config.env ]]; then
  install -m 0644 "${INSTALL_DIR}/config/config.example.env" /etc/quail/config.env
fi

if [[ -f /etc/quail/config.env ]]; then
  # shellcheck disable=SC1091
  set -a
  source /etc/quail/config.env
  set +a
fi

if ! id -u quail >/dev/null 2>&1; then
  useradd --system --home /var/lib/quail --shell /usr/sbin/nologin quail
fi

if [[ ${INTERACTIVE} -eq 1 ]]; then
  default_data_dir="/var/lib/quail"
  default_eml_dir="${default_data_dir}/eml"
  default_att_dir="${default_data_dir}/att"
  default_db_path="${default_data_dir}/quail.db"

  data_dir="${QUAIL_DATA_DIR:-${default_data_dir}}"
  eml_dir="${QUAIL_EML_DIR:-${default_eml_dir}}"
  att_dir="${QUAIL_ATTACHMENT_DIR:-${default_att_dir}}"
  db_path="${QUAIL_DB_PATH:-${default_db_path}}"

  if [[ "${data_dir}" == "${default_data_dir}" && "${eml_dir}" == "${default_eml_dir}" && "${att_dir}" == "${default_att_dir}" && "${db_path}" == "${default_db_path}" ]]; then
    read -r -p "Use default storage paths under ${default_data_dir}? [Y/n] " use_defaults
    if [[ "${use_defaults}" =~ ^[Nn]$ ]]; then
      read -r -p "QUAIL_DATA_DIR [${default_data_dir}]: " input
      data_dir="${input:-${default_data_dir}}"
      read -r -p "QUAIL_EML_DIR [${data_dir}/eml]: " input
      eml_dir="${input:-${data_dir}/eml}"
      read -r -p "QUAIL_ATTACHMENT_DIR [${data_dir}/att]: " input
      att_dir="${input:-${data_dir}/att}"
      read -r -p "QUAIL_DB_PATH [${data_dir}/quail.db]: " input
      db_path="${input:-${data_dir}/quail.db}"

      set_env_var "QUAIL_DATA_DIR" "${data_dir}"
      set_env_var "QUAIL_EML_DIR" "${eml_dir}"
      set_env_var "QUAIL_ATTACHMENT_DIR" "${att_dir}"
      set_env_var "QUAIL_DB_PATH" "${db_path}"
      QUAIL_DATA_DIR="${data_dir}"
      QUAIL_EML_DIR="${eml_dir}"
      QUAIL_ATTACHMENT_DIR="${att_dir}"
      QUAIL_DB_PATH="${db_path}"
    fi
  fi

  if [[ -z "${QUAIL_DOMAINS:-}" || "${QUAIL_DOMAINS}" == "mail.example.test" ]]; then
    while true; do
      read -r -p "QUAIL_DOMAINS (comma-separated) []: " input
      if [[ -z "${input}" || "${input}" == "mail.example.test" ]]; then
        echo "Please enter at least one real domain." >&2
        continue
      fi
      QUAIL_DOMAINS="${input}"
      set_env_var "QUAIL_DOMAINS" "${QUAIL_DOMAINS}"
      break
    done
  fi

  if [[ "${QUAIL_BIND_HOST:-127.0.0.1}" == "127.0.0.1" ]]; then
    echo "Choose bind host:"
    echo "  1) Local-only dev (127.0.0.1)"
    echo "  2) VPN/internal direct access (0.0.0.0)"
    echo "  3) Reverse proxy (keep 127.0.0.1)"
    read -r -p "Selection [1]: " input
    case "${input}" in
      2)
        QUAIL_BIND_HOST="0.0.0.0"
        ;;
      3)
        QUAIL_BIND_HOST="127.0.0.1"
        ;;
      *)
        QUAIL_BIND_HOST="127.0.0.1"
        ;;
    esac
    set_env_var "QUAIL_BIND_HOST" "${QUAIL_BIND_HOST}"
  fi

  if [[ "${QUAIL_BIND_PORT:-8000}" == "8000" ]]; then
    read -r -p "QUAIL_BIND_PORT [8000]: " input
    if [[ -n "${input}" ]]; then
      QUAIL_BIND_PORT="${input}"
      set_env_var "QUAIL_BIND_PORT" "${QUAIL_BIND_PORT}"
    fi
  fi

  if [[ "${QUAIL_MAX_MESSAGE_SIZE_MB:-10}" == "10" ]]; then
    while true; do
      read -r -p "QUAIL_MAX_MESSAGE_SIZE_MB [10]: " input
      if [[ -z "${input}" ]]; then
        break
      fi
      if [[ ! "${input}" =~ ^[0-9]+$ ]]; then
        echo "Please enter a numeric value." >&2
        continue
      fi
      QUAIL_MAX_MESSAGE_SIZE_MB="${input}"
      set_env_var "QUAIL_MAX_MESSAGE_SIZE_MB" "${QUAIL_MAX_MESSAGE_SIZE_MB}"
      break
    done
  fi

  if [[ -z "${QUAIL_ALLOWED_ORIGINS:-}" ]]; then
    suggested_origin=""
    if [[ "${QUAIL_BIND_HOST:-127.0.0.1}" == "127.0.0.1" ]]; then
      suggested_origin="http://127.0.0.1:${QUAIL_BIND_PORT:-8000}"
    fi
    if [[ -n "${suggested_origin}" ]]; then
      read -r -p "QUAIL_ALLOWED_ORIGINS (comma-separated) [${suggested_origin} or blank]: " input
      if [[ -n "${input}" ]]; then
        QUAIL_ALLOWED_ORIGINS="${input}"
        set_env_var "QUAIL_ALLOWED_ORIGINS" "${QUAIL_ALLOWED_ORIGINS}"
      fi
    else
      read -r -p "QUAIL_ALLOWED_ORIGINS (comma-separated, blank to allow host origin) []: " input
      if [[ -n "${input}" ]]; then
        QUAIL_ALLOWED_ORIGINS="${input}"
        set_env_var "QUAIL_ALLOWED_ORIGINS" "${QUAIL_ALLOWED_ORIGINS}"
      fi
    fi
  fi
fi

data_dir="${QUAIL_DATA_DIR:-/var/lib/quail}"
eml_dir="${QUAIL_EML_DIR:-${data_dir}/eml}"
att_dir="${QUAIL_ATTACHMENT_DIR:-${data_dir}/att}"
db_path="${QUAIL_DB_PATH:-${data_dir}/quail.db}"

install -d -o quail -g quail -m 0750 "${data_dir}" "${eml_dir}" "${att_dir}"

if [[ -f /etc/quail/config.env ]]; then
  if ! grep -q "^QUAIL_ENABLE_WS=" /etc/quail/config.env; then
    printf '\nQUAIL_ENABLE_WS=true\n' >> /etc/quail/config.env
  fi
fi

pin_already_set=0
if [[ -f "${db_path}" ]]; then
  pin_already_set="$(python3 - <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
try:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'admin_pin_hash' LIMIT 1"
        ).fetchone()
    if row and row[0]:
        print("1")
    else:
        print("0")
except sqlite3.Error:
    print("0")
PY
"${db_path}")"
fi

if [[ ${INTERACTIVE} -eq 1 && "${pin_already_set}" != "1" && -z "${QUAIL_ADMIN_PIN:-}" ]]; then
  while true; do
    read -r -p "Set QUAIL_ADMIN_PIN (4-9 digits): " input
    if [[ -z "${input}" ]]; then
      echo "PIN is required for first install." >&2
      continue
    fi
    if [[ ! "${input}" =~ ^[0-9]+$ ]] || [[ ${#input} -lt 4 ]] || [[ ${#input} -gt 9 ]]; then
      echo "PIN must be 4-9 digits." >&2
      continue
    fi
    QUAIL_ADMIN_PIN="${input}"
    set_env_var "QUAIL_ADMIN_PIN" "${QUAIL_ADMIN_PIN}"
    break
  done
fi

if [[ "${pin_already_set}" != "1" && -z "${QUAIL_ADMIN_PIN:-}" ]]; then
  cat <<'EOF' >&2
========================================
ERROR: QUAIL_ADMIN_PIN is not set.
========================================

Quail requires a digits-only admin PIN (4-9 digits) during installation.
Set QUAIL_ADMIN_PIN in /etc/quail/config.env, for example:

  QUAIL_ADMIN_PIN=1234

Then re-run: sudo ./install.sh
EOF
  exit 1
fi

if [[ "${pin_already_set}" != "1" ]]; then
  if [[ ! "${QUAIL_ADMIN_PIN}" =~ ^[0-9]+$ ]] || [[ ${#QUAIL_ADMIN_PIN} -lt 4 ]] || [[ ${#QUAIL_ADMIN_PIN} -gt 9 ]]; then
    cat <<'EOF' >&2
========================================
ERROR: QUAIL_ADMIN_PIN must be 4-9 digits.
========================================

Update QUAIL_ADMIN_PIN in /etc/quail/config.env with a digits-only value, then
re-run: sudo ./install.sh
EOF
    exit 1
  fi
fi

if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
  python3 -m venv "${INSTALL_DIR}/venv"
fi

chmod 0755 "${INSTALL_DIR}/scripts/quail-ingest"

"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

"${INSTALL_DIR}/venv/bin/python" - <<'PY'
import os

from quail import db, settings
from quail.security import hash_pin

pin = os.getenv("QUAIL_ADMIN_PIN", "")
db_path = settings.get_settings().db_path
db.init_db(db_path)
if pin and db.get_setting(db_path, "admin_pin_hash") is None:
    db.set_setting(db_path, "admin_pin_hash", hash_pin(pin))
PY

if command -v postconf >/dev/null 2>&1; then
  if [[ -z "${QUAIL_DOMAINS:-}" || "${QUAIL_DOMAINS}" == "mail.example.test" ]]; then
    cat <<'EOF' >&2
========================================
ERROR: QUAIL_DOMAINS is not set (or still the example value).
========================================

Quail requires at least one real mail domain to be configured before installation.
Set QUAIL_DOMAINS in /etc/quail/config.env, for example:

  QUAIL_DOMAINS=mail.example.test

Then re-run: sudo ./install.sh
EOF
    exit 1
  fi
  domains_raw="${QUAIL_DOMAINS}"
  IFS=',' read -r -a domain_list <<< "${domains_raw}"
  quail_domains=()
  for domain_entry in "${domain_list[@]}"; do
    domain="$(echo "${domain_entry}" | xargs)"
    if [[ -n "${domain}" ]]; then
      quail_domains+=("${domain}")
    fi
  done
  if [[ ${#quail_domains[@]} -eq 0 ]]; then
    echo "ERROR: QUAIL_DOMAINS is empty after parsing; check /etc/quail/config.env." >&2
    exit 1
  fi
  quail_domains_string="${quail_domains[*]}"
  max_size_mb="${QUAIL_MAX_MESSAGE_SIZE_MB:-10}"
  max_size_bytes=$((max_size_mb * 1024 * 1024))
  # NOTE: We intentionally do not use virtual aliasing for Quail domains because
  # virtual alias rewriting happens before transport lookup and would bypass the
  # pipe transport needed to preserve the original envelope recipient.
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^# ]] && continue
    key="${line%%=*}"
    key="$(echo "${key}" | xargs)"
    current="$(postconf -h "${key}" || true)"
    if [[ -z "${current}" ]]; then
      postconf -e "${line}"
    fi
  done < "${INSTALL_DIR}/postfix/maincf.snippet"

  relay_domains="$(postconf -h relay_domains || true)"
  if [[ -z "${relay_domains}" ]]; then
    postconf -e "relay_domains = ${quail_domains_string}"
  else
    missing_domain=0
    for domain in "${quail_domains[@]}"; do
      if [[ "${relay_domains}" != *"${domain}"* ]]; then
        missing_domain=1
        break
      fi
    done
    if [[ ${missing_domain} -eq 1 ]]; then
      echo "WARNING: relay_domains is already set; update manually to include ${quail_domains_string}." >&2
    fi
  fi

  transport_maps="$(postconf -h transport_maps || true)"
  if [[ -z "${transport_maps}" ]]; then
    postconf -e "transport_maps = hash:/etc/postfix/transport"
  elif [[ "${transport_maps}" != *"/etc/postfix/transport"* ]]; then
    echo "WARNING: transport_maps is already set; update manually to include /etc/postfix/transport." >&2
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

if [[ ! -f /etc/postfix/transport ]]; then
  printf '%s\n' "# Quail transport mapping" > /etc/postfix/transport
fi
for domain in "${quail_domains[@]}"; do
  entry="${domain} quail:"
  if ! grep -Fxq "${entry}" /etc/postfix/transport; then
    printf '%s\n' "${entry}" >> /etc/postfix/transport
  fi
done

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

if [[ ${SMOKE_TEST} -eq 1 ]]; then
  echo "Running install smoke test..."
  if ! systemctl is-active --quiet quail.service; then
    echo "ERROR: quail.service is not active." >&2
    exit 1
  fi
  if [[ ${#quail_domains[@]} -eq 0 ]]; then
    echo "ERROR: QUAIL_DOMAINS is empty; cannot run smoke test." >&2
    exit 1
  fi
  test_domain="${quail_domains[0]}"
  test_localpart="smoke-$(date +%s)"
  test_rcpt="${test_localpart}@${test_domain}"
  transport_check="$(postmap -q "${test_domain}" /etc/postfix/transport || true)"
  if [[ "${transport_check}" != "quail:" ]]; then
    echo "ERROR: /etc/postfix/transport does not route ${test_domain} to quail:." >&2
    exit 1
  fi
  if ! swaks --to "${test_rcpt}" --from "smoke@${test_domain}" --server 127.0.0.1 --timeout 10 >/dev/null 2>&1; then
    echo "ERROR: swaks failed to send test email to ${test_rcpt}." >&2
    exit 1
  fi
  db_path="${QUAIL_DB_PATH:-/var/lib/quail/quail.db}"
  if ! python3 - <<'PY' "${db_path}" "${test_rcpt}"; then
import sqlite3
import sys
import time

db_path = sys.argv[1]
rcpt = sys.argv[2]
deadline = time.time() + 15

while time.time() < deadline:
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT id FROM messages WHERE envelope_rcpt = ? ORDER BY id DESC LIMIT 1",
                (rcpt,),
            ).fetchone()
        if row:
            sys.exit(0)
    except sqlite3.Error:
        pass
    time.sleep(1)

sys.exit(1)
PY
  then
    echo "ERROR: smoke test message not ingested within timeout." >&2
    exit 1
  fi
  bind_host="${QUAIL_BIND_HOST:-127.0.0.1}"
  bind_port="${QUAIL_BIND_PORT:-8000}"
  echo "Smoke test passed: message ingested for ${test_rcpt}."
  echo "UI reachable at http://${bind_host}:${bind_port}/"
fi

echo "Quail install complete."
