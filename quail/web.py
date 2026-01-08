"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
import secrets
from typing import Iterable

from fastapi import FastAPI, Form, HTTPException, Request
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


@app.on_event("startup")
async def _startup() -> None:
    configure_logging()
    settings = get_settings()
    db.init_db(settings.db_path)
    _init_settings(settings.db_path)


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
