# ADR 0002: Quarantine Retention Overrides

*Status:* accepted

## Context

Phase 6 of the spam mitigation plan calls for separate retention windows for quarantined
messages, plus optional per-domain overrides. The existing purge job only used the global inbox
retention period. We need to extend purge behavior without introducing external services or new
datastores.

## Decision

Add a new `quarantine_retention_days` setting and store optional per-domain quarantine retention
overrides on `domain_policy`. Update the purge job to apply retention by message status and to
delete associated `.eml` files and attachments in batches.

## Consequences

- Operators can shorten quarantine retention while keeping inbox retention stable.
- Domain-specific overrides are supported without adding new tables.
- The purge job now evaluates per-message retention, which adds a small amount of logic to the
  batch deletion loop.

## Alternatives Considered

- A dedicated quarantine retention table: rejected to keep the schema minimal and aligned with
  existing domain policy controls.
- Retaining the single retention window: rejected because it does not meet the Phase 6
  requirements.
