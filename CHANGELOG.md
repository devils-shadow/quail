# Change Log

All notable changes to this project will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

- None.

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
