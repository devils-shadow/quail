# Quail Codex Guide

This document acts as the "Codex Constitution" for the **Quail** project. All tasks undertaken by the Codex agent or any automated tooling must comply with these guidelines in addition to the authoritative context defined in `QUAIL_CODEX_CONTEXT.md`. Read this file before performing any work and refer back whenever in doubt.

## Project Purpose

Quail is a self‑hosted, **receive‑only email sink** for CST QA/dev teams. It accepts inbound email on the `m.cst.ro` domain and exposes a private, shared inbox UI available only over VPN or explicitly configured private networks【104907567664902†L10-L16】. Quail **does not send email** under any circumstances and is designed for low volume, single‑operator environments【104907567664902†L17-L20】. No SaaS services are used and there are no per‑user accounts; all viewers share a common inbox【104907567664902†L17-L31】. The full specification, including non‑negotiable requirements and architecture, lives in `QUAIL_CODEX_CONTEXT.md`.

## Definition of Done

A task is considered complete when:

- It satisfies the requirements in `QUAIL_CODEX_CONTEXT.md` without introducing any new requirements or assumptions.
- It includes any necessary configuration changes and documentation updates.
- It is accompanied by automated tests or evidence demonstrating that the change works.
- It leaves the repository in a buildable, lint‑clean state (`ruff` and `black` passing).
- It has been reviewed by a human supervisor and merged via a pull request.

Never mark a task as done if there are unresolved TODOs, broken tests, or undocumented changes.

## Non‑Goals

The following are explicitly **out of scope** and must never be attempted by the Codex agent:

- Sending outbound email or implementing SMTP clients【104907567664902†L17-L19】.
- Adding SaaS or external dependencies【104907567664902†L17-L19】.
- Creating per‑user accounts or changing the shared inbox model【104907567664902†L27-L31】.
- Deviating from the prescribed repository structure【104907567664902†L127-L173】.
- Modifying retention periods, admin PIN flow or other security‑critical defaults unless explicitly instructed.
- Large‑scale refactors or dependency upgrades without a clear reason.

## Workflow

1. **Create an Issue:** Every piece of work must begin with a GitHub issue using the `task` template. Clearly state the goal, acceptance criteria, out‑of‑scope items and verification steps.
2. **Branch & Implement:** Work on a feature or fix in a short‑lived branch. Follow the diff budget rule—prefer minimal diffs that touch only necessary files.
3. **Evidence Artifacts:** Produce evidence for your change: test output, screenshots of the UI (if applicable) and any logs or scripts needed to verify the behavior.
4. **Pull Request:** Open a pull request against the `dev` branch using the PR template. Fill out all sections (What, Why, How to test, Risk level, Files touched, Follow‑up tasks). Do not auto‑merge.
5. **Review & Merge:** A human supervisor reviews the PR. Only after review passes are you allowed to merge; never merge your own work without human approval.
6. **Documentation:** When behavior or configuration changes, update the README and relevant docs. Maintain `CHANGELOG.md` and `STATUS.md` to reflect what has changed.

## House Rules

- **Repository Layout:** Adhere to the directory structure defined in `QUAIL_CODEX_CONTEXT.md`【104907567664902†L127-L173】. Do not move or rename modules unless there is a documented ADR and approval.
- **Coding Style:** Use Python ≥3.11. Code must be formatted with `black` and linted with `ruff`. Line length is 100 characters as defined in `pyproject.toml`.
- **Dependencies:** Use the pinned versions in `requirements.txt`. Do not add new dependencies without justification and approval.
- **Minimal Diffs:** One PR should solve one problem. Avoid mass reformatting, dependency upgrades or large refactors unless specifically requested.
- **Tests:** Prefer small, deterministic tests. If no tests exist, create them; if creation is infeasible, provide manual verification steps in the PR.
- **Labels:** Use labels to track the state of issues: `needs-spec`, `ready-for-codex`, `in-progress`, `needs-human-review`, `blocked`, `ready-to-merge`.

## Safety Rails

- Never rewrite large subsystems or delete data without explicit approval.
- Never invent configuration values or flags【104907567664902†L223-L231】; if uncertain, leave a TODO with a safe default and document it.
- Always respect the "receive‑only" constraint【104907567664902†L17-L19】 and security rules like admin PIN rate‑limiting【104907567664902†L101-L106】.
- When in doubt, consult `QUAIL_CODEX_CONTEXT.md` or ask for clarification via an issue.

## Running and Testing

A single command developer experience is provided via the Makefile (see `Makefile`). Typical commands:

- `make venv` – create and populate a virtual environment.
- `make lint` – run `ruff` to check lint and `black` for formatting.
- `make test` – run the automated test suite with `pytest`.
- `make run` – start the FastAPI application locally via `uvicorn`.

For CI, a GitHub Actions workflow runs linting and tests on each push and pull request. See `.github/workflows/ci.yml` for details.

---

By following this guide you will help ensure that Codex remains a disciplined assistant and that the Quail repository stays maintainable and secure.
