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
