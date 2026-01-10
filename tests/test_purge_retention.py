"""Tests for retention purge behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quail import db, purge, settings


def _configure_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")


def _insert_message(
    db_path,
    *,
    received_at: datetime,
    envelope_rcpt: str,
    status: str,
    quarantined: int,
    eml_path,
    attachment_path=None,
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
                "Retention",
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
        message_id = cursor.lastrowid
        if attachment_path:
            conn.execute(
                """
                INSERT INTO attachments (message_id, filename, stored_path, content_type, size_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, attachment_path.name, str(attachment_path), "application/pdf", 4),
            )
        conn.commit()
    return int(message_id)


def _write_file(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_purge_respects_quarantine_retention_overrides(tmp_path, monkeypatch) -> None:
    _configure_settings(tmp_path, monkeypatch)
    settings_obj = settings.get_settings()
    db.init_db(settings_obj.db_path)

    db.set_setting(settings_obj.db_path, settings.SETTINGS_RETENTION_DAYS_KEY, "30")
    db.set_setting(
        settings_obj.db_path,
        settings.SETTINGS_QUARANTINE_RETENTION_DAYS_KEY,
        "3",
    )
    now = datetime.now(tz=timezone.utc)
    db.upsert_domain_policy(
        settings_obj.db_path,
        "long.example",
        "OPEN",
        "INBOX",
        10,
        now.isoformat(),
    )

    settings_obj.eml_dir.mkdir(parents=True, exist_ok=True)
    settings_obj.attachment_dir.mkdir(parents=True, exist_ok=True)

    inbox_expired = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=40),
        envelope_rcpt="user@m.cst.ro",
        status="INBOX",
        quarantined=0,
        eml_path=settings_obj.eml_dir / "inbox-expired.eml",
        attachment_path=settings_obj.attachment_dir / "inbox-expired.pdf",
    )
    _write_file(settings_obj.eml_dir / "inbox-expired.eml", "Subject: retention\n\nbody")
    _write_file(settings_obj.attachment_dir / "inbox-expired.pdf", "pdf")
    inbox_keep = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=10),
        envelope_rcpt="user@m.cst.ro",
        status="INBOX",
        quarantined=0,
        eml_path=settings_obj.eml_dir / "inbox-keep.eml",
    )
    _write_file(settings_obj.eml_dir / "inbox-keep.eml", "Subject: retention\n\nbody")
    quarantine_expired = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=5),
        envelope_rcpt="user@short.example",
        status="QUARANTINE",
        quarantined=1,
        eml_path=settings_obj.eml_dir / "quarantine-expired.eml",
        attachment_path=settings_obj.attachment_dir / "quarantine-expired.pdf",
    )
    _write_file(settings_obj.eml_dir / "quarantine-expired.eml", "Subject: retention\n\nbody")
    _write_file(settings_obj.attachment_dir / "quarantine-expired.pdf", "pdf")
    quarantine_keep = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=5),
        envelope_rcpt="user@long.example",
        status="QUARANTINE",
        quarantined=1,
        eml_path=settings_obj.eml_dir / "quarantine-keep.eml",
    )
    _write_file(settings_obj.eml_dir / "quarantine-keep.eml", "Subject: retention\n\nbody")
    quarantine_expired_override = _insert_message(
        settings_obj.db_path,
        received_at=now - timedelta(days=12),
        envelope_rcpt="user@long.example",
        status="QUARANTINE",
        quarantined=1,
        eml_path=settings_obj.eml_dir / "quarantine-expired-override.eml",
        attachment_path=settings_obj.attachment_dir / "quarantine-expired-override.pdf",
    )
    _write_file(
        settings_obj.eml_dir / "quarantine-expired-override.eml",
        "Subject: retention\n\nbody",
    )
    _write_file(settings_obj.attachment_dir / "quarantine-expired-override.pdf", "pdf")

    assert purge.main() == 0

    with db.get_connection(settings_obj.db_path) as conn:
        remaining = {row["id"] for row in conn.execute("SELECT id FROM messages").fetchall()}

    assert inbox_keep in remaining
    assert quarantine_keep in remaining
    assert inbox_expired not in remaining
    assert quarantine_expired not in remaining
    assert quarantine_expired_override not in remaining

    assert (settings_obj.eml_dir / "inbox-expired.eml").exists() is False
    assert (settings_obj.attachment_dir / "inbox-expired.pdf").exists() is False
    assert (settings_obj.eml_dir / "quarantine-expired.eml").exists() is False
    assert (settings_obj.attachment_dir / "quarantine-expired.pdf").exists() is False
    assert (settings_obj.eml_dir / "quarantine-expired-override.eml").exists() is False
    assert (settings_obj.attachment_dir / "quarantine-expired-override.pdf").exists() is False


def test_purge_removes_expired_admin_actions(tmp_path, monkeypatch) -> None:
    _configure_settings(tmp_path, monkeypatch)
    settings_obj = settings.get_settings()
    db.init_db(settings_obj.db_path)
    now = datetime.now(tz=timezone.utc)

    db.log_admin_action(
        settings_obj.db_path,
        "admin_old_action",
        "127.0.0.1",
        (now - timedelta(days=31)).isoformat(),
    )
    db.log_admin_action(
        settings_obj.db_path,
        "admin_recent_action",
        "127.0.0.1",
        (now - timedelta(days=1)).isoformat(),
    )

    assert purge.main() == 0

    with db.get_connection(settings_obj.db_path) as conn:
        remaining = [row["action"] for row in conn.execute("SELECT action FROM admin_actions")]

    assert "admin_recent_action" in remaining
    assert "admin_old_action" not in remaining
