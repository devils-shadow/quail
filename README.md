# Quail

Quail is a self-hosted, receive-only mail sink for internal QA/dev teams. It
accepts inbound mail on configured domains (example: `mail.example.test`) and
exposes a private shared inbox UI. See `QUAIL_CODEX_CONTEXT.md` for the
authoritative requirements, including the domain policy/rule/quarantine model.

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
- WebSocket inbox updates enabled by default; opt out via `QUAIL_ENABLE_WS=false`.
- Message detail pages with HTML, plaintext, and attachments tabs; attachments
  are available for download when present.
- Quarantine review with bulk restore/delete actions and rule creation flows.

## Configuration

Use this checklist before running `install.sh`:

1) Copy `config/config.example.env` from the repo into `/etc/quail/config.env`.
2) Edit `/etc/quail/config.env` and set `QUAIL_DOMAINS` to a comma-separated
   list of domains Postfix should accept (required; the installer rejects the
   example value).
3) In the same file, set `QUAIL_ADMIN_PIN` to a 4-9 digit numeric PIN (required
   on first install).
4) Optional: choose one of the following for `QUAIL_BIND_HOST` in
   `/etc/quail/config.env`:
   - Local-only dev: `127.0.0.1`
   - VPN/internal DNS (direct access): `0.0.0.0`
   - Public internet: `127.0.0.1` behind a reverse proxy (for example, nginx
     with OAuth2)

5) Run the installer: `sudo ./install.sh` (optional: `--smoke-test`).
6) Verify services: `systemctl status quail quail-purge.timer`.
7) If you terminate TLS with nginx, add WebSocket upgrade headers (see
   `docs/RUNBOOK.md`) and reload nginx.

### Upgrades

To upgrade an existing install:

1) Pull the latest changes into `/opt/quail`.
2) Run `sudo ./upgrade.sh` to update dependencies and restart services.
3) Verify services: `systemctl status quail quail-purge.timer`.

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

## Testing

- See `docs/TESTING.md` for pytest markers, standard commands, and CI coverage.

## Deprecations

- Framework deprecation notes and a minimal migration plan live in
  `docs/DEPRECATIONS.md`.

## Install location

The install script and systemd units assume the repository is cloned to
`/opt/quail`. If you want to install from `/home/user`, you must update
`install.sh` and the systemd unit paths accordingly before running install.
