# Repository Guidelines

This document defines **how Codex and human contributors should work with Quail in a local WSL-based development environment** where Quail is **installed and managed via systemd**, not run manually with uvicorn.

These rules exist to prevent configuration drift, port conflicts, and accidental architectural violations.

---

## Core Operating Mode (Read This First)

**Quail is managed exclusively via `systemctl`.**

* The application is installed using `install.sh`
* Runtime is controlled by a systemd service (`quail.service`)
* The service owns port `127.0.0.1:8000`
* Manual `uvicorn` invocation is **not used** in this environment

Any attempt to start Quail manually while the service is running will result in port conflicts and undefined behavior.

---

## Project Structure & Module Organization

Directories relevant for UI-focused work:

* `quail/` – Core application code

  * `web.py` – FastAPI routes and template wiring (touch sparingly)
* `quail/templates/` – **Primary UI development surface**
* `config/` – Runtime configuration (read-only unless instructed)
* `tests/` – Test suite (out of scope for UI iteration)

Out of scope for local Codex work:

* `postfix/`
* `systemd/`
* `scripts/`
* `install.sh`, `upgrade.sh`

---

## Running, Restarting, and Applying Changes

Quail is already running as a system service.

To apply changes:

```bash
sudo systemctl restart quail
```

To observe logs during startup or UI debugging:

```bash
sudo journalctl -u quail -f
```

Notes:

* Template changes may appear on browser refresh, but **restart is the authoritative way** to ensure changes are applied
* Do not attempt to use `uvicorn --reload`
* Do not start a second server manually

---

## Build and Test Commands

Tests can be run locally if needed:

```bash
make test
```

UI work does not require rebuilding or reinstalling Quail.

---

## Coding Style & Naming Conventions

* Python is formatted with **black** and linted with **ruff**
* Line length: 100 characters
* Follow existing naming and layout conventions
* HTML templates should be minimal, readable, and consistent
* Avoid introducing JavaScript unless already present in the file

---

## Testing Guidelines

* Tests use `pytest`
* UI changes generally do not require new tests
* Never remove or weaken existing tests
* Do not claim tests were run unless they actually were

---

## Commit & Pull Request Guidelines

All changes are pushed to the `dev` branch.

Commits should:

* Be small and UI-focused
* Avoid unrelated refactors

Pull requests must:

* Clearly describe UI changes
* Include screenshots or descriptions when UI is affected
* Avoid backend, ingest, or configuration changes unless explicitly requested

---

## Codex-Specific Rules (Strict)

Codex acts as a **UI assistant only**.

Codex **must not**:

* Start or manage application processes
* Invoke `uvicorn` directly
* Modify Postfix, systemd units, or service files
* Change ingest, purge, retention, or database schema logic
* Introduce outbound email functionality

Codex **may**:

* Edit files under `quail/templates/`
* Make small, UI-driven changes to `quail/web.py`
* Improve layout, accessibility, and UX clarity

When uncertain, Codex must ask before acting.

---

## Guiding Principle

Quail prioritizes **operational safety**, **predictable behavior**, and **boring correctness**.

UI improvements must never compromise those values.
