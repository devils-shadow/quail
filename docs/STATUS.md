# Project Status

## Current Version

0.3.0-beta.1

## Overview

Quail is in active internal use with a complete inbox UI, admin workflows, and
ingest/purge automation. HTML rendering is available via a sandboxed iframe,
quarantine management is live, and retention policies are configurable.

## Known Issues

- DMARC support is not implemented (required for internet-facing deployments).
- WebSocket inbox updates are planned; current refresh uses ETag-aware polling.

## Next Milestones

- Evaluate DMARC integration for broader public deployment.
- Implement WebSocket inbox updates per `docs/WEBSOCKET_INBOX_PLAN.md`.
- Expand automated coverage and diagnostics for CI.
