# Roadmap

This roadmap outlines high‑level goals for the upcoming releases. Timeframes are aspirational and may change.

## Legacy Track (Current Deployment)

### Near Term

- **DMARC Support:** Evaluate and implement DMARC validation for broader public deployments.
- **WebSocket Inbox Updates:** Implement real-time inbox refresh per `docs/WEBSOCKET_INBOX_PLAN.md`.
- **Operational Visibility:** Add lightweight service health/status and storage usage reporting.
- **Documentation:** Maintain and update the documentation set (architecture, runbook, glossary, ADRs) as features evolve.

### Longer Term

- **Attachment Management:** Allow admin‑controlled attachment types with quarantine review and safe preview features.
- **Monitoring & Metrics:** Add logging and simple metrics to help operators monitor ingestion rates, storage usage and purge results.
- **Internationalization:** Consider localization for UI labels and messages if the user base expands beyond internal teams.

## Quail 2.0 Track (Future)

Quail 2.0 is a longer-term effort that introduces authentication, tenant scoping,
billing integration, and public-internet hardening. See `docs/QUAIL_2_0_SPEC.md`
for the authoritative scope and phased delivery plan.

### Long Term

- **Auth and RBAC:** Invite-only accounts, collaborator access, and admin roles.
- **Billing Gate:** Stripe subscription gating and seat/retention upgrades.
- **Outbound Auth Email:** SMTP relay support for invites and resets.
- **Public Inbox Restrictions:** Filter-first access and limited public views.
- **DMARC Enforcement:** Quarantine DMARC failures and surface metadata in admin views.
