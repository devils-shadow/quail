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
module and stores raw `.eml` files plus metadata in SQLite.
Oversize messages are rejected at SMTP via Postfix and dropped by the ingest
pipeline when they exceed the configured maximum size.
module and stores raw `.eml` files plus metadata in SQLite. Allowed attachments
are extracted into the attachment directory, and attachment metadata is stored
alongside each message.

## Configuration

Copy `config/config.example.env` to `/etc/quail/config.env` and adjust values as
needed.

## Admin access

Admin actions are gated by a shared PIN stored as a hash in the SQLite settings
table (`admin_pin_hash`). Session unlocks are short-lived and require the PIN
again after expiration. TODO: provide a supported setup flow for the initial
PIN.

## HTML rendering

Message detail pages default to plaintext. Admins can enable sanitized HTML
rendering in settings; HTML is cleaned before display and remote images are
blocked. If HTML rendering is disabled or missing, Quail falls back to
plaintext.
