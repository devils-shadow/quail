# Change Log

All notable changes to this project will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Added spam mitigation phase 1 schema tables and message metadata columns.

## [0.1.0] - 2026-01-09

### Added

- Initial repository scaffolding, including core package layout and FastAPI service.
- Ingest pipeline for storing raw `.eml` files and metadata.
- Retention purge job with systemd timer.
- Admin settings form and PIN‑gated UI.
- Installation (`install.sh`) and upgrade (`upgrade.sh`) scripts with basic functionality.
