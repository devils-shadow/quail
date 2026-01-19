# Testing

Quail keeps tests fast and deterministic. Most coverage uses pytest with the FastAPI
TestClient, so no systemd services or Postfix are required for local runs.

## Test groups

Tests are tagged with markers:

- `unit`: pure logic or database tests.
- `api`: FastAPI endpoints exercised via TestClient.
- `integration`: multi-module or persistence-heavy paths.
- `slow`: heavy or long-running checks (reserved for scheduled CI).

## Local runs

Run the standard suite (mirrors CI):

```bash
pytest -m "not slow" -ra
```

Run a focused subset:

```bash
pytest -m unit -ra
pytest -m api -ra
pytest -m integration -ra
```

## CI expectations

CI runs the main suite on every push with `-m "not slow"` and schedules a nightly
job for integration/slow tests. Use markers to keep quick feedback loops while
retaining deeper coverage in scheduled runs.

## Local E2E (Playwright)

Quail includes local Playwright-based E2E smoke coverage under `tests/e2e/`.
These tests target a running local service and validate the inbox/message UI,
theme persistence, and refresh health.

Requirements:
- A running local Quail service at `http://127.0.0.1:8000`.
- Playwright dependencies installed (`sudo /opt/quail/.venv-e2e/bin/playwright install-deps`
  if needed).
- Chromium installed via Playwright.

Recommended setup (local-only):

```bash
python3 -m venv .venv-e2e
./.venv-e2e/bin/python -m pip install -r tests/e2e/requirements.txt
./.venv-e2e/bin/python -m playwright install chromium
```

Run the E2E suite:

```bash
BASE_URL=http://127.0.0.1:8000 QUAIL_E2E_ADMIN_PIN=<ADMIN_PIN> \
  ./.venv-e2e/bin/python -m pytest tests/e2e
```

Baseline screenshots and perf capture commands are documented in
`tests/e2e/RUNBOOK.md`.

## CSS bundle updates

Quail serves a bundled stylesheet from `quail/static/quail.css`. If you edit any
CSS partials under `quail/templates/partials/styles/`, rebuild the bundle and
restart the service so the cache-buster updates:

```bash
make css-bundle
sudo systemctl restart quail
```

Or in one step:

```bash
make css-bundle-restart
```

The test suite includes a bundle guard (`tests/test_css_bundle.py`) that fails
if `quail/static/quail.css` is stale or missing.
