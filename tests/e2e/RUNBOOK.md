# E2E Runbook

## Prerequisites

- Quail is running locally on `http://127.0.0.1:8000` via systemd.
- Python environment has the E2E dependencies installed.
- Playwright is installed and Chromium is available.

Install Playwright for E2E:

```bash
python3 -m venv .venv-e2e
./.venv-e2e/bin/python -m pip install -r tests/e2e/requirements.txt
./.venv-e2e/bin/python -m playwright install chromium
```

## Smoke Tests

```bash
BASE_URL=http://127.0.0.1:8000 QUAIL_E2E_ADMIN_PIN=<ADMIN_PIN> \
  ./.venv-e2e/bin/python -m pytest tests/e2e
```

## Visual Baselines

```bash
BASE_URL=http://127.0.0.1:8000 \
  ./.venv-e2e/bin/python tests/e2e/capture_baselines.py --update
```

Baselines are written to `tests/e2e/baselines/`.

## Perf Baseline

```bash
BASE_URL=http://127.0.0.1:8000 \
  ./.venv-e2e/bin/python tests/e2e/capture_perf.py \
  --out tests/e2e/artifacts/perf_baseline.json
```

Perf output is stored at `tests/e2e/artifacts/perf_baseline.json`.

## Notes

- Tests expect at least one inbox message to exist.
- Admin coverage includes unlock flow and admin settings page render only.
- Attachment and quarantine coverage is not included in local E2E runs.
