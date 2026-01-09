# Architecture

This document summarizes the architecture described in `QUAIL_CODEX_CONTEXT.md` and serves as a high‑level overview for developers and reviewers.

## Public Plane

Quail uses **Postfix** as its public facing SMTP server. The mail daemon listens on TCP/25 and accepts mail for the domain `m.cst.ro`【104907567664902†L42-L46】. Postfix enforces a maximum message size (default 10 MB) and pipes the raw RFC822 message together with the envelope recipient to the ingest script【104907567664902†L42-L47】.

## Private Plane

A single Python **FastAPI** service provides both the ingest entrypoint and the web UI/API【104907567664902†L49-L53】. The UI is deliberately not publicly accessible—access is restricted to VPN or interface‑restricted networks【104907567664902†L49-L54】. The service binds to localhost by default and should be reverse‑proxied or firewalled for remote access【104907567664902†L121-L123】.

## Ingest Pipeline

The ingest entrypoint stores the full raw email as a `.eml` file and extracts metadata including recipient, from, subject, date, message‑ID and size【104907567664902†L60-L69】. Metadata is inserted into a SQLite database【104907567664902†L62-L70】. Attachments are allowed only for specific MIME types (default **PDF**), configurable via the admin UI【104907567664902†L71-L74】. Messages with disallowed attachments are quarantined and hidden from non‑admin users【104907567664902†L71-L78】. The ingest pipeline applies deterministic domain policies and address/content rules to set each message status (INBOX, QUARANTINE, or DROP) and stores decision metadata alongside the message.

## Retention and Purge

By default messages and attachments are retained for **30 days**. A daily purge job deletes expired `.eml` files, extracted attachments and database rows【104907567664902†L87-L95】. Administrators can adjust the retention period via the UI, and they may delete individual messages manually【104907567664902†L89-L96】.

## Admin Model

There are no per‑user accounts. A single shared admin PIN gates access to privileged actions【104907567664902†L31-L33】【104907567664902†L101-L112】. The PIN is stored as a salted strong hash; admin sessions have a limited TTL and rate‑limiting protects against brute force【104907567664902†L101-L106】. Admins can change global settings, delete messages, toggle HTML rendering and modify attachment rules【104907567664902†L107-L112】.

## Repository Structure

The expected repository layout is specified in `QUAIL_CODEX_CONTEXT.md`【104907567664902†L127-L173】. Core code lives under the `quail/` package, system scripts reside in `scripts/` and `systemd/`, configuration files are under `config/` and the top level contains installation scripts and this documentation. Never invent alternative layouts without explicit justification.
