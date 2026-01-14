# Deprecations and Migration Notes

This document tracks framework deprecations that affect Quail and provides a
minimal migration plan. It is intended for future LLM or human work; no behavior
changes should be made without explicit approval.

## FastAPI startup events (`on_event`)

### What changed

FastAPI is deprecating `@app.on_event("startup")` in favor of lifespan handlers.
Quail currently uses `on_event` to initialize logging, the database, and default
settings.

### Risk

Low today, but future FastAPI releases may remove `on_event`, causing startup
errors.

### Minimal migration plan (no behavior change)

1. Add a lifespan context manager and move the current startup logic into it.
2. Remove the `@app.on_event("startup")` function.
3. Ensure the same initialization order is preserved.

Snippet (structure only, preserve existing calls):

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    db.init_db(settings.db_path)
    _init_settings(settings.db_path)
    yield

app = FastAPI(title="Quail", lifespan=lifespan)
```

## Starlette `TemplateResponse` signature

### What changed

Starlette prefers `TemplateResponse(request, "name.html", context)` instead of
`TemplateResponse("name.html", context)`. Warnings are raised in tests and CI.

### Risk

Low today, but future Starlette releases may enforce the new signature.

### Minimal migration plan (mechanical change)

1. Replace all `TemplateResponse("template.html", {...})` calls with
   `TemplateResponse(request, "template.html", {...})`.
2. Keep context dictionaries identical, including `"request": request`.
3. Re-run the test suite to confirm no template regressions.

Snippet (before/after):

```python
# before
return templates.TemplateResponse("message.html", {"request": request, ...})

# after
return templates.TemplateResponse(request, "message.html", {"request": request, ...})
```

## Validation checklist

- CI warnings about `on_event` and `TemplateResponse` are cleared.
- No change to behavior or rendered HTML output.
- Admin/login flows and message rendering pages still load normally.
