"""Postfix pipe ingest for Quail."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path
from typing import Iterable, TypedDict
from uuid import uuid4

from quail import db
from quail.logging_config import configure_logging
from quail.settings import get_settings

LOGGER = logging.getLogger(__name__)
DEFAULT_ALLOWED_MIME_TYPES = ("application/pdf",)
SETTINGS_ALLOWED_MIME_KEY = "allowed_attachment_mime_types"


class AttachmentRecord(TypedDict):
    filename: str
    stored_path: str
    content_type: str
    size_bytes: int


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
    eml_path = _write_eml(raw_bytes, settings.eml_dir)
    metadata = _extract_metadata(message)
    allowed_types = _allowed_mime_types(settings.db_path)
    attachments, quarantined = _collect_attachments(
        message,
        allowed_types,
        settings.attachment_dir,
    )

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
                quarantined
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(tz=timezone.utc).isoformat(),
                envelope_rcpt,
                metadata["from_addr"],
                metadata["subject"],
                metadata["date"],
                metadata["message_id"],
                len(raw_bytes),
                str(eml_path),
                1 if quarantined else 0,
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

    if quarantined:
        LOGGER.warning("Message quarantined due to disallowed attachment types.")


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
