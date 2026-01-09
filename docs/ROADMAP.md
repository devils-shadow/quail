# Roadmap

This roadmap outlines high‑level goals for the upcoming releases. Timeframes are aspirational and may change.

## Near Term

- **UI Completion:** Flesh out the web interface with inbox listing, message detail pages and administrative forms. Provide sanitized HTML rendering with toggle【819940561035949†L35-L40】.
- **Installation UX:** Finalize `install.sh` and `upgrade.sh` scripts to be idempotent, safe and fully automate OS configuration【104907567664902†L190-L210】.
- **Testing & CI:** Introduce automated tests for ingest, retention and the web UI. Expand CI to run these tests on each commit.
- **Admin PIN Flow:** Build a guided setup process for the initial admin PIN and document recovery procedures【819940561035949†L30-L33】.
- **Documentation:** Maintain and update the documentation set (architecture, runbook, glossary, ADRs) as features evolve.

## Longer Term

- **Attachment Management:** Allow admin‑controlled attachment types with quarantine review and safe preview features【104907567664902†L71-L78】.
- **Monitoring & Metrics:** Add logging and simple metrics to help operators monitor ingestion rates, storage usage and purge results.
- **Internationalization:** Consider localization for UI labels and messages if the user base expands beyond internal teams.
