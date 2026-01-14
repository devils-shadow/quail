# WebSocket Inbox Implementation Checklist

This checklist sequences the WebSocket inbox work with required prep tasks. It
is written for iterative implementation with minimal diffs and no breaking
changes. Each phase must preserve current behavior until explicitly replaced.

## Phase 0: Deployment Mode Clarity

**Objective:** Make deployment modes explicit and repeatable before adding real-time UI.

Checklist:
- Add a short "Modes" doc describing VPN VM mode vs reverse-proxy mode.
- Add `scripts/quail-mode` helper to switch `QUAIL_BIND_HOST` and restart Quail.
- Ensure defaults remain proxy-safe (bind to `127.0.0.1`).

Acceptance criteria:
- `scripts/quail-mode vpn` sets `QUAIL_BIND_HOST=0.0.0.0` in `/etc/quail/config.env` and restarts.
- `scripts/quail-mode proxy` sets `QUAIL_BIND_HOST=127.0.0.1` and restarts.
- The new doc explains both modes without requiring systemd overrides.

## Phase 1: Ingest Health Visibility

**Objective:** Surface ingest failures in the admin UI to avoid silent breakage.

Checklist:
- Add a DB table for ingest attempts (timestamp, status, error summary, rcpt).
- Update ingest pipeline to log success and failure.
- Add an "Ingest health" panel to admin settings showing recent attempts.
- Keep existing ingest metrics intact.

Acceptance criteria:
- When ingest fails (e.g., bad venv path), admin UI shows the failure and error cause.
- When ingest succeeds, admin UI shows recent successes.
- No changes to message ingest behavior or message schema beyond logging.

## Phase 2: Install Smoke Test

**Objective:** Validate end-to-end ingest during installation.

Checklist:
- Add `--smoke-test` (or env flag) to `install.sh`.
- Verify `quail.service` is active via `systemctl`.
- Verify Postfix transport maps include `quail:` for the configured domain.
- Send a test message via `swaks` and wait briefly for ingest.
- Print a clear pass/fail summary; exit non-zero on failure.

Acceptance criteria:
- Smoke test fails fast with actionable output if any step fails.
- Smoke test success confirms at least one message ingested.
- Default install behavior is unchanged when the flag is not used.

## Phase 3: WebSocket Inbox (Single Process)

**Objective:** Add WebSocket inbox updates with a safe fallback and opt-out flag.

Checklist:
- Implement `/ws/inbox` per `docs/WEBSOCKET_INBOX_PLAN.md`.
- Implement an in-memory connection manager keyed by inbox filter.
- Emit snapshot on connect; emit delta updates on ingest/admin/purge changes.
- Keep ETag polling as a fallback if WebSocket fails.
- Add a feature flag so polling-only remains available (`QUAIL_ENABLE_WS=false`).

Acceptance criteria:
- WebSocket connects and delivers a snapshot payload by default.
- Inbox updates without full-page reloads when new messages arrive.
- When WebSocket fails, polling resumes automatically.
- Admin/non-admin access rules match `/api/inbox` behavior.

## Phase 4: WebSocket Hardening

**Objective:** Improve resilience and avoid drift in real deployments.

Checklist:
- Add reconnect backoff and visibility-aware reconnect.
- Add drift detection and forced snapshot on mismatch.
- Validate behavior in VPN VM mode and reverse-proxy mode.
- Document operational notes and known limits in the WebSocket plan.

Acceptance criteria:
- Long-running tabs recover after disconnects without stale inbox data.
- Reconnect logic does not flood the server under failure conditions.
- Documentation reflects the final WebSocket behavior and fallback strategy.

## Implementation Notes

- Avoid breaking changes: keep polling in place until WebSockets are stable.
- Follow existing layout and naming conventions.
- Use the database only when required; keep WebSocket state in memory for the
  single-process baseline.
- Do not add multi-worker brokers unless explicitly required.
