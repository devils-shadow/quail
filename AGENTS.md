# Repository Guidelines

This document defines **how Codex and human contributors should work with Quail in a local WSL-based development environment** where Quail is **installed and managed via systemd**, not run manually with uvicorn.

These rules exist to prevent configuration drift, port conflicts, accidental architectural violations, and UI regressions caused by overly broad CSS changes.

---

## Core Operating Mode (Read This First)

**Quail is managed exclusively via `systemctl`.**

- The application is installed using `install.sh`
- Runtime is controlled by a systemd service (`quail.service`)
- The service owns port `127.0.0.1:8000`
- Manual `uvicorn` invocation is **not used** in this environment

Any attempt to start Quail manually while the service is running will result in port conflicts and undefined behavior.

---

## Project Structure & Module Organization

Directories relevant for UI-focused work:

- `quail/` – Core application code
  - `web.py` – FastAPI routes and template wiring (touch sparingly)
- `quail/templates/` – **Primary UI development surface**
- `config/` – Runtime configuration (read-only unless instructed)
- `tests/` – Test suite (out of scope for UI iteration)

Out of scope for local Codex work:

- `postfix/`
- `systemd/`
- `scripts/`
- `install.sh`, `upgrade.sh`

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

- Template changes may appear on browser refresh, but **restart is the authoritative way** to ensure changes are applied
- Do not attempt to use `uvicorn --reload`
- Do not start a second server manually

---

## Coding Style & Naming Conventions

- Python is formatted with **black** and linted with **ruff**
- Line length: 100 characters
- Follow existing naming and layout conventions
- HTML templates should be minimal, readable, and consistent
- Avoid introducing JavaScript unless already present in the file

---

## UI Layout Rules (Strict)

These rules exist because layout regressions are easy to introduce and hard to notice in review.

### Scope and Safety

- Prefer **page-scoped selectors** (e.g. `.admin-page .form__grid`) over global rules
- Do **not** change global base classes (`.card`, `.button`, `.input`, etc.) unless:
  - the change is backward-compatible, and
  - you have verified at least one other page using the same class
- Avoid layout changes in `layout.html` unless explicitly instructed

### Grid Discipline

When editing admin or settings-style forms:

- Use **one consistent grid** across related sections (Core settings, Domain policies, Add policy)
- Use the existing `.form__grid` layout
- Keep `row-gap` and `column-gap` identical across those sections
- Avoid mixing grids and ad-hoc flex layouts inside the same card

### Width Discipline

- Do **not** let fields stretch just because horizontal space exists
- Inputs and selects should share the **same visual width** per column
- Prefer fixed or capped column widths (for example using `minmax(...)`)
- Avoid per-field improvisation with large column spans
- If a row has fewer fields than columns, leave empty space instead of stretching fields

Short-value fields (PINs, small numbers) must never expand to full-card width.

### Spacing Discipline

- Titles, fields, and buttons must never touch card edges
- Use consistent inner padding via a clear structure (for example `card__header` and `card__body`)
- Vertical spacing between fields must be consistent across sections
- Action buttons must be placed in a consistent container (for example `card__actions`)

### Action Buttons

- Buttons must be visually scoped by label, not position alone
  - Example: “Save core settings”, “Save domain”, “Add domain policy”
- Buttons must have clear padding and separation from surrounding content

### Acceptance Checks

Before considering a layout change complete:

- Core settings and Domain policies align to the same grid and gutters
- Field widths look intentional and consistent
- No field appears absurdly wide relative to its purpose
- Buttons are padded, aligned, and clearly scoped
- No unintended changes appear on unrelated pages

**If unsure how to implement a new or modified admin form, copy an existing admin form section that already looks correct and adapt it, rather than inventing a new layout pattern.**

---

## Testing Guidelines

- Tests use `pytest`
- UI changes generally do not require new tests
- Never remove or weaken existing tests
- Do not claim tests were run unless they actually were

---

## Commit & Pull Request Guidelines

All changes are pushed to the `dev` branch.

Commits should:

- Be small and UI-focused
- Avoid unrelated refactors

Pull requests must:

- Clearly describe UI changes
- Include screenshots or descriptions when UI is affected
- Avoid backend, ingest, or configuration changes unless explicitly requested

---

## Codex-Specific Rules (Strict)

Codex acts as a **UI assistant only**.

Codex **must not**:

- Start or manage application processes
- Invoke `uvicorn` directly
- Modify Postfix, systemd units, or service files
- Change ingest, purge, retention, or database schema logic
- Introduce outbound email functionality

Codex **may**:

- Edit files under `quail/templates/`
- Make small, UI-driven changes to `quail/web.py`
- Improve layout, accessibility, and UX clarity

When uncertain, Codex must ask before acting.

---

## Architecture Decision Records (ADRs)

Major architectural changes should be captured in `docs/adr/`. Use the template
in `docs/adr/0000-template.md` and keep ADRs brief.

Current ADRs include:

- `docs/adr/0001-html-rendering-model.md`
- `docs/adr/0002-inbox-websocket-upgrade.md`

---

## Web Codex Notes

This repository is primarily operated in a local WSL environment. If Codex is
running in a web sandbox (no systemd access), avoid service management and focus
on documentation or static UI edits only. When in doubt, ask before acting.

---

## Guiding Principle

Quail prioritizes **operational safety**, **predictable behavior**, and **boring correctness**.

UI improvements must never compromise those values.

