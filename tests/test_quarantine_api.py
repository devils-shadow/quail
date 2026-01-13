"""API tests for admin quarantine endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from fastapi.testclient import TestClient

from quail import db, settings
from quail.web import app

pytestmark = [pytest.mark.api, pytest.mark.integration]


@contextmanager
def _build_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")
    with TestClient(app) as client:
        yield client


def _unlock_admin(client: TestClient, pin: str = "1234") -> None:
    response = client.post("/admin/unlock", data={"pin": pin}, follow_redirects=False)
    assert response.status_code == 303


def _insert_quarantined_message(db_path, eml_path, quarantine_reason: str) -> int:
    db.init_db(db_path)
    now = datetime.now(tz=timezone.utc).isoformat()
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
                now,
                "user@mail.example.test",
                "Sender <sender@example.com>",
                "Quarantine test",
                now,
                "msg-1",
                12,
                str(eml_path),
                1,
                "QUARANTINE",
                quarantine_reason,
                None,
            ),
        )
        message_id = cursor.lastrowid
        conn.commit()
    return int(message_id)


def test_quarantine_restore_endpoint(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client, pin="1234")
        settings_obj = settings.get_settings()
        eml_path = settings_obj.eml_dir / "restore.eml"
        eml_path.parent.mkdir(parents=True, exist_ok=True)
        eml_path.write_text("Subject: Restore\n\nBody")
        message_id = _insert_quarantined_message(
            settings_obj.db_path, eml_path, "Disallowed attachment types"
        )

        response = client.post(
            "/admin/quarantine/restore",
            data={"message_id": str(message_id)},
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert response.status_code == 200
        assert response.json()["restored"] == [message_id]

        with db.get_connection(settings_obj.db_path) as conn:
            row = conn.execute(
                "SELECT status, quarantined, quarantine_reason FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        assert row["status"] == "INBOX"
        assert row["quarantined"] == 0
        assert row["quarantine_reason"] is None


def test_quarantine_delete_endpoint(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client, pin="1234")
        settings_obj = settings.get_settings()
        eml_path = settings_obj.eml_dir / "delete.eml"
        attachment_path = settings_obj.attachment_dir / "delete.pdf"
        eml_path.parent.mkdir(parents=True, exist_ok=True)
        attachment_path.parent.mkdir(parents=True, exist_ok=True)
        eml_path.write_text("Subject: Delete\n\nBody")
        attachment_path.write_text("fake")
        message_id = _insert_quarantined_message(
            settings_obj.db_path, eml_path, "Domain policy paused (DROP)"
        )
        with db.get_connection(settings_obj.db_path) as conn:
            conn.execute(
                """
                INSERT INTO attachments (message_id, filename, stored_path, content_type, size_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, "delete.pdf", str(attachment_path), "application/pdf", 4),
            )
            conn.commit()

        response = client.post(
            "/admin/quarantine/delete",
            data={"message_id": str(message_id)},
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == [message_id]

        with db.get_connection(settings_obj.db_path) as conn:
            row = conn.execute("SELECT id FROM messages WHERE id = ?", (message_id,)).fetchone()
        assert row is None
        assert not eml_path.exists()
        assert not attachment_path.exists()
