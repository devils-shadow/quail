"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
import secrets
from typing import Iterable

from fastapi import FastAPI, Form, HTTPException, Request
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


ADMIN_PIN_HASH_KEY = "admin_pin_hash"
RETENTION_DAYS_KEY = "retention_days"
ALLOW_HTML_KEY = "allow_html"
ALLOWED_MIME_TYPES_KEY = "allowed_attachment_mime_types"
DEFAULT_ALLOWED_MIME_TYPES = "application/pdf"
DEFAULT_RETENTION_DAYS = "30"
DEFAULT_ALLOW_HTML = "false"
ADMIN_SESSION_TTL = timedelta(minutes=20)
ADMIN_COOKIE_NAME = "quail_admin"
MAX_LIST_ROWS = 200
MAX_ADMIN_ATTEMPTS = 5
ADMIN_ATTEMPT_WINDOW = timedelta(minutes=5)

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_admin_sessions: dict[str, datetime] = {}
_admin_attempts: dict[str, list[datetime]] = {}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _cleanup_admin_state() -> None:
    now = _now()
    for token, expires_at in list(_admin_sessions.items()):
        if expires_at <= now:
            _admin_sessions.pop(token, None)
    for ip, timestamps in list(_admin_attempts.items()):
        _admin_attempts[ip] = [
            ts for ts in timestamps if now - ts <= ADMIN_ATTEMPT_WINDOW
        ]
        if not _admin_attempts[ip]:
            _admin_attempts.pop(ip, None)


def _record_admin_attempt(ip: str) -> None:
    _admin_attempts.setdefault(ip, []).append(_now())


def _too_many_attempts(ip: str) -> bool:
    _cleanup_admin_state()
    return len(_admin_attempts.get(ip, [])) >= MAX_ADMIN_ATTEMPTS


def _is_admin(request: Request) -> bool:
    _cleanup_admin_state()
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        return False
    expires_at = _admin_sessions.get(token)
    if not expires_at:
        return False
    if expires_at <= _now():
        _admin_sessions.pop(token, None)
        return False
    return True


def _require_admin(request: Request) -> None:
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required.")


def _set_admin_cookie(response: RedirectResponse) -> None:
    token = secrets.token_urlsafe(32)
    _admin_sessions[token] = _now() + ADMIN_SESSION_TTL
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=int(ADMIN_SESSION_TTL.total_seconds()),
    )


def _init_settings(settings_path: Path) -> None:
    if db.get_setting(settings_path, ALLOWED_MIME_TYPES_KEY) is None:
        db.set_setting(settings_path, ALLOWED_MIME_TYPES_KEY, DEFAULT_ALLOWED_MIME_TYPES)
    if db.get_setting(settings_path, RETENTION_DAYS_KEY) is None:
        db.set_setting(settings_path, RETENTION_DAYS_KEY, DEFAULT_RETENTION_DAYS)
    if db.get_setting(settings_path, ALLOW_HTML_KEY) is None:
        db.set_setting(settings_path, ALLOW_HTML_KEY, DEFAULT_ALLOW_HTML)


def _log_admin_action(db_path: Path, action: str, request: Request) -> None:
    with db.get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO admin_actions (action, source_ip, performed_at) VALUES (?, ?, ?)",
            (
                action,
                request.client.host if request.client else "unknown",
                _now().isoformat(),
            ),
        )
        conn.commit()


def _iter_messages(db_path: Path, include_quarantined: bool) -> Iterable[dict[str, str]]:
    query = """
        SELECT id, received_at, envelope_rcpt, from_addr, subject, date, size_bytes, quarantined
        FROM messages
        {where_clause}
        ORDER BY received_at DESC
        LIMIT ?
    """
    where_clause = "" if include_quarantined else "WHERE quarantined = 0"
    with db.get_connection(db_path) as conn:
        rows = conn.execute(query.format(where_clause=where_clause), (MAX_LIST_ROWS,)).fetchall()
    return [dict(row) for row in rows]


def _get_message(db_path: Path, message_id: int) -> dict[str, str]:
    with db.get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, received_at, envelope_rcpt, from_addr, subject, date, message_id,
                   size_bytes, eml_path, quarantined
            FROM messages
            WHERE id = ?
            """,
            (message_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found.")
    return dict(row)


def _parse_message_body(eml_path: Path) -> tuple[str, list[dict[str, str]]]:
    raw_bytes = eml_path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    body = ""
    attachments: list[dict[str, str]] = []
    for part in message.walk():
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True)
        size = len(payload) if payload else 0
        if disposition == "attachment" or filename:
            attachments.append(
                {
                    "filename": filename or "unnamed",
                    "content_type": content_type,
                    "size": str(size),
                }
            )
            continue
        if not body and part.get_content_type() == "text/plain":
            body = part.get_content()
    if not body:
        body = "(No plaintext body found.)"
    return body, attachments
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
    _init_settings(settings.db_path)


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


@app.get("/", response_class=HTMLResponse)
@app.get("/inbox", response_class=HTMLResponse)
async def inbox(request: Request) -> HTMLResponse:
    settings = get_settings()
    is_admin = _is_admin(request)
    messages = _iter_messages(settings.db_path, include_quarantined=is_admin)
    return templates.TemplateResponse(
        "inbox.html",
        {"request": request, "messages": messages, "is_admin": is_admin},
    )


@app.get("/message/{message_id}", response_class=HTMLResponse)
async def message_detail(request: Request, message_id: int) -> HTMLResponse:
    settings = get_settings()
    is_admin = _is_admin(request)
    message = _get_message(settings.db_path, message_id)
    if message["quarantined"] and not is_admin:
        raise HTTPException(status_code=404, detail="Message not found.")
    body, attachments = _parse_message_body(Path(message["eml_path"]))
    return templates.TemplateResponse(
        "message.html",
        {
            "request": request,
            "message": message,
            "body": body,
            "attachments": attachments,
            "is_admin": is_admin,
        },
    )


@app.get("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "admin_unlock.html",
        {"request": request, "error": error},
    )


@app.post("/admin/unlock")
async def admin_unlock_post(request: Request, pin: str = Form(...)) -> RedirectResponse:
    settings = get_settings()
    if _too_many_attempts(request.client.host if request.client else "unknown"):
        return RedirectResponse(url="/admin/unlock?error=rate_limited", status_code=303)
    stored_hash = db.get_setting(settings.db_path, ADMIN_PIN_HASH_KEY)
    if stored_hash is None:
        db.set_setting(settings.db_path, ADMIN_PIN_HASH_KEY, hash_pin(pin))
        _log_admin_action(settings.db_path, "admin_pin_initialized", request)
    elif not verify_pin(pin, stored_hash):
        _record_admin_attempt(request.client.host if request.client else "unknown")
        return RedirectResponse(url="/admin/unlock?error=invalid", status_code=303)
    response = RedirectResponse(url="/admin/settings", status_code=303)
    _set_admin_cookie(response)
    return response


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    settings = get_settings()
    if not _is_admin(request):
        return RedirectResponse(url="/admin/unlock", status_code=303)
    context = {
        "request": request,
        "allowed_mime_types": db.get_setting(settings.db_path, ALLOWED_MIME_TYPES_KEY)
        or DEFAULT_ALLOWED_MIME_TYPES,
        "retention_days": db.get_setting(settings.db_path, RETENTION_DAYS_KEY)
        or DEFAULT_RETENTION_DAYS,
        "allow_html": db.get_setting(settings.db_path, ALLOW_HTML_KEY) == "true",
    }
    return templates.TemplateResponse("admin_settings.html", context)


@app.post("/admin/settings")
async def admin_settings_post(
    request: Request,
    allowed_mime_types: str = Form(...),
    retention_days: str = Form(...),
    allow_html: str | None = Form(None),
    admin_pin: str | None = Form(None),
) -> RedirectResponse:
    settings = get_settings()
    _require_admin(request)
    try:
        retention_value = int(retention_days)
        if retention_value <= 0:
            raise ValueError
    except ValueError:
        return RedirectResponse(url="/admin/settings?error=retention", status_code=303)

    normalized_mime_types = ",".join(
        item.strip().lower()
        for item in allowed_mime_types.split(",")
        if item.strip()
    )
    if not normalized_mime_types:
        normalized_mime_types = DEFAULT_ALLOWED_MIME_TYPES
    db.set_setting(settings.db_path, ALLOWED_MIME_TYPES_KEY, normalized_mime_types)
    db.set_setting(settings.db_path, RETENTION_DAYS_KEY, str(retention_value))
    db.set_setting(
        settings.db_path, ALLOW_HTML_KEY, "true" if allow_html else "false"
    )
    if admin_pin:
        db.set_setting(settings.db_path, ADMIN_PIN_HASH_KEY, hash_pin(admin_pin))
        _log_admin_action(settings.db_path, "admin_pin_updated", request)
    _log_admin_action(settings.db_path, "admin_settings_updated", request)
    return RedirectResponse(url="/admin/settings?updated=1", status_code=303)
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
