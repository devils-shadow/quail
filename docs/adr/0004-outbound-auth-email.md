# ADR 0004: Outbound Auth Email via SMTP Relay

*Status:* proposed

## Context

Invite delivery and password resets require outbound email. The current Quail
constraints prohibit sending email and must be updated for public internet
operation with paid users.

## Decision

Add outbound email capability limited to authentication flows. Support SMTP
relay via local Postfix or external SMTP credentials. Configure via the admin
UI. Use `noreply@quail.yourdomain.com` as the sender address.

## Consequences

- Violates the prior "never send email" constraint and requires updated
  documentation and operational guidance.
- Requires secure storage of SMTP credentials.
- Adds outbound email delivery and failure logging.

## Alternatives Considered

- Manual invite distribution and password resets.
- External email service only (no local relay option).
- Disable password reset and require admin intervention.
