# Change Log

All notable changes to this project will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Added spam mitigation phase 1 schema tables and message metadata columns.
- Implemented phase 2 deterministic ingest decisions with policy/rule metadata.
- Added admin domain policy management endpoints and UI controls.
- Added admin address/content rule CRUD endpoints, validation, and settings UI.
- Added admin quarantine view with filters and bulk restore/delete/rule creation actions.
- Added quarantine retention settings with optional per-domain overrides in purge logic.
- Added ingest decision logging, admin audit detail fields, and ingest visibility metrics in the admin UI.
- Added purge retention for admin audit entries (30 days).
- Added pytest to requirements to run the test suite locally.
- Added Postfix transport map configuration and domain list support to `install.sh`.

### Fixed

- Ensured Postfix ingest uses the Quail virtual environment interpreter with a clear error when missing.
- Updated Postfix install configuration to use relay domains with transport maps instead of virtual aliases, preserving envelope recipients.
- Ensured the Postfix ingest pipe sets `PYTHONPATH` so Quail runs from the source tree without packaging.

## [0.1.0] - 2026-01-09

### Added

- Initial repository scaffolding, including core package layout and FastAPI service.
- Ingest pipeline for storing raw `.eml` files and metadata.
- Retention purge job with systemd timer.
- Admin settings form and PIN‑gated UI.
- Installation (`install.sh`) and upgrade (`upgrade.sh`) scripts with basic functionality.
