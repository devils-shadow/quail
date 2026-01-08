"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from quail import db
from quail.ingest import DEFAULT_ALLOWED_MIME_TYPES, SETTINGS_ALLOWED_MIME_KEY
from quail.settings import get_settings

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from quail import db
from quail.logging_config import configure_logging
from quail.security import hash_pin, verify_pin
from quail.settings import get_settings

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory="quail/templates")

_ADMIN_SESSION_COOKIE = "quail_admin_session"
_ADMIN_SESSION_TTL = timedelta(minutes=20)
_ADMIN_RATE_LIMIT_WINDOW = timedelta(minutes=15)
_ADMIN_RATE_LIMIT_MAX_ATTEMPTS = 5
from quail.settings import SETTINGS_RETENTION_DAYS_KEY, get_retention_days, get_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _get_admin_pin_hash(settings_db_path) -> str | None:
    return db.get_setting(settings_db_path, "admin_pin_hash")


def _get_session_state(settings_db_path) -> tuple[str | None, datetime | None]:
    token_hash = db.get_setting(settings_db_path, "admin_session_hash")
    expires_at_raw = db.get_setting(settings_db_path, "admin_session_expires_at")
    if not token_hash or not expires_at_raw:
        return None, None
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        return None, None
    return token_hash, expires_at


def _set_session_state(settings_db_path, token_hash: str, expires_at: datetime) -> None:
    db.set_setting(settings_db_path, "admin_session_hash", token_hash)
    db.set_setting(settings_db_path, "admin_session_expires_at", expires_at.isoformat())


def _clear_session_state(settings_db_path) -> None:
    db.set_setting(settings_db_path, "admin_session_hash", "")
    db.set_setting(settings_db_path, "admin_session_expires_at", "")


def _is_rate_limited(settings_db_path, source_ip: str, now: datetime) -> bool:
    state = db.get_rate_limit_state(settings_db_path, source_ip)
    if not state:
        return False
    try:
        window_start = datetime.fromisoformat(state["window_start"])
    except ValueError:
        db.clear_rate_limit_state(settings_db_path, source_ip)
        return False
    if now - window_start > _ADMIN_RATE_LIMIT_WINDOW:
        db.clear_rate_limit_state(settings_db_path, source_ip)
        return False
    return state["attempts"] >= _ADMIN_RATE_LIMIT_MAX_ATTEMPTS


def _record_rate_limit_failure(settings_db_path, source_ip: str, now: datetime) -> None:
    state = db.get_rate_limit_state(settings_db_path, source_ip)
    if not state:
        db.set_rate_limit_state(settings_db_path, source_ip, 1, now.isoformat())
        return
    try:
        window_start = datetime.fromisoformat(state["window_start"])
    except ValueError:
        db.set_rate_limit_state(settings_db_path, source_ip, 1, now.isoformat())
        return
    if now - window_start > _ADMIN_RATE_LIMIT_WINDOW:
        db.set_rate_limit_state(settings_db_path, source_ip, 1, now.isoformat())
        return
    attempts = state["attempts"] + 1
    db.set_rate_limit_state(settings_db_path, source_ip, attempts, window_start.isoformat())


def _reset_rate_limit(settings_db_path, source_ip: str) -> None:
    db.clear_rate_limit_state(settings_db_path, source_ip)


def _require_admin_session(request: Request) -> bool:
    settings = get_settings()
    token_hash, expires_at = _get_session_state(settings.db_path)
    if not token_hash or not expires_at:
        return False
    if expires_at < _now():
        _clear_session_state(settings.db_path)
        return False
    token = request.cookies.get(_ADMIN_SESSION_COOKIE)
    if not token:
        return False
    try:
        return verify_pin(token, token_hash)
    except Exception:
        return False
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


@app.get("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        "admin_unlock.html",
        {
            "request": request,
            "error": None,
            "pin_configured": bool(_get_admin_pin_hash(settings.db_path)),
        },
    )


@app.post("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock_submit(request: Request, pin: str = Form(...)) -> HTMLResponse:
    settings = get_settings()
    source_ip = _get_client_ip(request)
    now = _now()
    if _is_rate_limited(settings.db_path, source_ip, now):
        return templates.TemplateResponse(
            "admin_unlock.html",
            {
                "request": request,
                "error": "Too many attempts. Please wait before retrying.",
                "pin_configured": bool(_get_admin_pin_hash(settings.db_path)),
            },
            status_code=429,
        )

    stored_hash = _get_admin_pin_hash(settings.db_path)
    if not stored_hash:
        return templates.TemplateResponse(
            "admin_unlock.html",
            {
                "request": request,
                "error": "Admin PIN not configured. TODO: set admin PIN in settings.",
                "pin_configured": False,
            },
            status_code=400,
        )

    if verify_pin(pin, stored_hash):
        _reset_rate_limit(settings.db_path, source_ip)
        token = secrets.token_urlsafe(32)
        token_hash = hash_pin(token)
        expires_at = now + _ADMIN_SESSION_TTL
        _set_session_state(settings.db_path, token_hash, expires_at)
        db.log_admin_action(
            settings.db_path, "admin_unlock", source_ip, now.isoformat()
        )
        response = RedirectResponse(url="/admin/settings", status_code=303)
        response.set_cookie(
            _ADMIN_SESSION_COOKIE,
            token,
            max_age=int(_ADMIN_SESSION_TTL.total_seconds()),
            httponly=True,
            samesite="lax",
        )
        return response

    _record_rate_limit_failure(settings.db_path, source_ip, now)
    return templates.TemplateResponse(
        "admin_unlock.html",
        {
            "request": request,
            "error": "Invalid PIN.",
            "pin_configured": True,
        },
        status_code=401,
    )


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    if not _require_admin_session(request):
        return RedirectResponse(url="/admin/unlock", status_code=303)
    settings = get_settings()
    source_ip = _get_client_ip(request)
    db.log_admin_action(
        settings.db_path, "admin_settings_view", source_ip, _now().isoformat()
    )
    return templates.TemplateResponse(
        "admin_settings.html",
        {"request": request},
    )
