"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
import secrets
from typing import Iterable

import bleach
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from quail import db
from quail.ingest import DEFAULT_ALLOWED_MIME_TYPES, SETTINGS_ALLOWED_MIME_KEY
from quail.logging_config import configure_logging
from quail.security import hash_pin, verify_pin
from quail.settings import get_settings


ADMIN_PIN_HASH_KEY = "admin_pin_hash"
RETENTION_DAYS_KEY = "retention_days"
ALLOW_HTML_KEY = "allow_html"
DEFAULT_ALLOWED_MIME_TYPES_STR = ",".join(DEFAULT_ALLOWED_MIME_TYPES)
DEFAULT_RETENTION_DAYS = "30"
DEFAULT_ALLOW_HTML = "false"
ADMIN_SESSION_TTL = timedelta(minutes=20)
ADMIN_COOKIE_NAME = "quail_admin_session"
MAX_LIST_ROWS = 200
ADMIN_RATE_LIMIT_WINDOW = timedelta(minutes=15)
ADMIN_RATE_LIMIT_MAX_ATTEMPTS = 5

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _init_settings(settings_path: Path) -> None:
    if db.get_setting(settings_path, SETTINGS_ALLOWED_MIME_KEY) is None:
        db.set_setting(settings_path, SETTINGS_ALLOWED_MIME_KEY, DEFAULT_ALLOWED_MIME_TYPES_STR)
    if db.get_setting(settings_path, RETENTION_DAYS_KEY) is None:
        db.set_setting(settings_path, RETENTION_DAYS_KEY, DEFAULT_RETENTION_DAYS)
    if db.get_setting(settings_path, ALLOW_HTML_KEY) is None:
        db.set_setting(settings_path, ALLOW_HTML_KEY, DEFAULT_ALLOW_HTML)


def _get_session_state(settings_db_path: Path) -> tuple[str | None, datetime | None]:
    token_hash = db.get_setting(settings_db_path, "admin_session_hash")
    expires_at_raw = db.get_setting(settings_db_path, "admin_session_expires_at")
    if not token_hash or not expires_at_raw:
        return None, None
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        return None, None
    return token_hash, expires_at


def _set_session_state(settings_db_path: Path, token_hash: str, expires_at: datetime) -> None:
    db.set_setting(settings_db_path, "admin_session_hash", token_hash)
    db.set_setting(settings_db_path, "admin_session_expires_at", expires_at.isoformat())


def _clear_session_state(settings_db_path: Path) -> None:
    db.set_setting(settings_db_path, "admin_session_hash", "")
    db.set_setting(settings_db_path, "admin_session_expires_at", "")


def _is_rate_limited(settings_db_path: Path, source_ip: str, now: datetime) -> bool:
    state = db.get_rate_limit_state(settings_db_path, source_ip)
    if not state:
        return False
    try:
        window_start = datetime.fromisoformat(state["window_start"])
    except ValueError:
        db.clear_rate_limit_state(settings_db_path, source_ip)
        return False
    if now - window_start > ADMIN_RATE_LIMIT_WINDOW:
        db.clear_rate_limit_state(settings_db_path, source_ip)
        return False
    return state["attempts"] >= ADMIN_RATE_LIMIT_MAX_ATTEMPTS


def _record_rate_limit_failure(settings_db_path: Path, source_ip: str, now: datetime) -> None:
    state = db.get_rate_limit_state(settings_db_path, source_ip)
    if not state:
        db.set_rate_limit_state(settings_db_path, source_ip, 1, now.isoformat())
        return
    try:
        window_start = datetime.fromisoformat(state["window_start"])
    except ValueError:
        db.set_rate_limit_state(settings_db_path, source_ip, 1, now.isoformat())
        return
    if now - window_start > ADMIN_RATE_LIMIT_WINDOW:
        db.set_rate_limit_state(settings_db_path, source_ip, 1, now.isoformat())
        return
    attempts = state["attempts"] + 1
    db.set_rate_limit_state(settings_db_path, source_ip, attempts, window_start.isoformat())


def _reset_rate_limit(settings_db_path: Path, source_ip: str) -> None:
    db.clear_rate_limit_state(settings_db_path, source_ip)


def _validate_admin_session(request: Request) -> bool:
    settings = get_settings()
    token_hash, expires_at = _get_session_state(settings.db_path)
    if not token_hash or not expires_at:
        return False
    if expires_at < _now():
        _clear_session_state(settings.db_path)
        return False
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        return False
    try:
        return verify_pin(token, token_hash)
    except Exception:
        return False


def _is_admin(request: Request) -> bool:
    return _validate_admin_session(request)


def _require_admin(request: Request) -> None:
    if not _validate_admin_session(request):
        raise HTTPException(status_code=403, detail="Admin access required.")


def _normalize_mime_list(value: str) -> str:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    return ",".join(items)


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
    allow_html = db.get_setting(settings.db_path, ALLOW_HTML_KEY) == "true"
    body, attachments, html_body = _parse_message_body(
        Path(message["eml_path"]), allow_html
    )
    sanitized_html = _sanitize_html(html_body) if allow_html and html_body else None
    return templates.TemplateResponse(
        "message.html",
        {
            "request": request,
            "message": message,
            "body": body,
            "html_body": sanitized_html,
            "attachments": attachments,
            "is_admin": is_admin,
            "allow_html": allow_html,
        },
    )


@app.get("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock(request: Request) -> HTMLResponse:
    settings = get_settings()
    if _is_admin(request):
        return RedirectResponse(url="/admin/settings", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "admin_unlock.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
            "pin_configured": bool(db.get_setting(settings.db_path, ADMIN_PIN_HASH_KEY)),
        },
    )


@app.post("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock_post(request: Request, pin: str = Form(...)) -> HTMLResponse:
    settings = get_settings()
    source_ip = _get_client_ip(request)
    now = _now()
    if _is_rate_limited(settings.db_path, source_ip, now):
        return RedirectResponse(
            url="/admin/unlock?error=rate_limited", status_code=HTTP_303_SEE_OTHER
        )
    stored_hash = db.get_setting(settings.db_path, ADMIN_PIN_HASH_KEY)
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
    if not verify_pin(pin, stored_hash):
        _record_rate_limit_failure(settings.db_path, source_ip, now)
        return RedirectResponse(
            url="/admin/unlock?error=invalid", status_code=HTTP_303_SEE_OTHER
        )

    _reset_rate_limit(settings.db_path, source_ip)
    token = secrets.token_urlsafe(32)
    token_hash = hash_pin(token)
    expires_at = now + ADMIN_SESSION_TTL
    _set_session_state(settings.db_path, token_hash, expires_at)
    db.log_admin_action(settings.db_path, "admin_unlock", source_ip, now.isoformat())
    response = RedirectResponse(url="/admin/settings", status_code=HTTP_303_SEE_OTHER)
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        max_age=int(ADMIN_SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    _require_admin(request)
    settings = get_settings()
    context = {
        "request": request,
        "allowed_mime_types": db.get_setting(settings.db_path, SETTINGS_ALLOWED_MIME_KEY)
        or DEFAULT_ALLOWED_MIME_TYPES_STR,
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
    _require_admin(request)
    settings = get_settings()
    source_ip = _get_client_ip(request)
    now = _now()
    try:
        retention_value = int(retention_days)
        if retention_value <= 0:
            raise ValueError
    except ValueError:
        return RedirectResponse(url="/admin/settings?error=retention", status_code=HTTP_303_SEE_OTHER)

    normalized_mime_types = _normalize_mime_list(allowed_mime_types)
    if not normalized_mime_types:
        normalized_mime_types = DEFAULT_ALLOWED_MIME_TYPES_STR
    db.set_setting(settings.db_path, SETTINGS_ALLOWED_MIME_KEY, normalized_mime_types)
    db.set_setting(settings.db_path, RETENTION_DAYS_KEY, str(retention_value))
    db.set_setting(settings.db_path, ALLOW_HTML_KEY, "true" if allow_html else "false")

    if admin_pin:
        db.set_setting(settings.db_path, ADMIN_PIN_HASH_KEY, hash_pin(admin_pin))
        db.log_admin_action(settings.db_path, "admin_pin_updated", source_ip, now.isoformat())

    db.log_admin_action(settings.db_path, "admin_settings_updated", source_ip, now.isoformat())
    return RedirectResponse(url="/admin/settings?updated=1", status_code=HTTP_303_SEE_OTHER)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
