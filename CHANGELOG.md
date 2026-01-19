# Change Log

All notable changes to this project will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Nothing yet.

## [0.4.0] - 2026-01-19

### Added

- Playwright-based E2E smoke tests, visual baselines, and perf capture with a runbook.
- CSS bundle workflow with cache-busted `quail.css` and Makefile targets for rebuilds.
- Static inbox and layout JS files extracted from templates.
- Admin UI CSRF tokens for state-changing requests.
- Desktop notifications toggle and dynamic tab titles for inbox status.

### Changed

- Inbox, message view, admin settings, and quarantine templates are split into partials.
- Layout shell and admin form patterns moved into macros/partials.
- `make test` now rebuilds the CSS bundle when partials change.
- install.sh initializes the admin PIN from `QUAIL_ADMIN_PIN` when unset.
- upgrade.sh can reset the admin PIN when `QUAIL_RESET_PIN=true`.
- Admin session cookies are marked Secure when HTTPS is detected (including `X-Forwarded-Proto`).
- Inbox list pages use internal scrolling with sticky headers and aligned list layouts.
- Inbox copy updated (Received Mail title, QA subtitle, filter placeholder) with new empty-state messaging.
- WebSocket inbox adds app-level ping/pong keepalive with jittered reconnect backoff.
- WebSocket inbox loop retries after unexpected errors to keep live updates running.
- Docs clarify that HTML is rendered as sent inside a sandboxed iframe (no sanitization).

### Fixed

- Attachment downloads return 404 when files are missing on disk.

## [0.3.5] - 2026-01-14

### Added

- WebSocket inbox updates with automatic fallback to polling and periodic timestamp refresh.
- WebSocket reconnect/backoff and drift detection for inbox updates.
- Origin allowlist support for WebSocket connections (`QUAIL_ALLOWED_ORIGINS`).
- Inbox event retention cleanup to keep event logs bounded.
- Interactive install and upgrade prompts (CI-safe) for required settings and PIN rotation.
- Optional install smoke test (`install.sh --smoke-test`).
- Admin ingest health summary on the settings page.

### Changed

- WebSocket inbox updates are enabled by default with `QUAIL_ENABLE_WS=true`.
- Upgrade flow can rotate the admin PIN via interactive prompt or `QUAIL_RESET_PIN=true`.

### Fixed

- Purge retention job uses a shared connection to avoid SQLite locking while logging events.
- WebSocket event loop row handling.
- Admin PIN validation and enforcement on first install.

## [0.3.0] - 2026-01-13

### Added

- Admin quarantine view with filters and bulk restore/delete plus rule creation.
- Domain policy management and address/content rule CRUD with validation.
- Ingest decision logging, admin audit entries, and ingest visibility metrics.
- Separate retention windows for inbox and quarantine, plus per-domain quarantine overrides.
- Full HTML rendering toggle with sandboxed iframe HTML view and HTML/text/attachments tabs.
- Inbox auto-refresh with ETag caching and receiver name column.
- Favicons for common platforms.
- pytest added to requirements for local test runs.
- Postfix transport map configuration and domain list support in install scripts.

### Changed

- Message detail layout uses fixed panel scrolling and desktop-tuned spacing.
- Minimal HTML emails inherit the app theme in dark mode for readability.
- install.sh now requires QUAIL_DOMAINS to be explicitly configured; upgrade warns if missing.

### Fixed

- Postfix ingest uses the Quail virtual environment interpreter with a clear error when missing.
- Postfix install configuration uses relay domains/transport maps and preserves envelope recipients.
- Ingest pipe sets PYTHONPATH so Quail runs from the source tree.
- Attachment download handling for message detail view.
- Optional tinycss2 dependency handling for HTML sanitization.

## [0.1.0] - 2026-01-09

### Added

- Initial repository scaffolding, including core package layout and FastAPI service.
- Ingest pipeline for storing raw `.eml` files and metadata.
- Retention purge job with systemd timer.
- Admin settings form and PIN‑gated UI.
- Installation (`install.sh`) and upgrade (`upgrade.sh`) scripts with basic functionality.
