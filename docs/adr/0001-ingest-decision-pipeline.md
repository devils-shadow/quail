# ADR 0001: Deterministic ingest decision pipeline

*Status:* accepted

## Context

Quail needs a deterministic ingest decision pipeline to apply domain policies and address/content
rules that classify incoming messages as INBOX, QUARANTINE, or DROP, aligned with the spam
mitigation plan and the receive-only constraints in `QUAIL_CODEX_CONTEXT.md`.

## Decision

Implement a deterministic, ordered ingest decision function that loads domain policy and enabled
rules from SQLite, evaluates them in priority order, and stores decision metadata (`status`,
`quarantine_reason`, and JSON decision details) on each message.

## Consequences

- Ingest now records the policy/rule decision on every message, enabling later admin workflows.
- A new decision function must be tested and maintained alongside ingest.

## Alternatives Considered

- Deferring decisioning until the admin UI exists (rejected: would block Phase 2 requirements).
- Adding a heuristic or scoring system (rejected: out of scope for Quail).
