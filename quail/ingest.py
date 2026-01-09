"""Postfix pipe ingest for Quail."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
from typing import Iterable, TypedDict
from uuid import uuid4

from quail import db
from quail.logging_config import configure_logging
from quail.settings import get_settings

LOGGER = logging.getLogger(__name__)
DEFAULT_ALLOWED_MIME_TYPES = ("application/pdf",)
SETTINGS_ALLOWED_MIME_KEY = "allowed_attachment_mime_types"
DECISION_STATUSES = ("INBOX", "QUARANTINE", "DROP")
DOMAIN_MODES = ("OPEN", "RESTRICTED", "PAUSED")
RULE_TYPES = ("ALLOW", "BLOCK")
MATCH_FIELDS = ("RCPT_LOCALPART", "MAIL_FROM", "FROM_DOMAIN", "SUBJECT")
RULE_ALLOW_DEFAULT = "INBOX"
RULE_BLOCK_DEFAULT = "QUARANTINE"
DOMAIN_DEFAULT_MODE = "OPEN"
DOMAIN_DEFAULT_ACTION = "INBOX"
REGEX_CACHE: dict[str, re.Pattern[str]] = {}


class AttachmentRecord(TypedDict):
    filename: str
    stored_path: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class IngestDecision:
    status: str
    quarantine_reason: str | None
    ingest_decision_meta: dict[str, str | int | None]


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quail ingest")
    parser.add_argument(
        "envelope_rcpt",
        nargs="?",
        default=os.getenv("QUAIL_RCPT", ""),
        help="Envelope recipient provided by Postfix",
    )
    return parser.parse_args(list(argv))


def _allowed_mime_types(db_path: Path) -> set[str]:
    value = db.get_setting(db_path, SETTINGS_ALLOWED_MIME_KEY)
    if not value:
        db.set_setting(db_path, SETTINGS_ALLOWED_MIME_KEY, ",".join(DEFAULT_ALLOWED_MIME_TYPES))
        return set(DEFAULT_ALLOWED_MIME_TYPES)
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _sanitize_filename(filename: str | None) -> str:
    if not filename:
        filename = "attachment"
    cleaned = filename.replace("\x00", "").replace("\\", "/")
    cleaned = Path(cleaned).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned or "attachment"


def _collect_attachments(
    message: Message,
    allowed_types: set[str],
    attachment_dir: Path,
) -> tuple[list[AttachmentRecord], bool]:
    attachment_dir.mkdir(parents=True, exist_ok=True)
    attachments: list[AttachmentRecord] = []
    has_disallowed = False
    for part in message.walk():
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if disposition != "attachment" and not filename:
            continue
        content_type = part.get_content_type().lower()
        if content_type not in allowed_types:
            has_disallowed = True
            continue
        payload = part.get_payload(decode=True) or b""
        safe_name = _sanitize_filename(filename)
        stored_name = f"{uuid4().hex}_{safe_name}"
        stored_path = attachment_dir / stored_name
        stored_path.write_bytes(payload)
        attachments.append(
            {
                "filename": safe_name,
                "stored_path": str(stored_path),
                "content_type": content_type,
                "size_bytes": len(payload),
            }
        )
    return attachments, has_disallowed


def _extract_metadata(message: Message) -> dict[str, str | None]:
    return {
        "from_addr": message.get("From"),
        "subject": message.get("Subject"),
        "date": message.get("Date"),
        "message_id": message.get("Message-ID"),
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _split_envelope_rcpt(envelope_rcpt: str) -> tuple[str, str]:
    localpart, _, domain = envelope_rcpt.partition("@")
    return localpart, domain.lower()


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


def _get_cached_regex(pattern: str) -> re.Pattern[str] | None:
    compiled = REGEX_CACHE.get(pattern)
    if compiled is not None:
        return compiled
    try:
        compiled = re.compile(pattern)
    except re.error:
        LOGGER.warning("Invalid regex pattern in address_rule: %s", pattern)
        return None
    REGEX_CACHE[pattern] = compiled
    return compiled


def _load_domain_policy(conn: sqlite3.Connection, domain: str) -> dict[str, str]:
    row = conn.execute(
        "SELECT id, domain, mode, default_action FROM domain_policy WHERE domain = ?",
        (domain,),
    ).fetchone()
    if row:
        return dict(row)
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO domain_policy (domain, mode, default_action, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (domain, DOMAIN_DEFAULT_MODE, DOMAIN_DEFAULT_ACTION, now, now),
    )
    conn.commit()
    return {
        "domain": domain,
        "mode": DOMAIN_DEFAULT_MODE,
        "default_action": DOMAIN_DEFAULT_ACTION,
    }


def _load_address_rules(conn: sqlite3.Connection, domain: str) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT id, domain, rule_type, match_field, pattern, priority, action, enabled
        FROM address_rule
        WHERE domain = ? AND enabled = 1
        ORDER BY priority ASC, id ASC
        """,
        (domain,),
    ).fetchall()
    return [dict(row) for row in rows]


def _match_value(
    match_field: str,
    envelope_rcpt: str,
    message: Message,
) -> str:
    localpart, _ = _split_envelope_rcpt(envelope_rcpt)
    from_addr = _extract_primary_address(message.get("From"))
    from_domain = _extract_domain(from_addr)
    subject = message.get("Subject")
    mapping = {
        "RCPT_LOCALPART": localpart,
        "MAIL_FROM": from_addr or "",
        "FROM_DOMAIN": from_domain or "",
        "SUBJECT": subject or "",
    }
    return mapping.get(match_field, "")


def _normalize_status(action: str | None) -> str:
    if not action:
        return DOMAIN_DEFAULT_ACTION
    normalized = action.upper()
    if normalized not in DECISION_STATUSES:
        LOGGER.warning("Unknown action %s in policy/rule; defaulting to INBOX", action)
        return DOMAIN_DEFAULT_ACTION
    return normalized


def determine_ingest_decision(db_path: Path, envelope_rcpt: str, message: Message) -> IngestDecision:
    _, domain = _split_envelope_rcpt(envelope_rcpt)
    decision_meta: dict[str, str | int | None] = {
        "rule_id": None,
        "rule_type": None,
        "match_field": None,
        "matched_value": None,
        "timestamp": _now_iso(),
    }
    with db.get_connection(db_path) as conn:
        policy = _load_domain_policy(conn, domain)
        rules = _load_address_rules(conn, domain)

    mode = (policy.get("mode") or DOMAIN_DEFAULT_MODE).upper()
    if mode not in DOMAIN_MODES:
        LOGGER.warning("Unknown domain policy mode %s; defaulting to OPEN", mode)
        mode = DOMAIN_DEFAULT_MODE
    default_action = _normalize_status(policy.get("default_action"))

    if mode == "PAUSED":
        status = "QUARANTINE" if default_action == "QUARANTINE" else "DROP"
        reason = f"Domain policy paused ({status})"
        return IngestDecision(status=status, quarantine_reason=reason, ingest_decision_meta=decision_meta)

    for rule in rules:
        match_field = rule.get("match_field", "")
        if match_field not in MATCH_FIELDS:
            continue
        match_value = _match_value(match_field, envelope_rcpt, message)
        compiled = _get_cached_regex(rule.get("pattern", ""))
        if not compiled:
            continue
        if compiled.search(match_value):
            rule_type = (rule.get("rule_type") or "").upper()
            if rule_type not in RULE_TYPES:
                LOGGER.warning("Unknown rule type %s for rule %s", rule_type, rule.get("id"))
                continue
            action = _normalize_status(rule.get("action"))
            if rule_type == "ALLOW" and action == DOMAIN_DEFAULT_ACTION:
                action = RULE_ALLOW_DEFAULT
            if rule_type == "BLOCK" and action == DOMAIN_DEFAULT_ACTION:
                action = RULE_BLOCK_DEFAULT
            decision_meta.update(
                {
                    "rule_id": rule.get("id"),
                    "rule_type": rule_type,
                    "match_field": match_field,
                    "matched_value": match_value,
                }
            )
            reason = f"Rule {rule.get('id')} {rule_type} matched {match_field}"
            return IngestDecision(status=action, quarantine_reason=reason, ingest_decision_meta=decision_meta)

    if mode == "RESTRICTED":
        return IngestDecision(
            status="QUARANTINE",
            quarantine_reason="Restricted domain without allow rule",
            ingest_decision_meta=decision_meta,
        )

    reason = None
    if default_action != "INBOX":
        reason = f"Domain default action {default_action}"
    return IngestDecision(
        status=default_action,
        quarantine_reason=reason,
        ingest_decision_meta=decision_meta,
    )


def _write_eml(raw_bytes: bytes, eml_dir: Path) -> Path:
    eml_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{uuid4().hex}.eml"
    eml_path = eml_dir / filename
    eml_path.write_bytes(raw_bytes)
    return eml_path


def ingest(raw_bytes: bytes, envelope_rcpt: str) -> None:
    settings = get_settings()
    db.init_db(settings.db_path)

    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    decision = determine_ingest_decision(settings.db_path, envelope_rcpt, message)
    eml_path = _write_eml(raw_bytes, settings.eml_dir)
    metadata = _extract_metadata(message)
    allowed_types = _allowed_mime_types(settings.db_path)
    attachments, quarantined = _collect_attachments(
        message,
        allowed_types,
        settings.attachment_dir,
    )

    status = decision.status
    quarantine_reason = decision.quarantine_reason
    decision_meta = decision.ingest_decision_meta
    if quarantined:
        status = "QUARANTINE"
        quarantine_reason = "Disallowed attachment types"
    is_quarantined = status != "INBOX"

    with db.get_connection(settings.db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                received_at,
                envelope_rcpt,
                from_addr,
                subject,
                date,
                message_id,
                size_bytes,
                eml_path,
                quarantined,
                status,
                quarantine_reason,
                ingest_decision_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now_iso(),
                envelope_rcpt,
                metadata["from_addr"],
                metadata["subject"],
                metadata["date"],
                metadata["message_id"],
                len(raw_bytes),
                str(eml_path),
                1 if is_quarantined else 0,
                status,
                quarantine_reason,
                json.dumps(decision_meta),
            ),
        )
        message_id = cursor.lastrowid
        if attachments:
            conn.executemany(
                """
                INSERT INTO attachments (
                    message_id,
                    filename,
                    stored_path,
                    content_type,
                    size_bytes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        message_id,
                        attachment["filename"],
                        attachment["stored_path"],
                        attachment["content_type"],
                        attachment["size_bytes"],
                    )
                    for attachment in attachments
                ],
            )
        conn.commit()

    if status == "DROP":
        LOGGER.warning("Message dropped by ingest policy for %s.", envelope_rcpt)
    elif status == "QUARANTINE":
        LOGGER.warning("Message quarantined for %s: %s", envelope_rcpt, quarantine_reason)


def main(argv: Iterable[str] | None = None) -> int:
    configure_logging()
    args = _parse_args(argv or sys.argv[1:])

    raw_bytes = sys.stdin.buffer.read()
    if not raw_bytes:
        LOGGER.error("No email content received on stdin.")
        return 1

    settings = get_settings()
    max_bytes = settings.max_message_size_mb * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        LOGGER.error(
            "Message size %s exceeds configured max %s MB; dropping.",
            len(raw_bytes),
            settings.max_message_size_mb,
        )
        return 0

    envelope_rcpt = args.envelope_rcpt or "unknown"
    ingest(raw_bytes, envelope_rcpt)
    LOGGER.info("Message ingested for recipient %s.", envelope_rcpt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
