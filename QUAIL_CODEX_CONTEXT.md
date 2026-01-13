# Quail — Self-Hosted Receive-Only Mail System
(Authoritative Context for Codex)

This document is the **single source of truth** for the Quail project.
All code, configuration, and iteration must conform to what is defined here.
Do not invent requirements. Do not remove constraints. Prefer safe defaults.

---

## 1. Project Overview

**Name:** Quail  
**Purpose:** Self-hosted, receive-only email sink for internal QA/dev teams.

Quail accepts email from the public internet and exposes a **shared inbox UI**
accessible only over VPN or explicitly configured private networks.

Quail does NOT send email. Ever.

No SaaS. No external dependencies. One operator. Low volume.

---

## 2. Core Requirements (Non-Negotiable)

- Domain: configured at install (example: `mail.example.test` in `/etc/quail/config.env`)
- Catch-all inbound: `anything@mail.example.test` (when using catch-all)
- Receive-only. No outbound SMTP, no bounces.
- Public SMTP, private UI.
- No per-user accounts.
- Shared inbox for all viewers.
- Admin actions gated by a **single PIN**.
- Raw `.eml` stored as source of truth.
- SQLite for metadata + settings.
- Retention policy with automatic purge.
- Easy upkeep by one non-developer operator.

---

## 3. Architecture

### Public Plane
- Postfix SMTP
- Listens on TCP/25
- Accepts mail for configured domains (example: `mail.example.test`)
- Enforces max message size (default 10 MB)
- Pipes raw RFC822 message + envelope RCPT to local ingest

### Private Plane
- Single service (preferred: Python FastAPI)
- Provides:
  - Ingest entrypoint (invoked by Postfix)
  - Web UI + API
- UI must NOT be publicly accessible
- VPN-only or interface-restricted access

---

## 4. Email Handling Rules

### Ingest
- Store full raw email as `.eml`
- Extract metadata:
  - Envelope RCPT
  - From
  - Subject
  - Date
  - Message-ID
  - Size
- Insert metadata into SQLite

### Attachments
- Default allowed type: **PDF only**
- Allowed attachment MIME types must be configurable via admin UI
- If a message contains disallowed attachment types:
  - Do NOT reject at SMTP
  - Mark message as **quarantined**
  - Hide from non-admin UI
- Attachments must never be executed or rendered unsafely

### HTML
- Default: plaintext only
- Optional full HTML view (admin-controlled) rendered in a sandboxed iframe
- Plaintext remains available alongside HTML

---

## 5. Retention Policy

- Default retention: 30 days
- Configurable via admin UI
- Daily purge job deletes:
  - `.eml`
  - Extracted attachments
  - Database rows
- Admin deletions remove messages immediately

---

## 6. Admin Model

- Single shared admin PIN
- PIN stored as salted strong hash (Argon2 or bcrypt)
- Admin session TTL: 15–30 minutes
- Rate-limit PIN attempts
- Log admin actions (timestamp + source IP)

Admin-only actions:
- Change global settings
- Delete messages
- Enable/disable HTML rendering
- Modify attachment rules

---

## 7. Security Constraints

- Never send email
- Never execute attachment content
- Prevent path traversal in filenames
- Sanitize HTML strictly if enabled
- UI must not bind to `0.0.0.0` by default
- Prefer binding to localhost + VPN firewall rules
- Do not log full email bodies

---

## 8. Expected Repository Structure

Codex must create and work within the following structure:

quail/
README.md
CODEX_CONTEXT.md
.gitignore
requirements.txt
pyproject.toml

quail/
init.py
web.py
ingest.py
purge.py
db.py
security.py
settings.py
logging_config.py
templates/
layout.html
inbox.html
message.html
admin_unlock.html
admin_settings.html

scripts/
quail-ingest

systemd/
quail.service
quail-purge.service
quail-purge.timer

postfix/
virtual
maincf.snippet
mastercf_pipe.snippet

config/
config.example.env

install.sh
upgrade.sh

No alternative layouts unless explicitly justified.

---

## 9. Implementation Preferences

- Language: Python
- Framework: FastAPI
- Database: SQLite
- Single deployable service
- systemd for service + purge timer
- Idempotent install and upgrade scripts
- No destructive operations in install/upgrade
- Minimal dependencies, pinned where reasonable

---

## 10. install.sh Expectations

install.sh must:
- Install required OS packages
- Create system user
- Create `/var/lib/quail/{eml,att}` with correct permissions
- Create Python venv and install deps
- Install Postfix catch-all pipe safely (no clobbering)
- Install systemd units and enable them
- Be safe to re-run

---

## 11. upgrade.sh Expectations

upgrade.sh must:
- Update dependencies if needed
- Restart services cleanly
- Never delete stored mail
- Never modify retention or admin data

---

## 12. Operational Assumptions

- Host is a spare laptop running Ubuntu Server
- Access via SSH and VPN
- Email volume: low (tens/day at most)
- Maintainability > cleverness
- Explicit > implicit
- Boring > fragile

---

## 13. Codex Rules of Engagement

- Do NOT hallucinate configs, flags, or features
- If unsure, leave a TODO with a safe default
- Prefer clarity over abstraction
- Update README when behavior changes
- Show exact diffs when changing configs
- Never assume public exposure is acceptable

This document overrides all other context.