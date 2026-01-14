# ADR 0007: DMARC Enforcement for Public Internet Deployment

*Status:* proposed

## Context

Quail is intended for public internet deployment and must implement DMARC
validation to reduce spoofing and align with operational expectations.

## Decision

Implement DMARC evaluation during ingest. Messages that fail DMARC are
quarantined, not dropped. DMARC results are stored with message metadata and
exposed to admins.

## Consequences

- Adds DNS and policy evaluation to the ingest pipeline.
- Increases metadata storage requirements.
- Introduces a new quarantine trigger beyond attachment and policy rules.

## Alternatives Considered

- No DMARC enforcement for public deployments.
- Drop DMARC-failing messages instead of quarantining.
- Enforce DMARC only for specific domains.
