# Architecture

This document summarizes the architecture described in `QUAIL_CODEX_CONTEXT.md` and serves as a high‑level overview for developers and reviewers. The authoritative ingest decision model, including domain policy/rule/quarantine behavior, lives in `QUAIL_CODEX_CONTEXT.md`. Forward-looking design work is captured in `docs/QUAIL_2_0_SPEC.md`.

## Public Plane

Quail uses **Postfix** as its public facing SMTP server. The mail daemon listens on TCP/25 and accepts mail for configured domains (example: `mail.example.test`). Postfix enforces a maximum message size (default 10 MB) and pipes the raw RFC822 message together with the envelope recipient to the ingest script.

## Private Plane

A single Python **FastAPI** service provides both the ingest entrypoint and the web UI/API【104907567664902†L49-L53】. The UI is deliberately not publicly accessible—access is restricted to VPN or interface‑restricted networks【104907567664902†L49-L54】. The service binds to localhost by default and can be reverse‑proxied or exposed directly over a VPN as needed【104907567664902†L121-L123】.

Inbox list updates use a WebSocket channel with app-level ping/pong keepalive and polling fallback to preserve live refresh behavior.

## Ingest Pipeline

The ingest entrypoint stores the full raw email as a `.eml` file and extracts metadata including recipient, from, subject, date, message‑ID and size【104907567664902†L60-L69】. Metadata is inserted into a SQLite database【104907567664902†L62-L70】. Attachments are allowed only for specific MIME types (default **PDF**), configurable via the admin UI【104907567664902†L71-L74】. Messages with disallowed attachments are quarantined and hidden from non‑admin users【104907567664902†L71-L78】. The ingest pipeline applies deterministic domain policies and address/content rules to set each message status (INBOX, QUARANTINE, or DROP) and stores decision metadata alongside the message.

## Retention and Purge

By default inbox messages and attachments are retained for **30 days**, while quarantined or dropped messages use a shorter default retention window. A daily purge job deletes expired `.eml` files, extracted attachments and database rows. Administrators can adjust both retention periods via the UI, optionally set per-domain quarantine overrides and delete individual messages manually.

## Admin Model

There are no per‑user accounts. A single shared admin PIN gates access to privileged actions. The PIN is stored as a salted strong hash; admin sessions have a limited TTL and rate‑limiting protects against brute force. Admins can change global settings, delete messages, toggle full HTML rendering in the sandboxed iframe view, and modify attachment rules.

## Repository Structure

The expected repository layout is specified in `QUAIL_CODEX_CONTEXT.md`【104907567664902†L127-L173】. Core code lives under the `quail/` package, system scripts reside in `scripts/` and `systemd/`, configuration files are under `config/` and the top level contains installation scripts and this documentation. Never invent alternative layouts without explicit justification.
