# Project Status

## Current Version

0.1.0

## Overview

The initial repository scaffolding and ingest pipeline are in place. Retention purge job and admin settings form are implemented, while the broader FastAPI UI and installation/upgrade automation are still stubbed with TODOs【819940561035949†L8-L10】.

## Known Issues

- The full web UI for browsing messages and managing settings is incomplete.
- Install and upgrade scripts may require additional hardening and error handling.
- No automated tests are present; coverage is effectively zero.
- Admin PIN setup flow is manual and undocumented.

## Next Milestones

- Implement the complete FastAPI UI, including inbox and message detail views.
- Finish the install and upgrade automation to meet the idempotent requirements【104907567664902†L190-L199】.
- Add automated tests for ingest, UI and retention.
- Implement a supported flow for setting the initial admin PIN【819940561035949†L30-L33】.
