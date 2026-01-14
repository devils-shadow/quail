# ADR 0005: Stripe Billing Integration and Subscription Gating

*Status:* proposed

## Context

Power User access is paid and invite-only. Quail requires a billing system to
gate tenant provisioning, retention upgrades, and collaborator seats.

## Decision

Integrate Stripe Checkout for subscriptions and store subscription state in a
local database. Use Stripe webhooks as the source of truth. On successful
payment, issue a Power User admin invite. If the subscription ends, disable
ingest for the tenant domain and purge tenant data after 14 days.

## Consequences

- Introduces a dependency on Stripe webhooks and subscription state.
- Requires local storage of billing metadata and reconciliation logic.
- Adds paid feature gating and seat limits.

## Alternatives Considered

- Manual billing and admin-provisioned invites.
- On-demand Stripe API lookups without local storage.
- License-key based activation without Stripe integration.
