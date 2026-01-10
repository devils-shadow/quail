"""Phase 8 acceptance coverage tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi.testclient import TestClient

from quail import db, ingest, purge, settings
from quail.web import app


@contextmanager
def _build_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")
    with TestClient(app) as client:
        yield client


def _configure_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")
    return settings.get_settings()


def _build_message(subject: str, sender: str = "sender@example.com") -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "user@m.cst.ro"
    message["Subject"] = subject
    message.set_content("Test body")
    return message


def _ingest_message(envelope_rcpt: str, subject: str) -> None:
    ingest.ingest(_build_message(subject).as_bytes(), envelope_rcpt)


def _insert_message(
    db_path,
    *,
    received_at: datetime,
    envelope_rcpt: str,
    status: str,
    quarantined: int,
    eml_path,
    subject: str,
) -> int:
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
                "Sender <sender@example.com>",
                subject,
                received_at.isoformat(),
                f"msg-{received_at.timestamp()}",
                12,
                str(eml_path),
                quarantined,
                status,
                None,
                None,
            ),
        )
        conn.commit()
    return int(cursor.lastrowid)


def _unlock_admin(client: TestClient, pin: str = "1234") -> None:
    response = client.post("/admin/unlock", data={"pin": pin}, follow_redirects=False)
    assert response.status_code == 303


def test_acceptance_open_delivers_to_inbox(tmp_path, monkeypatch) -> None:
    settings_obj = _configure_settings(tmp_path, monkeypatch)
    db.init_db(settings_obj.db_path)
    ingest.REGEX_CACHE.clear()

    _ingest_message("user@m.cst.ro", "Open delivers")

    with db.get_connection(settings_obj.db_path) as conn:
        row = conn.execute(
            "SELECT status, quarantined FROM messages ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row["status"] == "INBOX"
    assert row["quarantined"] == 0


def test_acceptance_paused_blocks_new_inbox_entries(tmp_path, monkeypatch) -> None:
    settings_obj = _configure_settings(tmp_path, monkeypatch)
    db.init_db(settings_obj.db_path)
    ingest.REGEX_CACHE.clear()

    db.upsert_domain_policy(
        settings_obj.db_path,
        "m.cst.ro",
        "PAUSED",
        "INBOX",
        None,
        datetime.now(tz=timezone.utc).isoformat(),
    )

    _ingest_message("user@m.cst.ro", "Paused policy")

    with db.get_connection(settings_obj.db_path) as conn:
        row = conn.execute("SELECT status FROM messages ORDER BY id DESC LIMIT 1").fetchone()

    assert row["status"] != "INBOX"


def test_acceptance_restricted_requires_allow_rules(tmp_path, monkeypatch) -> None:
    settings_obj = _configure_settings(tmp_path, monkeypatch)
    db.init_db(settings_obj.db_path)
    ingest.REGEX_CACHE.clear()

    db.upsert_domain_policy(
        settings_obj.db_path,
        "m.cst.ro",
        "RESTRICTED",
        "INBOX",
        None,
        datetime.now(tz=timezone.utc).isoformat(),
    )

    _ingest_message("user@m.cst.ro", "Restricted without allow")

    with db.get_connection(settings_obj.db_path) as conn:
        row = conn.execute("SELECT status FROM messages ORDER BY id DESC LIMIT 1").fetchone()

    assert row["status"] == "QUARANTINE"

    db.create_address_rule(
        settings_obj.db_path,
        "m.cst.ro",
        "ALLOW",
        "RCPT_LOCALPART",
        r"^user$",
        1,
        "INBOX",
        1,
        "Acceptance allow",
        datetime.now(tz=timezone.utc).isoformat(),
    )

    _ingest_message("user@m.cst.ro", "Restricted with allow")

    with db.get_connection(settings_obj.db_path) as conn:
        row = conn.execute("SELECT status FROM messages ORDER BY id DESC LIMIT 1").fetchone()

    assert row["status"] == "INBOX"


def test_acceptance_block_rules_default_to_quarantine(tmp_path, monkeypatch) -> None:
    settings_obj = _configure_settings(tmp_path, monkeypatch)
    db.init_db(settings_obj.db_path)
    ingest.REGEX_CACHE.clear()

    db.upsert_domain_policy(
        settings_obj.db_path,
        "m.cst.ro",
        "OPEN",
        "INBOX",
        None,
        datetime.now(tz=timezone.utc).isoformat(),
    )
    db.create_address_rule(
        settings_obj.db_path,
        "m.cst.ro",
        "BLOCK",
        "SUBJECT",
        r"spam",
        1,
        "QUARANTINE",
        1,
        "Acceptance block",
        datetime.now(tz=timezone.utc).isoformat(),
    )

    _ingest_message("user@m.cst.ro", "spam message")

    with db.get_connection(settings_obj.db_path) as conn:
        row = conn.execute("SELECT status FROM messages ORDER BY id DESC LIMIT 1").fetchone()

    assert row["status"] == "QUARANTINE"


def test_acceptance_quarantine_restore(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client)
        settings_obj = settings.get_settings()
        db.init_db(settings_obj.db_path)
        eml_path = settings_obj.eml_dir / "restore.eml"
        eml_path.parent.mkdir(parents=True, exist_ok=True)
        eml_path.write_text("Subject: Restore\n\nBody")
        message_id = _insert_message(
            settings_obj.db_path,
            received_at=datetime.now(tz=timezone.utc),
            envelope_rcpt="user@m.cst.ro",
            status="QUARANTINE",
            quarantined=1,
            eml_path=eml_path,
            subject="Restore",
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
                "SELECT status, quarantined FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()

        assert row["status"] == "INBOX"
        assert row["quarantined"] == 0


def test_acceptance_retention_purge(tmp_path, monkeypatch) -> None:
    settings_obj = _configure_settings(tmp_path, monkeypatch)
    db.init_db(settings_obj.db_path)

    db.set_setting(settings_obj.db_path, settings.SETTINGS_RETENTION_DAYS_KEY, "1")
    db.set_setting(
        settings_obj.db_path,
        settings.SETTINGS_QUARANTINE_RETENTION_DAYS_KEY,
        "1",
    )

    now = datetime.now(tz=timezone.utc)
    settings_obj.eml_dir.mkdir(parents=True, exist_ok=True)

    inbox_message = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=2),
        envelope_rcpt="user@m.cst.ro",
        status="INBOX",
        quarantined=0,
        eml_path=settings_obj.eml_dir / "inbox-expired.eml",
        subject="Inbox expired",
    )
    quarantine_message = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=2),
        envelope_rcpt="user@m.cst.ro",
        status="QUARANTINE",
        quarantined=1,
        eml_path=settings_obj.eml_dir / "quarantine-expired.eml",
        subject="Quarantine expired",
    )

    assert purge.main() == 0

    with db.get_connection(settings_obj.db_path) as conn:
        remaining = {row["id"] for row in conn.execute("SELECT id FROM messages")}

    assert inbox_message not in remaining
    assert quarantine_message not in remaining


def test_acceptance_admin_actions_logged(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client)
        settings_obj = settings.get_settings()

        response = client.post(
            "/admin/domain-policies",
            data={
                "domain": "example.com",
                "mode": "OPEN",
                "default_action": "INBOX",
            },
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )

        assert response.status_code == 200

        with db.get_connection(settings_obj.db_path) as conn:
            actions = [
                row["action"]
                for row in conn.execute("SELECT action FROM admin_actions ORDER BY id")
            ]

        assert "admin_domain_policy_upsert:example.com" in actions


def test_acceptance_inbox_ui_loads_under_expected_volume(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        settings_obj = settings.get_settings()
        db.init_db(settings_obj.db_path)

        now = datetime.now(tz=timezone.utc)
        settings_obj.eml_dir.mkdir(parents=True, exist_ok=True)
        for index in range(120):
            _insert_message(
                settings_obj.db_path,
                received_at=now,
                envelope_rcpt="user@m.cst.ro",
                status="INBOX",
                quarantined=0,
                eml_path=settings_obj.eml_dir / f"load-{index}.eml",
                subject=f"Load test {index}",
            )

        response = client.get("/inbox")

        assert response.status_code == 200
        assert "Load test 0" in response.text
        assert "Load test 119" in response.text
