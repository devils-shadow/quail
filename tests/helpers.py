"""Shared test helpers for Quail."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from quail import db, settings
from quail.web import app


def build_email(
    *,
    subject: str,
    to_addr: str,
    from_addr: str = "sender@example.com",
    text_body: str = "Test body",
    html_body: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = to_addr
    message["Subject"] = subject
    message["Date"] = datetime.now(tz=timezone.utc).isoformat()
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


def configure_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    eml_dir = data_dir / "eml"
    attachment_dir = data_dir / "att"
    db_path = data_dir / "quail.db"
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", eml_dir)
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", attachment_dir)
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", db_path)
    return settings.get_settings()


@contextmanager
def build_client(tmp_path, monkeypatch):
    settings_obj = configure_settings(tmp_path, monkeypatch)
    with TestClient(app) as client:
        yield client, settings_obj


def get_csrf_token(client: TestClient) -> str:
    token = client.cookies.get("quail_csrf")
    if token:
        return token
    response = client.get("/admin/unlock")
    assert response.status_code == 200
    token = client.cookies.get("quail_csrf")
    assert token
    return token


def unlock_admin(client: TestClient, pin: str = "1234") -> None:
    csrf_token = get_csrf_token(client)
    response = client.post(
        "/admin/unlock",
        data={"pin": pin, "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def write_eml(eml_path: Path, message: EmailMessage) -> None:
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    eml_path.write_bytes(message.as_bytes())


def insert_message(
    settings_obj,
    *,
    message: EmailMessage,
    envelope_rcpt: str,
    status: str = "INBOX",
    quarantined: int = 0,
    received_at: datetime | None = None,
) -> dict[str, object]:
    received_at = received_at or datetime.now(tz=timezone.utc)
    eml_path = settings_obj.eml_dir / f"msg-{received_at.timestamp()}-{uuid4().hex}.eml"
    write_eml(eml_path, message)
    size_bytes = eml_path.stat().st_size
    message_id = message.get("Message-ID") or f"msg-{received_at.timestamp()}"
    with db.get_connection(settings_obj.db_path) as conn:
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
                received_at.isoformat(),
                envelope_rcpt,
                message.get("From"),
                message.get("Subject"),
                message.get("Date") or received_at.isoformat(),
                message_id,
                size_bytes,
                str(eml_path),
                quarantined,
                status,
                None,
                None,
            ),
        )
        conn.commit()
    return {"id": int(cursor.lastrowid), "eml_path": eml_path}


def insert_attachment(
    settings_obj,
    *,
    message_id: int,
    filename: str,
    content_type: str,
    content: bytes,
) -> dict[str, object]:
    attachment_path = settings_obj.attachment_dir / filename
    attachment_path.parent.mkdir(parents=True, exist_ok=True)
    attachment_path.write_bytes(content)
    size_bytes = attachment_path.stat().st_size
    with db.get_connection(settings_obj.db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO attachments (message_id, filename, stored_path, content_type, size_bytes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, filename, str(attachment_path), content_type, size_bytes),
        )
        conn.commit()
    return {"id": int(cursor.lastrowid), "path": attachment_path}
