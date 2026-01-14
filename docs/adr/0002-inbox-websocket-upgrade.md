# ADR 0002: Inbox WebSocket Upgrade

*Status:* accepted

## Context

The inbox UI currently uses ETag-aware polling to refresh data. This creates
continuous background requests and limits the responsiveness of updates. We
want to move toward push-based updates while preserving stability and fallback
behavior.

## Decision

Adopt a WebSocket-based inbox update channel with a polling fallback:

- Add `/ws/inbox` for real-time updates by inbox filter.
- Send an initial snapshot followed by deltas.
- Keep polling as a fallback when sockets are unavailable.
- Start with a single-process in-memory broadcaster; add a broker only if
  multi-worker deployments are required.

Implementation details and historical hardening notes live in
`docs/archive/WEBSOCKET_INBOX_PLAN.md`.

## Consequences

**Positive**
- Near real-time updates with reduced background requests.
- Graceful fallback preserves current behavior.

**Negative**
- Requires connection management and additional state handling.
- Multi-worker deployments need a shared broker to avoid missed updates.

## Alternatives Considered

- Continue polling only: rejected due to background traffic and lag.
- Server-sent events (SSE): rejected due to limited bidirectional control and
  less flexible reconnection handling.
