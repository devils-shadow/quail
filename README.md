# Quail

Quail is a self-hosted, receive-only mail sink for CST QA/dev teams. It accepts
inbound mail on `m.cst.ro` and exposes a private shared inbox UI. See
`QUAIL_CODEX_CONTEXT.md` for the authoritative requirements and constraints.

## Status

Core ingest, UI, and admin workflows are implemented and actively maintained.
Quail is production-oriented for internal QA use; see `CHANGELOG.md` for
release updates.

## Ingest

- Postfix pipes messages to `scripts/quail-ingest`, which runs the ingest module
  with the `/opt/quail/venv` interpreter and ensures the repo root is on
  `PYTHONPATH`.
- Raw `.eml` files plus metadata are stored in SQLite; allowed attachments are
  extracted into the attachment directory with metadata recorded alongside.
- Oversize messages are rejected at SMTP and dropped by the ingest pipeline
  when they exceed the configured maximum size.
- Deterministic domain policies and address/content rules set status (INBOX,
  QUARANTINE, DROP) and record a decision log row with operator metadata.

## Web UI

- ETag-aware inbox auto-refresh with recent filter history.
- Message detail pages with HTML, plaintext, and attachments tabs; attachments
  are available for download when present.
- Quarantine review with bulk restore/delete actions and rule creation flows.

## Configuration

Copy `config/config.example.env` to `/etc/quail/config.env` and adjust values as
needed. The default bind host in the example config is `127.0.0.1`, so the
service binds to localhost unless you change it; use a reverse proxy and DNS if
you need external access. `QUAIL_DOMAINS` controls the comma-separated list of
domains that `install.sh` registers in Postfix transport maps and relay domains
(default: `m.cst.ro`).

## Admin access

- Admin actions are gated by a shared PIN stored as a hash in SQLite
  (`admin_pin_hash`) with short-lived unlock sessions.
- Admin settings include per-domain policy controls, allow/block rules, and
  HTML rendering toggles; rule and policy changes apply only to new ingests.
- Separate retention windows exist for inbox and quarantine messages, with
  optional per-domain quarantine overrides.
- The settings page includes ingest visibility metrics and a 30-day audit log.

## HTML rendering

- When enabled in settings, HTML renders in a sandboxed iframe alongside
  plaintext and attachments.
- HTML is rendered as sent; CID inline images are rewritten to local attachment
  URLs, while plaintext uses `html2text` conversion.
- If HTML rendering is disabled or missing, Quail falls back to plaintext only.
- In dark mode, minimal HTML messages inherit the app theme for readable
  contrast without altering richer layouts.

## Install location

The install script and systemd units assume the repository is cloned to
`/opt/quail`. If you want to install from `/home/cst`, you must update
`install.sh` and the systemd unit paths accordingly before running install.
