# ADR 0003: Authentication and Role-Based Access Control

*Status:* proposed

## Context

Quail 2.0 requires user authentication, role-based access control, and tenant
scoping for public internet deployment. The existing admin PIN model is
insufficient for paid tenants, collaborator access, and permission separation.

## Decision

Implement user accounts with roles (Public, Power User admin, Collaborator,
Platform Admin), session-based authentication, and invite-only account
creation. Replace the admin PIN workflow with role-based access. Invite tokens
are single-use, expire after 24 hours, and are bound to the target email.

## Consequences

- Introduces new authentication and session management responsibilities.
- Requires new user, invite, and session data models.
- Deprecates the admin PIN flow and updates UI accordingly.
- Enables tenant-specific permissions and collaborator access.

## Alternatives Considered

- Keep the admin PIN unlock model for all privileged actions.
- Implement open public sign-up without invites.
- Use a shared tenant password instead of per-user accounts.
