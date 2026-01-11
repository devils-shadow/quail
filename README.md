# Quail

Quail is a self-hosted, receive-only mail sink for CST QA/dev teams. It accepts
inbound mail on `m.cst.ro` and exposes a private shared inbox UI. See
`QUAIL_CODEX_CONTEXT.md` for the authoritative requirements and constraints.

## Status

Initial repository scaffolding and ingest pipeline are in place. The retention
purge job and admin settings form are implemented, while the broader FastAPI UI
and install/upgrade automation are still stubbed with TODOs.

## Ingest

Postfix should pipe messages to `scripts/quail-ingest`, which runs the ingest
module with the `/opt/quail/venv` interpreter and stores raw `.eml` files plus
metadata in SQLite.
Oversize messages are rejected at SMTP via Postfix and dropped by the ingest
pipeline when they exceed the configured maximum size. Allowed attachments are
extracted into the attachment directory, and attachment metadata is stored
alongside each message.
The ingest pipeline applies deterministic domain policies and address/content
rules to mark messages as INBOX, QUARANTINE, or DROP while storing the decision
metadata in SQLite. Each ingest also records a decision log row with the final
decision, reason, recipient details, and sender domain for operator visibility.

## Configuration

Copy `config/config.example.env` to `/etc/quail/config.env` and adjust values as
needed. The default bind host in the example config is `127.0.0.1`, so the
service binds to localhost unless you change it; use a reverse proxy and DNS if
you need external access.

## Admin access

Admin actions are gated by a shared PIN stored as a hash in the SQLite settings
table (`admin_pin_hash`). Session unlocks are short-lived and require the PIN
again after expiration. TODO: provide a supported setup flow for the initial
PIN. Admins can delete messages immediately from the message detail view.
Admins can also review quarantined messages in the admin quarantine view,
restore or delete them in bulk, and create allow/block rules from selections.
Admin settings also include per-domain policy controls (mode + default action)
that apply to new ingests and require PIN confirmation for each change. Admins
can also manage per-domain allow/block rules (regex patterns with priorities)
from the settings page; rule changes apply only to new ingests.
Admins can configure separate retention windows for inbox and quarantine
messages, plus optional per-domain quarantine retention overrides in the
domain policy section. The settings page includes ingest visibility metrics
and a lightweight audit log of admin actions retained for 30 days.

## HTML rendering

Message detail pages default to plaintext. Admins can enable sanitized HTML
rendering in settings; HTML is cleaned before display and remote images are
blocked. If HTML rendering is disabled or missing, Quail falls back to
plaintext.

## Install location

The install script and systemd units assume the repository is cloned to
`/opt/quail`. If you want to install from `/home/cst`, you must update
`install.sh` and the systemd unit paths accordingly before running install.
