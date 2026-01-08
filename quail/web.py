"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from quail import db
from quail.logging_config import configure_logging
from quail.settings import SETTINGS_RETENTION_DAYS_KEY, get_retention_days, get_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
async def _startup() -> None:
    configure_logging()
    settings = get_settings()
    db.init_db(settings.db_path)


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    settings = get_settings()
    retention_days = get_retention_days(settings.db_path)
    return templates.TemplateResponse(
        request,
        "admin_settings.html",
        {"retention_days": retention_days, "error": None},
    )


@app.post("/admin/settings", response_class=HTMLResponse)
async def admin_settings_update(
    request: Request, retention_days: int = Form(..., ge=1)
) -> HTMLResponse:
    settings = get_settings()
    # TODO: Require admin PIN session before updating settings.
    if retention_days < 1:
        return templates.TemplateResponse(
            request,
            "admin_settings.html",
            {"retention_days": retention_days, "error": "Retention must be at least 1 day."},
            status_code=400,
        )
    db.set_setting(settings.db_path, SETTINGS_RETENTION_DAYS_KEY, str(retention_days))
    return RedirectResponse(url="/admin/settings", status_code=303)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
