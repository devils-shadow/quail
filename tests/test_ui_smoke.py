"""UI smoke tests for core endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from quail import db, settings
from quail.web import app

pytestmark = pytest.mark.api


@contextmanager
def _build_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")
    with TestClient(app) as client:
        yield client


def _write_eml(eml_path, *, subject: str, to_addr: str) -> None:
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content("Smoke test body")
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    eml_path.write_bytes(message.as_bytes())


def _insert_message(db_path, *, eml_path, envelope_rcpt: str, subject: str) -> int:
    received_at = datetime.now(tz=timezone.utc)
    with db.get_connection(db_path) as conn:
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
                "sender@example.com",
                subject,
                received_at.isoformat(),
                f"smoke-{received_at.timestamp()}",
                12,
                str(eml_path),
                0,
                "INBOX",
                None,
                None,
            ),
        )
        conn.commit()
    return int(cursor.lastrowid)


def test_inbox_and_message_pages_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")
    settings_obj = settings.get_settings()
    db.init_db(settings_obj.db_path)

    eml_path = settings_obj.eml_dir / "smoke.eml"
    _write_eml(eml_path, subject="Smoke", to_addr="user@mail.example.test")
    message_id = _insert_message(
        settings_obj.db_path,
        eml_path=eml_path,
        envelope_rcpt="user@mail.example.test",
        subject="Smoke",
    )

    with _build_client(tmp_path, monkeypatch) as client:
        inbox_response = client.get("/inbox")
        assert inbox_response.status_code == 200

        message_response = client.get(f"/message/{message_id}")
        assert message_response.status_code == 200


def test_admin_unlock_page_loads(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        response = client.get("/admin/unlock")
        assert response.status_code == 200
