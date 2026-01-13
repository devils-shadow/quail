# Quail Spam Mitigation Plan (Admin Controls)

Status: Implemented. This plan is retained as historical context; see
`CHANGELOG.md` and `tests/test_phase8_acceptance.py` for current coverage.

This document is a repository-ready plan for the spam-mitigation admin features previously
scoped for Quail. It aligns with `QUAIL_CODEX_CONTEXT.md` and the existing FastAPI + SQLite
implementation. It is intentionally specific, but does not add new requirements beyond the
agreed scope.

---

## 0. Scope Guardrails (Read First)

These rules are mandatory and intentionally boring:

- No external services, no SaaS, no paid dependencies
- SQLite remains the only database
- One operator, low volume, maintainability > cleverness
- No spam scoring or ML classification
- No outbound mail, no SMTP feedback loops
- Prefer quarantine over drop, drop over rejection
- Any ambiguity → safe default + explicit TODO

Optional Phase 2 items are excluded; implement only what is documented here.

---

## 1. Phase Overview

Each phase should land as a working, testable system state:

1. Database schema extensions
2. Ingest decision pipeline
3. Admin domain policy controls
4. Address/content rule management
5. Quarantine view and actions
6. Retention and purge extensions
7. Metrics, logging, and audit
8. Hardening and acceptance verification

---

## 2. Phase 1 — Database Schema Changes

### 2.1 New Tables

Add the following tables via `db.py` schema migration logic (CREATE TABLE IF NOT EXISTS only):

#### `domain_policy`

- `id` INTEGER PRIMARY KEY
- `domain` TEXT UNIQUE NOT NULL
- `mode` TEXT NOT NULL
  Values: `OPEN`, `RESTRICTED`, `PAUSED`
- `default_action` TEXT NOT NULL
  Values: `INBOX`, `QUARANTINE`, `DROP`
- `created_at` TEXT NOT NULL
- `updated_at` TEXT NOT NULL

#### `address_rule`

- `id` INTEGER PRIMARY KEY
- `domain` TEXT NOT NULL
- `rule_type` TEXT NOT NULL
  Values: `ALLOW`, `BLOCK`
- `match_field` TEXT NOT NULL
  Values: `RCPT_LOCALPART`, `MAIL_FROM`, `FROM_DOMAIN`, `SUBJECT`
- `pattern` TEXT NOT NULL (stored as raw regex)
- `priority` INTEGER NOT NULL
- `action` TEXT NOT NULL
  Values: `INBOX`, `QUARANTINE`, `DROP`
- `enabled` INTEGER NOT NULL DEFAULT 1
- `note` TEXT
- `created_at` TEXT NOT NULL
- `updated_at` TEXT NOT NULL

### 2.2 Extend Existing Tables

Modify `messages` table:

- Add `status` TEXT NOT NULL DEFAULT `INBOX`
- Add `quarantine_reason` TEXT NULL
- Add `ingest_decision_meta` TEXT NULL (JSON stored as TEXT)

Do **not** remove the existing `quarantined` column yet. Treat it as legacy until migration is
complete.

---

## 3. Phase 2 — Ingest Decision Pipeline

### 3.1 Decision Flow

Implement a deterministic decision function inside `ingest.py` in this order:

1. Extract recipient domain from `envelope_rcpt`.
2. Load or create `domain_policy` (default: `OPEN`, `INBOX`).
3. If domain mode is `PAUSED` → decision = `DROP` (or `QUARANTINE` if configured).
4. Load enabled `address_rule` entries for the domain ordered by `priority ASC`.
5. First matching rule wins:
   - `ALLOW` → apply rule action (default `INBOX`)
   - `BLOCK` → apply rule action (default `QUARANTINE`)
6. If domain mode is `RESTRICTED` and no `ALLOW` rule matched → `QUARANTINE`.
7. Otherwise → apply domain `default_action`.

### 3.2 Performance Constraints

- Compile regexes once per process and cache them.
- Matching must be O(number of rules for domain).
- No disk IO during decision phase.

### 3.3 Persistence

Store on each message:

- Final decision (`status`)
- `quarantine_reason` (human-readable)
- `ingest_decision_meta` JSON:
  - rule_id
  - rule_type
  - match_field
  - matched_value
  - timestamp

---

## 4. Phase 3 — Admin Domain Policy UI

### 4.1 Backend Endpoints

Add admin-only endpoints:

- `GET /admin/domain-policies`
- `POST /admin/domain-policies`

All endpoints:

- Require authenticated session
- Require Admin PIN verification
- Log all changes to `admin_actions`

### 4.2 UI

Extend `admin_settings.html` or add a new admin page section:

For each domain:

- Domain name
- Mode selector (`OPEN`, `RESTRICTED`, `PAUSED`)
- Default action selector (`INBOX`, `QUARANTINE`, `DROP`)
- Last modified timestamp
- Explicit Save button

Changes apply only to new ingests.

---

## 5. Phase 4 — Address/Content Rule Management

### 5.1 Backend

Endpoints:

- `GET /admin/rules?domain=`
- `POST /admin/rules`
- `PUT /admin/rules/{id}`
- `DELETE /admin/rules/{id}`
- `POST /admin/rules/test`

Validation rules:

- Regex must compile successfully
- Invalid patterns rejected with clear error

### 5.2 UI

Admin rules table columns:

- Enabled toggle
- Type (ALLOW / BLOCK)
- Match field
- Pattern
- Action
- Priority
- Note
- Last modified

Actions:

- Add
- Edit
- Delete
- Reorder priority

Optional helper:

- Test rule against sample input

---

## 6. Phase 5 — Quarantine View

### 6.1 Backend

Endpoints:

- `GET /admin/quarantine`
- `POST /admin/quarantine/restore`
- `POST /admin/quarantine/delete`
- `POST /admin/quarantine/rule-from-selection`

Restore behavior:

- Change message `status` to `INBOX`
- Do not re-ingest or re-parse message

### 6.2 UI

Admin-only Quarantine view list fields:

- Received timestamp
- Recipient address
- Sender
- Subject
- Quarantine reason

Filters:

- Domain
- Sender domain
- Recipient local-part
- Date range

Bulk actions:

- Delete
- Restore
- Create ALLOW rule
- Create BLOCK rule

---

## 7. Phase 6 — Retention and Purge

Extend purge logic:

- Global inbox retention (existing)
- New quarantine retention (default 3 days)
- Optional per-domain override

Expired messages:

- Delete `.eml`
- Delete attachments
- Delete DB rows

Deletion must be batched.

---

## 8. Phase 7 — Metrics, Logging, Audit

### 8.1 Storage Metrics

Expose in admin UI:

- Inbox message count
- Quarantine message count
- Dropped message count (last 24h)
- Recent ingest rate
- Top sender domains (last 24h)

Charts optional. Counts mandatory.

### 8.2 Logging

Ingest decision log (per message):

- Message ID
- Decision
- Reason
- Recipient domain/local-part
- Sender domain
- Source IP (if available)

Admin audit log:

- Timestamp
- Actor (if available)
- Action
- Entity identifiers
- Before/after snapshots

Retention: 30 days.

---

## 9. Phase 8 — Hardening & Acceptance

Verify acceptance criteria:

1. OPEN delivers to Inbox
2. PAUSED blocks new Inbox entries
3. RESTRICTED requires ALLOW rules
4. BLOCK rules default to Quarantine
5. Quarantine restore works
6. Retention jobs purge correctly
7. All admin actions logged
8. UI remains responsive under load

No additional features beyond this list.

---

## 10. Codex Execution Instructions

When feeding this to Codex:

- Work phase by phase
- One logical commit per phase
- No speculative refactors
- Update README only if behavior changes
- If unsure → stop and leave a TODO

This file is the execution contract.
