"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from quail import db
from quail.ingest import DEFAULT_ALLOWED_MIME_TYPES, SETTINGS_ALLOWED_MIME_KEY
from quail.settings import get_settings

from quail.logging_config import configure_logging

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _is_admin(request: Request) -> bool:
    if hasattr(request.state, "is_admin"):
        return bool(request.state.is_admin)
    # TODO: implement admin PIN session handling.
    return False


def _normalize_mime_list(value: str) -> str:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    return ",".join(items)


@app.on_event("startup")
async def _startup() -> None:
    configure_logging()
    settings = get_settings()
    db.init_db(settings.db_path)


@app.get("/")
async def inbox(request: Request) -> object:
    settings = get_settings()
    include_quarantined = _is_admin(request)
    messages = list(db.list_messages(settings.db_path, include_quarantined))
    return templates.TemplateResponse(
        "inbox.html",
        {"request": request, "messages": messages, "is_admin": include_quarantined},
    )


@app.get("/admin/settings")
async def admin_settings(request: Request) -> object:
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required.")
    settings = get_settings()
    allowed = db.get_setting(settings.db_path, SETTINGS_ALLOWED_MIME_KEY)
    if not allowed:
        allowed = ",".join(DEFAULT_ALLOWED_MIME_TYPES)
    return templates.TemplateResponse(
        "admin_settings.html",
        {
            "request": request,
            "allowed_attachment_mime_types": allowed,
        },
    )


@app.post("/admin/settings")
async def update_admin_settings(
    request: Request,
    allowed_attachment_mime_types: str = Form(""),
) -> object:
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required.")
    settings = get_settings()
    normalized = _normalize_mime_list(allowed_attachment_mime_types)
    if not normalized:
        normalized = ",".join(DEFAULT_ALLOWED_MIME_TYPES)
    db.set_setting(settings.db_path, SETTINGS_ALLOWED_MIME_KEY, normalized)
    return RedirectResponse("/admin/settings", status_code=HTTP_303_SEE_OTHER)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
