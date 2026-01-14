# Quail 2.0 Public Internet Deployment Spec

This document defines the design and implementation scope for Quail 2.0 when
operating on the public internet. It supersedes earlier assumptions about a
shared, unauthenticated inbox and introduces user authentication, billing
integration, and outbound auth email delivery. This spec is written to support
iterative implementation with minimal diff size per step.

## 1. Scope and Non-Goals

### In Scope
- Implement DMARC enforcement for public internet deployment.
- Add authentication and role-based access control (RBAC).
- Add paid Power User onboarding (invite-only) with Stripe gating.
- Add collaborator invites for Power User tenants (up to 100 seats).
- Restrict public access to filtered inbox views only.
- Add outbound auth email via SMTP relay (local Postfix or external creds).
- Add additional message views (JSON, RAW, LINKs, SMTP_LOG) for power users/admins.

### Out of Scope (v1)
- Public sign-up without payment/invite.
- Per-tenant multi-admin roles beyond the Power User admin.
- Full multi-domain ownership per tenant (one domain per power user).
- General-purpose outbound email or notifications beyond auth flows.

## 2. Roles and Access Model

### Public (Unauthenticated)
- Must filter by localpart or full address before viewing any messages.
- Can view HTML and plaintext only.
- Cannot view attachments, JSON, RAW, LINKs, or SMTP_LOG.
- No sender filter or wildcard search.

### Power User (Paid Tenant Admin)
- Owns exactly one private domain.
- Full message views (HTML, text, attachments, JSON, RAW, LINKs, SMTP_LOG).
- Can invite collaborators and manage seats.
- Cannot delegate admin rights to collaborators.

### Collaborator (Sub-User)
- Full message views for the tenant domain.
- No deletions (individual or bulk).
- Cannot manage domains, invites, seats, or billing.

### Platform Admin
- Full access to all tenants, domains, and public inbox.
- Can revoke domains and disable tenants.
- Manages system-wide settings and audit access.

## 3. Public Inbox Access Rules

- Public inbox uses a fixed, single domain.
- Public access is filter-first: no inbox list is shown until a filter is set.
- Filter accepts localpart or full address; normalized to lowercase.
- Wildcard support is disabled for public users.
- Sender-based filters are not available for public users.

## 4. Authentication and Identity

### User Identity
- Usernames are email addresses and are unique.
- Accounts are created only via invite tokens.
- There is no public invite request form.

### Invite Tokens
- Required to access signup form (Power User admin and collaborators).
- Single-use; 24-hour TTL; bound to a specific email address.
- Only one active invite per email; sending a new invite invalidates the prior token.

### Password Reset
- Uses outbound email.
- If the account is unconfirmed, the reset flow re-issues the invite token.
- Responses are generic to prevent account enumeration.
- Only one active reset token per account; new tokens invalidate old ones.

## 5. Outbound Auth Email

- Sending is limited to invite and password reset email.
- SMTP relay options:
  - Local Postfix relay.
  - External SMTP credentials (for example, SendGrid SMTP relay).
- Configured via admin UI; stored in server-side configuration.
- From address: `noreply@quail.yourdomain.com`.

## 6. Billing and Subscription Gating (Stripe)

### Payment Flow
- User clicks "Unlock Premium Features" from the public inbox.
- Redirect to Stripe Checkout for subscription.
- On successful payment, send invite email to the paid email address.
 - Power user admins can invite collaborators from their dashboard.

### Subscription State
- Subscription is paid upfront for the period (monthly/yearly).
- Cancellation stops renewal, but service remains active through the paid period.

### Access After Expiration
- Tenant login remains available.
- Ingest for the tenant domain is disabled after the paid period ends.
- Tenant message data is retained for 14 days after expiration, then purged.
- Tenant cannot change domain or invite new collaborators after expiration.

### Storage and Sync
- Store Stripe customer, subscription, tier, and status in local DB.
- Stripe webhooks are the source of truth; local DB is kept in sync.

### Seats and Retention Upgrades
- Default collaborator cap: 10 seats; purchasable up to 100 seats.
- Power user retention default: 3 months.
- Retention upgrades: 6 or 12 months.
- Billing tiers are described in product copy (not separate Stripe price tiers).

## 7. Domain Management

- Power user admin can set a single domain.
- Domain auto-approval with warnings (no hard block).
- Suggested checks (warnings only):
  - Domain has MX records.
  - MX points to the Quail host.
- Operator guidance should mention optional SPF and DMARC alignment for the tenant.
- Admin can revoke domains at any time.

## 8. DMARC Enforcement

- Required for public internet deployment.
- DMARC failure results in QUARANTINE (never DROP by default).
- DMARC pass allows normal ingest.
- DMARC result is stored in message metadata and shown to admins.

## 9. Retention Policy

- Public inbox retention: 10 minutes.
- Power user retention: 3 months default; 6 or 12 months via upgrades.
- Audit log retention: 1 year; admin can delete manually.
- Post-expiration retention: 14 days after paid period ends, then purge.

## 10. Message Views and Features

- Public: HTML + plaintext only.
- Power user/admin: HTML, text, attachments, JSON, RAW, LINKs, SMTP_LOG.
- Collaborators: same views as power user admin, but no deletion actions.
- Power users and collaborators can filter by sender; public users cannot.
- Power users can use wildcard search within their own tenant scope.
- SMTP_LOG view exposes ingest decision metadata and SMTP context captured during ingest.
- LINKs view shows extracted URLs only.

### Filtering Syntax
- Public users: localpart or full address only (no `FROM:` syntax).
- Power users and collaborators: support `FROM:` for sender filtering.
- Wildcard searches are allowed only for power users and collaborators.

## 11. UI and UX Changes

- Replace admin PIN unlock with login form.
- Add "Unlock Premium Features" CTA on public inbox index.
- Add payment flow page (Stripe Checkout redirect).
- Add invite and collaborator management screens for power user admin.
- Add seat purchase and retention upgrade controls for power user admin.
- Add settings for SMTP relay credentials in admin UI.
- Add new message view tabs (JSON, RAW, LINKs, SMTP_LOG).
- Public inbox default state is empty until a filter is applied.
- Add "clear" control at the bottom of recent inbox list (text-only).
- Add client-side tag filters stored in local browser session storage.
- Improve admin settings layout (low priority; design guidelines required).

## 12. Data Model (Conceptual)

Tables and key fields (names are indicative):
- `users`: id, email, password_hash, role, owner_id, created_at, disabled_at
- `user_invites`: id, email, role, token_hash, expires_at, consumed_at, issued_by
- `password_resets`: id, user_id, token_hash, expires_at, consumed_at
- `tenants`: id, owner_user_id, domain, status, seat_limit, retention_days
- `subscriptions`: id, tenant_id, stripe_customer_id, stripe_subscription_id,
  period_end, status, seats, retention_days
- `messages`: add tenant_id (owner scope), public_localpart
- `audit_actions`: add actor_user_id

## 13. Security Controls

- Rate limit login, invite issuance, and password reset requests.
- Store tokens as hashes; never store raw tokens.
- Session cookies: httpOnly, secure in production, short TTL.
- Audit log for auth events and tenant admin actions.

## 14. Operational Changes

- Postfix transport maps updated when a tenant domain is set.
- Public inbox domain is fixed and always enabled.
- Ingest pipeline must tag messages with tenant ownership or public scope.
- Subscription status gates ingest for tenant domains.
- Ingest must drop tenant mail when the paid period ends and log the decision.

## 15. Migration and Compatibility

- Existing data is disposable; no migration required.
- Admin PIN flow is deprecated and replaced by login.
- Feature flags should gate new behavior until fully deployed.

## 16. Implementation Sequence (Iterative)

Each phase should be a small, reviewable diff. Do not remove existing behavior
until a phase fully replaces it.

### Phase 1: Auth Foundation
- Add user tables and session handling.
- Implement login and admin role access.
- Keep existing public inbox behavior unchanged (feature flag).

### Phase 2: Outbound Auth Email
- Add SMTP relay configuration and email templates.
- Implement invite and password reset flow with token storage.
- Keep invites admin-only until billing integration is ready.

### Phase 3: Stripe Billing Gate
- Add Stripe webhook sync and subscription records.
- Add "Unlock Premium Features" CTA and checkout redirect.
- Auto-issue Power User admin invite on successful payment.
 - Leave checkout presentation as a Stripe redirect unless a later decision is made to embed it.

### Phase 4: Tenant Domain Ownership
- Add tenant model and domain assignment.
- Update ingest to tag tenant ownership.
- Add admin tools to revoke domains.

### Phase 5: Collaborators and Seats
- Add collaborator invites and seat limits.
- Enforce collaborator permissions (no deletions or admin actions).

### Phase 6: Public Access Restrictions
- Require public inbox filter before listing messages.
- Remove wildcard support for public users.
- Restrict public views to HTML/text only.
 - Add the "clear" control for recent inboxes.

### Phase 7: DMARC Enforcement
- Add DMARC evaluation and quarantine on failure.
- Surface DMARC results in message metadata for admins.

### Phase 8: Additional Message Views
- Add JSON, RAW, LINKs, and SMTP_LOG for power users/admins.
- Keep public view limited to HTML/text.
 - Add sender filter for power users and collaborators.

### Phase 9: Retention Tier Enforcement
- Apply tenant retention settings and post-expiration purge.
- Add 14-day post-expiration purge behavior.

## 17. Acceptance Criteria (Per Phase)

Each phase is complete when:
- Existing functionality remains stable behind feature flags.
- Role permissions are enforced for new paths.
- Auth emails are sent only via configured SMTP relay.
- Stripe webhook events update local subscription state correctly.
- Public inbox remains non-enumerable without a filter.
- DMARC failures are quarantined, not dropped.
- Power users can filter by sender; public users cannot.
