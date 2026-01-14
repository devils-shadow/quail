# Project Status

## Current Version

0.3.5-beta.2

## Overview

Quail is in active internal use with a complete inbox UI, admin workflows, and
ingest/purge automation. HTML rendering is available via a sandboxed iframe,
quarantine management is live, and retention policies are configurable.
WebSocket inbox updates are enabled by default with polling fallback.

## Known Issues

- DMARC support is not implemented (required for internet-facing deployments).
- FastAPI `on_event` startup handler and Starlette `TemplateResponse` signature
  deprecations are pending migration; see `docs/DEPRECATIONS.md`.

## Next Milestones

- Evaluate DMARC integration for broader public deployment.
- Expand automated coverage and diagnostics for CI.
- Plan a low-risk migration to FastAPI lifespan handlers and updated
  `TemplateResponse` signatures.
