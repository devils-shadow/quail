"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
import secrets
from typing import Iterable
from urllib.parse import quote

import bleach
from argon2.exceptions import InvalidHash, VerifyMismatchError
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from quail import db
from quail.ingest import (
    DECISION_STATUSES,
    DEFAULT_ALLOWED_MIME_TYPES,
    DOMAIN_MODES,
    MATCH_FIELDS,
    RULE_TYPES,
    SETTINGS_ALLOWED_MIME_KEY,
)
from quail.logging_config import configure_logging
from quail.security import hash_pin, verify_pin
from quail.settings import get_settings


ADMIN_PIN_HASH_KEY = "admin_pin_hash"
RETENTION_DAYS_KEY = "retention_days"
ALLOW_HTML_KEY = "allow_html"
DEFAULT_ALLOWED_MIME_TYPES_VALUE = ",".join(DEFAULT_ALLOWED_MIME_TYPES)
DEFAULT_RETENTION_DAYS = "30"
DEFAULT_ALLOW_HTML = "false"
ADMIN_SESSION_COOKIE = "quail_admin_session"
ADMIN_SESSION_TTL = timedelta(minutes=20)
ADMIN_RATE_LIMIT_WINDOW = timedelta(minutes=15)
ADMIN_RATE_LIMIT_MAX_ATTEMPTS = 5
MAX_LIST_ROWS = 200

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Quail")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
LOGGER = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _init_settings(settings_path: Path) -> None:
    if db.get_setting(settings_path, SETTINGS_ALLOWED_MIME_KEY) is None:
        db.set_setting(settings_path, SETTINGS_ALLOWED_MIME_KEY, DEFAULT_ALLOWED_MIME_TYPES_VALUE)
    if db.get_setting(settings_path, RETENTION_DAYS_KEY) is None:
        db.set_setting(settings_path, RETENTION_DAYS_KEY, DEFAULT_RETENTION_DAYS)
    if db.get_setting(settings_path, ALLOW_HTML_KEY) is None:
        db.set_setting(settings_path, ALLOW_HTML_KEY, DEFAULT_ALLOW_HTML)


def _get_admin_pin_hash(settings_db_path: Path) -> str | None:
    return db.get_setting(settings_db_path, ADMIN_PIN_HASH_KEY)


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


def _is_admin(request: Request) -> bool:
    settings = get_settings()
    token_hash, expires_at = _get_session_state(settings.db_path)
    if not token_hash or not expires_at:
        return False
    if expires_at < _now():
        _clear_session_state(settings.db_path)
        return False
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not token:
        return False
    try:
        return verify_pin(token, token_hash)
    except Exception:
        return False


def _log_admin_action(db_path: Path, action: str, request: Request) -> None:
    db.log_admin_action(db_path, action, _get_client_ip(request), _now().isoformat())


def _normalize_mime_list(value: str) -> str:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    return ",".join(items)


def _parse_enabled(raw_value: str | None) -> int:
    if raw_value is None:
        return 0
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "on", "yes"}:
        return 1
    return 0


def _validate_regex(pattern: str) -> str | None:
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"Invalid regex pattern: {exc}"
    return None


def _normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized or "@" in normalized or any(char.isspace() for char in normalized):
        return None
    return normalized or None


def _rule_error_response(
    request: Request, domain: str | None, message: str
) -> RedirectResponse | JSONResponse:
    if _wants_json(request):
        raise HTTPException(status_code=400, detail=message)
    domain_param = f"rules_domain={quote(domain)}&" if domain else ""
    return RedirectResponse(
        url=f"/admin/settings?{domain_param}rules_error={quote(message)}",
        status_code=HTTP_303_SEE_OTHER,
    )


def _serialize_rule(row: dict[str, str] | object) -> dict[str, str | int | None]:
    if hasattr(row, "keys"):
        data = dict(row)  # type: ignore[arg-type]
    else:
        data = dict(row)  # type: ignore[arg-type]
    return {
        "id": int(data["id"]),
        "domain": data["domain"],
        "rule_type": data["rule_type"],
        "match_field": data["match_field"],
        "pattern": data["pattern"],
        "priority": int(data["priority"]),
        "action": data["action"],
        "enabled": int(data["enabled"]),
        "note": data.get("note"),
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
    }


def _normalize_rule_fields(
    request: Request,
    rule_type: str,
    match_field: str,
    pattern: str,
    priority: str,
    action: str,
    domain: str | None = None,
) -> tuple[dict[str, object] | None, RedirectResponse | JSONResponse | None]:
    normalized_domain = _normalize_domain(domain) if domain is not None else None
    if domain is not None and not normalized_domain:
        message = "Domain is required."
        if domain.strip():
            message = "Invalid domain."
        return None, _rule_error_response(request, domain, message)
    normalized_rule_type = rule_type.strip().upper()
    if normalized_rule_type not in RULE_TYPES:
        return None, _rule_error_response(request, normalized_domain, "Invalid rule type.")
    normalized_match_field = match_field.strip().upper()
    if normalized_match_field not in MATCH_FIELDS:
        return None, _rule_error_response(request, normalized_domain, "Invalid match field.")
    normalized_action = action.strip().upper()
    if normalized_action not in DECISION_STATUSES:
        return None, _rule_error_response(request, normalized_domain, "Invalid action.")
    cleaned_pattern = pattern.strip()
    if not cleaned_pattern:
        return None, _rule_error_response(request, normalized_domain, "Pattern is required.")
    regex_error = _validate_regex(cleaned_pattern)
    if regex_error:
        return None, _rule_error_response(request, normalized_domain, regex_error)
    try:
        priority_value = int(priority)
    except ValueError:
        return None, _rule_error_response(
            request, normalized_domain, "Priority must be an integer."
        )
    if priority_value < 0:
        return None, _rule_error_response(
            request, normalized_domain, "Priority must be non-negative."
        )
    return (
        {
            "domain": normalized_domain,
            "rule_type": normalized_rule_type,
            "match_field": normalized_match_field,
            "pattern": cleaned_pattern,
            "priority": priority_value,
            "action": normalized_action,
        },
        None,
    )


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept or "application/*" in accept


def _build_quarantine_query(
    domain: str | None,
    sender_domain: str | None,
    recipient_localpart: str | None,
    start_date: str | None,
    end_date: str | None,
) -> str:
    params = []
    for key, value in (
        ("domain", domain),
        ("sender_domain", sender_domain),
        ("recipient_localpart", recipient_localpart),
        ("start_date", start_date),
        ("end_date", end_date),
    ):
        if value:
            params.append(f"{key}={quote(value)}")
    return f"?{'&'.join(params)}" if params else ""


async def _extract_message_ids(request: Request) -> list[int]:
    form = await request.form()
    raw_values = form.getlist("message_id")
    message_ids = []
    for value in raw_values:
        try:
            message_ids.append(int(value))
        except ValueError:
            continue
    return message_ids


def _require_admin_session(request: Request) -> RedirectResponse | None:
    if _is_admin(request):
        return None
    if _wants_json(request):
        raise HTTPException(status_code=403, detail="Admin session required.")
    return RedirectResponse(url="/admin/unlock", status_code=303)


def _verify_admin_pin(db_path: Path, admin_pin: str | None) -> bool:
    if not admin_pin:
        return False
    stored_hash = _get_admin_pin_hash(db_path)
    if not stored_hash:
        return False
    try:
        return verify_pin(admin_pin, stored_hash)
    except (VerifyMismatchError, InvalidHash):
        return False


def _reject_admin_pin(request: Request) -> RedirectResponse:
    if _wants_json(request):
        raise HTTPException(status_code=403, detail="Admin PIN verification required.")
    return RedirectResponse(url="/admin/settings?domain_error=pin", status_code=303)


def _get_admin_pin_from_request(request: Request, admin_pin: str | None = None) -> str | None:
    header_pin = request.headers.get("x-admin-pin")
    if header_pin:
        return header_pin
    return admin_pin


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_like_pattern(value: str) -> str:
    return _escape_like(value).replace("*", "%")


def _extract_primary_address(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    addresses = getaddresses([raw_value])
    for _, address in addresses:
        if address:
            return address
    return None


def _extract_domain(address: str | None) -> str | None:
    if not address:
        return None
    _, _, domain = address.partition("@")
    return domain.lower() if domain else None


def _split_envelope_rcpt(envelope_rcpt: str) -> tuple[str, str]:
    localpart, _, domain = envelope_rcpt.partition("@")
    return localpart, domain.lower()


def _parse_date_filter(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        date_value = datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        return None
    return datetime.combine(date_value, datetime.min.time(), tzinfo=timezone.utc)


def _iter_quarantine_messages(
    db_path: Path,
    domain_filter: str | None,
    sender_domain_filter: str | None,
    localpart_filter: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> list[dict[str, str]]:
    query = """
        SELECT
            id,
            received_at,
            envelope_rcpt,
            from_addr,
            subject,
            quarantine_reason
        FROM messages
        WHERE (status = 'QUARANTINE' OR quarantined = 1)
        {filters}
        ORDER BY received_at DESC
        LIMIT ?
    """
    conditions = []
    params: list[str | int] = []
    if domain_filter:
        pattern = f"%@{_escape_like(domain_filter)}"
        conditions.append("LOWER(envelope_rcpt) LIKE ? ESCAPE '\\'")
        params.append(pattern.lower())
    if sender_domain_filter:
        pattern = f"%@{_escape_like(sender_domain_filter)}%"
        conditions.append("LOWER(from_addr) LIKE ? ESCAPE '\\'")
        params.append(pattern.lower())
    if localpart_filter:
        pattern = f"{_escape_like(localpart_filter)}@%"
        conditions.append("LOWER(envelope_rcpt) LIKE ? ESCAPE '\\'")
        params.append(pattern.lower())
    if start_date:
        conditions.append("received_at >= ?")
        params.append(start_date.isoformat())
    if end_date:
        end_bound = end_date + timedelta(days=1)
        conditions.append("received_at < ?")
        params.append(end_bound.isoformat())
    filters = f" AND {' AND '.join(conditions)}" if conditions else ""
    params.append(MAX_LIST_ROWS)
    with db.get_connection(db_path) as conn:
        rows = conn.execute(query.format(filters=filters), params).fetchall()
    return [dict(row) for row in rows]


def _fetch_messages_by_ids(db_path: Path, message_ids: list[int]) -> list[dict[str, str]]:
    if not message_ids:
        return []
    placeholders = ",".join(["?"] * len(message_ids))
    query = f"""
        SELECT id, envelope_rcpt, from_addr, subject, status, quarantined
        FROM messages
        WHERE id IN ({placeholders})
    """
    with db.get_connection(db_path) as conn:
        rows = conn.execute(query, message_ids).fetchall()
    return [dict(row) for row in rows]


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 0:
        size_bytes = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size_bytes)} B"


def _get_storage_stats(db_path: Path) -> dict[str, int]:
    with db.get_connection(db_path) as conn:
        message_row = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(size_bytes), 0) AS total FROM messages"
        ).fetchone()
        attachment_row = conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM attachments"
        ).fetchone()
    return {
        "message_count": int(message_row["count"] or 0),
        "message_bytes": int(message_row["total"] or 0),
        "attachment_bytes": int(attachment_row["total"] or 0),
    }


def _iter_messages(
    db_path: Path, include_quarantined: bool, inbox_filter: str | None
) -> Iterable[dict[str, str]]:
    query = """
        SELECT id, received_at, envelope_rcpt, from_addr, subject, date, size_bytes, quarantined
        FROM messages
        {where_clause}
        ORDER BY received_at DESC
        LIMIT ?
    """
    conditions = []
    params: list[str | int] = []
    if not include_quarantined:
        conditions.append("quarantined = 0")
    if inbox_filter:
        if "*" in inbox_filter:
            conditions.append("envelope_rcpt LIKE ? ESCAPE '\\'")
            params.append(_to_like_pattern(inbox_filter))
        else:
            conditions.append("envelope_rcpt = ?")
            params.append(inbox_filter)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(MAX_LIST_ROWS)
    with db.get_connection(db_path) as conn:
        rows = conn.execute(query.format(where_clause=where_clause), params).fetchall()
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


def _get_message_attachments(db_path: Path, message_id: int) -> list[dict[str, str]]:
    with db.get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT filename, stored_path, content_type, size_bytes
            FROM attachments
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _sanitize_html(html_body: str) -> str:
    allowed_tags = [
        "a",
        "p",
        "br",
        "strong",
        "em",
        "ul",
        "ol",
        "li",
        "blockquote",
        "code",
        "pre",
    ]
    allowed_attributes = {
        "a": ["href", "title", "rel"],
    }
    return bleach.clean(
        html_body,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def _delete_path(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("Failed to delete file at %s", path)


def _delete_message(settings_db_path: Path, message_id: int) -> None:
    message = _get_message(settings_db_path, message_id)
    attachments = _get_message_attachments(settings_db_path, message_id)
    for attachment in attachments:
        _delete_path(Path(attachment["stored_path"]))
    _delete_path(Path(message["eml_path"]))
    with db.get_connection(settings_db_path) as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()


def _delete_all_messages(settings_db_path: Path) -> int:
    with db.get_connection(settings_db_path) as conn:
        attachments = conn.execute("SELECT stored_path FROM attachments").fetchall()
        messages = conn.execute("SELECT eml_path FROM messages").fetchall()
        conn.execute("DELETE FROM messages")
        conn.commit()
    for attachment in attachments:
        _delete_path(Path(attachment["stored_path"]))
    for message in messages:
        _delete_path(Path(message["eml_path"]))
    return len(messages)


def _update_message_status(settings_db_path: Path, message_id: int, status: str) -> None:
    with db.get_connection(settings_db_path) as conn:
        conn.execute(
            """
            UPDATE messages
            SET status = ?, quarantined = ?, quarantine_reason = ?
            WHERE id = ?
            """,
            (status, 0 if status == "INBOX" else 1, None if status == "INBOX" else "", message_id),
        )
        conn.commit()


def _parse_message_body(
    eml_path: Path, allow_html: bool
) -> tuple[str, list[dict[str, str]], str | None]:
    raw_bytes = eml_path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    body = ""
    html_body: str | None = None
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
        if allow_html and html_body is None and part.get_content_type() == "text/html":
            html_body = part.get_content()
    if not body:
        body = "(No plaintext body found.)"
    return body, attachments, html_body


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
    inbox_filter = request.query_params.get("inbox")
    if inbox_filter:
        inbox_filter = inbox_filter.strip() or None
    messages = _iter_messages(
        settings.db_path, include_quarantined=is_admin, inbox_filter=inbox_filter
    )
    return templates.TemplateResponse(
        "inbox.html",
        {
            "request": request,
            "messages": messages,
            "is_admin": is_admin,
            "current_inbox": inbox_filter or "",
        },
    )


@app.get("/message/{message_id}", response_class=HTMLResponse)
async def message_detail(request: Request, message_id: int) -> HTMLResponse:
    settings = get_settings()
    is_admin = _is_admin(request)
    message = _get_message(settings.db_path, message_id)
    if message["quarantined"] and not is_admin:
        raise HTTPException(status_code=404, detail="Message not found.")
    allow_html = db.get_setting(settings.db_path, ALLOW_HTML_KEY) == "true"
    body, attachments, html_body = _parse_message_body(Path(message["eml_path"]), allow_html)
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
            "current_inbox": request.query_params.get("inbox") or "",
        },
    )


@app.post("/admin/message/{message_id}/delete")
async def admin_delete_message(request: Request, message_id: int) -> RedirectResponse:
    if not _is_admin(request):
        return RedirectResponse(url="/admin/unlock", status_code=303)
    settings = get_settings()
    _delete_message(settings.db_path, message_id)
    _log_admin_action(settings.db_path, f"admin_message_deleted:{message_id}", request)
    return RedirectResponse(url="/inbox", status_code=303)


@app.get("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        "admin_unlock.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
            "pin_configured": bool(_get_admin_pin_hash(settings.db_path)),
        },
    )


@app.post("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock_post(request: Request, pin: str = Form(...)) -> HTMLResponse:
    settings = get_settings()
    source_ip = _get_client_ip(request)
    now = _now()
    if _is_rate_limited(settings.db_path, source_ip, now):
        return RedirectResponse(url="/admin/unlock?error=rate_limited", status_code=303)

    stored_hash = _get_admin_pin_hash(settings.db_path)
    if stored_hash is None:
        db.set_setting(settings.db_path, ADMIN_PIN_HASH_KEY, hash_pin(pin))
        _log_admin_action(settings.db_path, "admin_pin_initialized", request)
    elif stored_hash is not None:
        try:
            is_valid = verify_pin(pin, stored_hash)
        except (VerifyMismatchError, InvalidHash):
            is_valid = False
        if not is_valid:
            _record_rate_limit_failure(settings.db_path, source_ip, now)
            return RedirectResponse(url="/admin/unlock?error=invalid", status_code=303)

    _reset_rate_limit(settings.db_path, source_ip)
    token = secrets.token_urlsafe(32)
    token_hash = hash_pin(token)
    expires_at = now + ADMIN_SESSION_TTL
    _set_session_state(settings.db_path, token_hash, expires_at)
    _log_admin_action(settings.db_path, "admin_unlock", request)
    response = RedirectResponse(url="/admin/settings", status_code=303)
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        token,
        max_age=int(ADMIN_SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    _log_admin_action(settings.db_path, "admin_settings_view", request)
    storage_stats = _get_storage_stats(settings.db_path)
    rules_domain = _normalize_domain(request.query_params.get("rules_domain"))
    rules = db.list_address_rules(settings.db_path, rules_domain) if rules_domain else []
    context = {
        "request": request,
        "allowed_mime_types": db.get_setting(settings.db_path, SETTINGS_ALLOWED_MIME_KEY)
        or DEFAULT_ALLOWED_MIME_TYPES_VALUE,
        "retention_days": db.get_setting(settings.db_path, RETENTION_DAYS_KEY)
        or DEFAULT_RETENTION_DAYS,
        "allow_html": db.get_setting(settings.db_path, ALLOW_HTML_KEY) == "true",
        "message_count": storage_stats["message_count"],
        "message_bytes": _format_bytes(storage_stats["message_bytes"]),
        "attachment_bytes": _format_bytes(storage_stats["attachment_bytes"]),
        "total_bytes": _format_bytes(
            storage_stats["message_bytes"] + storage_stats["attachment_bytes"]
        ),
        "domain_policies": [dict(row) for row in db.list_domain_policies(settings.db_path)],
        "domain_modes": DOMAIN_MODES,
        "domain_actions": DECISION_STATUSES,
        "rules_domain": rules_domain,
        "rules": [dict(row) for row in rules],
        "rule_types": RULE_TYPES,
        "match_fields": MATCH_FIELDS,
        "rule_actions": DECISION_STATUSES,
    }
    return templates.TemplateResponse("admin_settings.html", context)


@app.post("/admin/settings")
async def admin_settings_post(
    request: Request,
    allowed_mime_types: str = Form(""),
    retention_days: str = Form(""),
    allow_html: str | None = Form(None),
    admin_pin: str | None = Form(None),
) -> RedirectResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect

    settings = get_settings()
    try:
        retention_value = int(retention_days)
        if retention_value <= 0:
            raise ValueError
    except ValueError:
        return RedirectResponse(
            url="/admin/settings?error=retention", status_code=HTTP_303_SEE_OTHER
        )

    normalized_mime_types = _normalize_mime_list(allowed_mime_types)
    if not normalized_mime_types:
        normalized_mime_types = DEFAULT_ALLOWED_MIME_TYPES_VALUE
    db.set_setting(settings.db_path, SETTINGS_ALLOWED_MIME_KEY, normalized_mime_types)
    db.set_setting(settings.db_path, RETENTION_DAYS_KEY, str(retention_value))
    db.set_setting(settings.db_path, ALLOW_HTML_KEY, "true" if allow_html else "false")
    if admin_pin:
        db.set_setting(settings.db_path, ADMIN_PIN_HASH_KEY, hash_pin(admin_pin))
        _log_admin_action(settings.db_path, "admin_pin_updated", request)
    _log_admin_action(settings.db_path, "admin_settings_updated", request)
    return RedirectResponse(url="/admin/settings?updated=1", status_code=HTTP_303_SEE_OTHER)


@app.get("/admin/domain-policies", response_class=JSONResponse)
async def admin_domain_policies(request: Request, admin_pin: str | None = None) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if resolved_pin and not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    policies = [dict(row) for row in db.list_domain_policies(settings.db_path)]
    return JSONResponse({"policies": policies})


@app.post("/admin/domain-policies", response_class=JSONResponse)
async def admin_domain_policies_post(
    request: Request,
    domain: str = Form(...),
    mode: str = Form(...),
    default_action: str = Form(...),
    admin_pin: str | None = Form(None),
) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    normalized_domain = domain.strip().lower()
    if not normalized_domain or "@" in normalized_domain or " " in normalized_domain:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="Invalid domain.")
        return RedirectResponse(url="/admin/settings?domain_error=domain", status_code=303)
    normalized_mode = mode.strip().upper()
    if normalized_mode not in DOMAIN_MODES:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="Invalid domain mode.")
        return RedirectResponse(url="/admin/settings?domain_error=mode", status_code=303)
    normalized_action = default_action.strip().upper()
    if normalized_action not in DECISION_STATUSES:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="Invalid default action.")
        return RedirectResponse(url="/admin/settings?domain_error=action", status_code=303)
    now = _now().isoformat()
    policy = db.upsert_domain_policy(
        settings.db_path, normalized_domain, normalized_mode, normalized_action, now
    )
    _log_admin_action(settings.db_path, f"admin_domain_policy_upsert:{normalized_domain}", request)
    if _wants_json(request):
        return JSONResponse({"policy": dict(policy)})
    return RedirectResponse(
        url=f"/admin/settings?domain_saved={normalized_domain}", status_code=303
    )


@app.get("/admin/rules", response_class=JSONResponse)
async def admin_rules(request: Request, domain: str | None = None) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    normalized_domain = _normalize_domain(domain)
    if not normalized_domain:
        message = "Domain is required."
        if domain and domain.strip():
            message = "Invalid domain."
        raise HTTPException(status_code=400, detail=message)
    settings = get_settings()
    rules = [
        _serialize_rule(row) for row in db.list_address_rules(settings.db_path, normalized_domain)
    ]
    return JSONResponse({"domain": normalized_domain, "rules": rules})


@app.post("/admin/rules", response_class=JSONResponse)
async def admin_rules_post(
    request: Request,
    domain: str = Form(...),
    rule_type: str = Form(...),
    match_field: str = Form(...),
    pattern: str = Form(...),
    priority: str = Form(...),
    action: str = Form(...),
    enabled: str | None = Form(None),
    note: str | None = Form(None),
    admin_pin: str | None = Form(None),
) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    normalized, error_response = _normalize_rule_fields(
        request,
        rule_type,
        match_field,
        pattern,
        priority,
        action,
        domain=domain,
    )
    if error_response:
        return error_response
    enabled_value = _parse_enabled(enabled)
    row = db.create_address_rule(
        settings.db_path,
        normalized["domain"],  # type: ignore[arg-type]
        normalized["rule_type"],  # type: ignore[arg-type]
        normalized["match_field"],  # type: ignore[arg-type]
        normalized["pattern"],  # type: ignore[arg-type]
        normalized["priority"],  # type: ignore[arg-type]
        normalized["action"],  # type: ignore[arg-type]
        enabled_value,
        note.strip() if note else None,
        _now().isoformat(),
    )
    _log_admin_action(settings.db_path, f"admin_rule_created:{row['id']}", request)
    if _wants_json(request):
        return JSONResponse({"rule": _serialize_rule(row)})
    return RedirectResponse(
        url=f"/admin/settings?rules_domain={quote(row['domain'])}&rules_saved=1",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.post("/admin/rules/test", response_class=JSONResponse)
async def admin_rules_test(
    request: Request,
    pattern: str = Form(...),
    sample: str = Form(""),
    admin_pin: str | None = Form(None),
    rules_domain: str | None = Form(None),
) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    cleaned_pattern = pattern.strip()
    if not cleaned_pattern:
        return _rule_error_response(request, rules_domain, "Pattern is required.")
    regex_error = _validate_regex(cleaned_pattern)
    if regex_error:
        return _rule_error_response(request, rules_domain, regex_error)
    matched = bool(re.search(cleaned_pattern, sample or ""))
    if _wants_json(request):
        return JSONResponse({"matched": matched})
    result = "matched" if matched else "no_match"
    normalized_domain = _normalize_domain(rules_domain) or ""
    domain_param = f"rules_domain={quote(normalized_domain)}&" if normalized_domain else ""
    return RedirectResponse(
        url=f"/admin/settings?{domain_param}rules_test={result}",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.api_route("/admin/rules/{rule_id}", methods=["PUT", "POST"], response_class=JSONResponse)
async def admin_rules_update(
    request: Request,
    rule_id: int,
    rule_type: str = Form(...),
    match_field: str = Form(...),
    pattern: str = Form(...),
    priority: str = Form(...),
    action: str = Form(...),
    enabled: str | None = Form(None),
    note: str | None = Form(None),
    admin_pin: str | None = Form(None),
) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    existing = db.get_address_rule(settings.db_path, rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found.")
    normalized, error_response = _normalize_rule_fields(
        request,
        rule_type,
        match_field,
        pattern,
        priority,
        action,
    )
    if error_response:
        return error_response
    enabled_value = _parse_enabled(enabled)
    row = db.update_address_rule(
        settings.db_path,
        rule_id,
        normalized["rule_type"],  # type: ignore[arg-type]
        normalized["match_field"],  # type: ignore[arg-type]
        normalized["pattern"],  # type: ignore[arg-type]
        normalized["priority"],  # type: ignore[arg-type]
        normalized["action"],  # type: ignore[arg-type]
        enabled_value,
        note.strip() if note else None,
        _now().isoformat(),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found.")
    _log_admin_action(settings.db_path, f"admin_rule_updated:{rule_id}", request)
    if _wants_json(request):
        return JSONResponse({"rule": _serialize_rule(row)})
    return RedirectResponse(
        url=f"/admin/settings?rules_domain={quote(row['domain'])}&rules_saved=1",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.delete("/admin/rules/{rule_id}", response_class=JSONResponse)
async def admin_rules_delete(
    request: Request,
    rule_id: int,
    admin_pin: str | None = None,
) -> JSONResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    existing = db.get_address_rule(settings.db_path, rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found.")
    deleted = db.delete_address_rule(settings.db_path, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found.")
    _log_admin_action(settings.db_path, f"admin_rule_deleted:{rule_id}", request)
    if _wants_json(request):
        return JSONResponse({"deleted": True, "rule_id": rule_id})
    return RedirectResponse(
        url=f"/admin/settings?rules_domain={quote(existing['domain'])}&rules_deleted=1",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.post("/admin/rules/{rule_id}/delete")
async def admin_rules_delete_post(
    request: Request,
    rule_id: int,
    admin_pin: str | None = Form(None),
) -> RedirectResponse:
    return await admin_rules_delete(request, rule_id, admin_pin)


@app.get("/admin/quarantine", response_class=HTMLResponse)
async def admin_quarantine(request: Request) -> HTMLResponse:
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    settings = get_settings()
    domain_filter = _normalize_domain(request.query_params.get("domain"))
    sender_domain = _normalize_domain(request.query_params.get("sender_domain"))
    recipient_localpart = request.query_params.get("recipient_localpart")
    if recipient_localpart:
        recipient_localpart = recipient_localpart.strip() or None
        if recipient_localpart and "@" in recipient_localpart:
            recipient_localpart = None
    start_date = _parse_date_filter(request.query_params.get("start_date"))
    end_date = _parse_date_filter(request.query_params.get("end_date"))
    messages = _iter_quarantine_messages(
        settings.db_path,
        domain_filter,
        sender_domain,
        recipient_localpart,
        start_date,
        end_date,
    )
    _log_admin_action(settings.db_path, "admin_quarantine_view", request)
    return templates.TemplateResponse(
        "admin_quarantine.html",
        {
            "request": request,
            "messages": messages,
            "domain_filter": domain_filter or "",
            "sender_domain_filter": sender_domain or "",
            "recipient_localpart_filter": recipient_localpart or "",
            "start_date_filter": request.query_params.get("start_date") or "",
            "end_date_filter": request.query_params.get("end_date") or "",
            "match_fields": MATCH_FIELDS,
        },
    )


@app.post("/admin/quarantine/restore")
async def admin_quarantine_restore(
    request: Request,
    admin_pin: str | None = Form(None),
    domain: str | None = Form(None),
    sender_domain: str | None = Form(None),
    recipient_localpart: str | None = Form(None),
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
):
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    message_ids = await _extract_message_ids(request)
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    if not message_ids:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="No messages selected.")
        query = _build_quarantine_query(
            domain, sender_domain, recipient_localpart, start_date, end_date
        )
        return RedirectResponse(
            url=f"/admin/quarantine{query}&error=selection" if query else "/admin/quarantine?error=selection",
            status_code=HTTP_303_SEE_OTHER,
        )
    for message_id_value in message_ids:
        _update_message_status(settings.db_path, message_id_value, "INBOX")
        _log_admin_action(
            settings.db_path, f"admin_quarantine_restore:{message_id_value}", request
        )
    if _wants_json(request):
        return JSONResponse({"restored": message_ids})
    query = _build_quarantine_query(domain, sender_domain, recipient_localpart, start_date, end_date)
    return RedirectResponse(
        url=f"/admin/quarantine{query}&restored=1" if query else "/admin/quarantine?restored=1",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.post("/admin/quarantine/delete")
async def admin_quarantine_delete(
    request: Request,
    admin_pin: str | None = Form(None),
    domain: str | None = Form(None),
    sender_domain: str | None = Form(None),
    recipient_localpart: str | None = Form(None),
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
):
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    message_ids = await _extract_message_ids(request)
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    if not message_ids:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="No messages selected.")
        query = _build_quarantine_query(
            domain, sender_domain, recipient_localpart, start_date, end_date
        )
        return RedirectResponse(
            url=f"/admin/quarantine{query}&error=selection" if query else "/admin/quarantine?error=selection",
            status_code=HTTP_303_SEE_OTHER,
        )
    for message_id_value in message_ids:
        _delete_message(settings.db_path, message_id_value)
        _log_admin_action(
            settings.db_path, f"admin_quarantine_delete:{message_id_value}", request
        )
    if _wants_json(request):
        return JSONResponse({"deleted": message_ids})
    query = _build_quarantine_query(domain, sender_domain, recipient_localpart, start_date, end_date)
    return RedirectResponse(
        url=f"/admin/quarantine{query}&deleted=1" if query else "/admin/quarantine?deleted=1",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.post("/admin/quarantine/rule-from-selection")
async def admin_quarantine_rule_from_selection(
    request: Request,
    rule_type: str = Form(...),
    match_field: str = Form(...),
    admin_pin: str | None = Form(None),
    domain: str | None = Form(None),
    sender_domain: str | None = Form(None),
    recipient_localpart: str | None = Form(None),
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
):
    redirect = _require_admin_session(request)
    if redirect:
        return redirect
    message_ids = await _extract_message_ids(request)
    settings = get_settings()
    resolved_pin = _get_admin_pin_from_request(request, admin_pin)
    if not _verify_admin_pin(settings.db_path, resolved_pin):
        return _reject_admin_pin(request)
    if not message_ids:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="No messages selected.")
        query = _build_quarantine_query(
            domain, sender_domain, recipient_localpart, start_date, end_date
        )
        return RedirectResponse(
            url=f"/admin/quarantine{query}&error=selection" if query else "/admin/quarantine?error=selection",
            status_code=HTTP_303_SEE_OTHER,
        )
    normalized_rule_type = rule_type.strip().upper()
    if normalized_rule_type not in RULE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid rule type.")
    normalized_match_field = match_field.strip().upper()
    if normalized_match_field not in MATCH_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid match field.")
    action = "INBOX" if normalized_rule_type == "ALLOW" else "QUARANTINE"
    rows = _fetch_messages_by_ids(settings.db_path, message_ids)
    created_rules = []
    seen = set()
    now = _now().isoformat()
    for row in rows:
        if row.get("status") != "QUARANTINE" and not row.get("quarantined"):
            continue
        envelope_rcpt = row.get("envelope_rcpt") or ""
        localpart, domain_value = _split_envelope_rcpt(envelope_rcpt)
        if not domain_value:
            continue
        raw_from = row.get("from_addr")
        if normalized_match_field == "RCPT_LOCALPART":
            match_value = localpart
        elif normalized_match_field == "MAIL_FROM":
            match_value = _extract_primary_address(raw_from)
        elif normalized_match_field == "FROM_DOMAIN":
            match_value = _extract_domain(_extract_primary_address(raw_from))
        else:
            match_value = row.get("subject")
        if not match_value:
            continue
        pattern = f"^{re.escape(match_value)}$"
        key = (domain_value, normalized_rule_type, normalized_match_field, pattern, action)
        if key in seen:
            continue
        seen.add(key)
        created_rule = db.create_address_rule(
            settings.db_path,
            domain_value,
            normalized_rule_type,
            normalized_match_field,
            pattern,
            0,
            action,
            1,
            f"Created from quarantine selection (message {row['id']}).",
            now,
        )
        created_rules.append(created_rule)
        _log_admin_action(
            settings.db_path, f"admin_quarantine_rule_created:{created_rule['id']}", request
        )
    if not created_rules:
        if _wants_json(request):
            raise HTTPException(status_code=400, detail="No rules created from selection.")
        query = _build_quarantine_query(
            domain, sender_domain, recipient_localpart, start_date, end_date
        )
        return RedirectResponse(
            url=f"/admin/quarantine{query}&error=rule" if query else "/admin/quarantine?error=rule",
            status_code=HTTP_303_SEE_OTHER,
        )
    if _wants_json(request):
        return JSONResponse({"created_rule_ids": [row["id"] for row in created_rules]})
    query = _build_quarantine_query(domain, sender_domain, recipient_localpart, start_date, end_date)
    return RedirectResponse(
        url=f"/admin/quarantine{query}&rules_created=1"
        if query
        else "/admin/quarantine?rules_created=1",
        status_code=HTTP_303_SEE_OTHER,
    )


@app.post("/admin/messages/clear")
async def admin_clear_messages(request: Request) -> RedirectResponse:
    if not _is_admin(request):
        return RedirectResponse(url="/admin/unlock", status_code=303)
    settings = get_settings()
    deleted_count = _delete_all_messages(settings.db_path)
    _log_admin_action(settings.db_path, f"admin_messages_cleared:{deleted_count}", request)
    return RedirectResponse(url="/admin/settings?cleared=1", status_code=HTTP_303_SEE_OTHER)
