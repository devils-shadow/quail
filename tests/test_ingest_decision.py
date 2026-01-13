"""Tests for ingest decision pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.message import EmailMessage

from quail import db, ingest, settings


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _insert_domain_policy(
    db_path,
    domain: str,
    mode: str,
    default_action: str,
) -> None:
    with db.get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO domain_policy (domain, mode, default_action, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (domain, mode, default_action, _now_iso(), _now_iso()),
        )
        conn.commit()


def _insert_address_rule(
    db_path,
    domain: str,
    rule_type: str,
    match_field: str,
    pattern: str,
    priority: int,
    action: str,
    enabled: int = 1,
) -> int:
    with db.get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO address_rule (
                domain, rule_type, match_field, pattern, priority, action, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                _now_iso(),
                _now_iso(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _build_message(subject: str = "Hello", from_addr: str = "sender@example.com") -> EmailMessage:
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = "user@mail.example.test"
    message["Subject"] = subject
    message.set_content("Test body")
    return message


def _configure_test_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    eml_dir = data_dir / "eml"
    attachment_dir = data_dir / "att"
    db_path = data_dir / "quail.db"
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", eml_dir)
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", attachment_dir)
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", db_path)
    return db_path


def test_open_default_routes_to_inbox(tmp_path, monkeypatch):
    db_path = _configure_test_settings(tmp_path, monkeypatch)
    db.init_db(db_path)
    ingest.REGEX_CACHE.clear()

    decision = ingest.determine_ingest_decision(db_path, "user@mail.example.test", _build_message())

    assert decision.status == "INBOX"
    assert decision.quarantine_reason is None


def test_paused_policy_routes_to_drop_or_quarantine(tmp_path, monkeypatch):
    db_path = _configure_test_settings(tmp_path, monkeypatch)
    db.init_db(db_path)
    ingest.REGEX_CACHE.clear()

    _insert_domain_policy(db_path, "mail.example.test", "PAUSED", "INBOX")
    decision = ingest.determine_ingest_decision(db_path, "user@mail.example.test", _build_message())
    assert decision.status == "DROP"

    _insert_domain_policy(db_path, "paused.example", "PAUSED", "QUARANTINE")
    decision = ingest.determine_ingest_decision(db_path, "user@paused.example", _build_message())
    assert decision.status == "QUARANTINE"


def test_restricted_requires_allow_rule(tmp_path, monkeypatch):
    db_path = _configure_test_settings(tmp_path, monkeypatch)
    db.init_db(db_path)
    ingest.REGEX_CACHE.clear()

    _insert_domain_policy(db_path, "mail.example.test", "RESTRICTED", "INBOX")
    decision = ingest.determine_ingest_decision(db_path, "user@mail.example.test", _build_message())
    assert decision.status == "QUARANTINE"

    _insert_address_rule(
        db_path,
        "mail.example.test",
        "ALLOW",
        "RCPT_LOCALPART",
        r"^user$",
        priority=1,
        action="INBOX",
    )
    decision = ingest.determine_ingest_decision(db_path, "user@mail.example.test", _build_message())
    assert decision.status == "INBOX"


def test_priority_first_match_wins(tmp_path, monkeypatch):
    db_path = _configure_test_settings(tmp_path, monkeypatch)
    db.init_db(db_path)
    ingest.REGEX_CACHE.clear()

    _insert_domain_policy(db_path, "mail.example.test", "OPEN", "INBOX")
    first_rule_id = _insert_address_rule(
        db_path,
        "mail.example.test",
        "BLOCK",
        "SUBJECT",
        r"promo",
        priority=1,
        action="DROP",
    )
    _insert_address_rule(
        db_path,
        "mail.example.test",
        "ALLOW",
        "SUBJECT",
        r"promo",
        priority=2,
        action="INBOX",
    )

    decision = ingest.determine_ingest_decision(
        db_path, "user@mail.example.test", _build_message(subject="promo")
    )

    assert decision.status == "DROP"
    assert decision.ingest_decision_meta["rule_id"] == first_rule_id


def test_ingest_persists_decision_fields(tmp_path, monkeypatch):
    db_path = _configure_test_settings(tmp_path, monkeypatch)
    db.init_db(db_path)
    ingest.REGEX_CACHE.clear()

    _insert_domain_policy(db_path, "mail.example.test", "OPEN", "QUARANTINE")
    rule_id = _insert_address_rule(
        db_path,
        "mail.example.test",
        "BLOCK",
        "FROM_DOMAIN",
        r"example.com",
        priority=1,
        action="QUARANTINE",
    )

    message = _build_message()
    ingest.ingest(message.as_bytes(), "user@mail.example.test")

    with db.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status, quarantine_reason, ingest_decision_meta FROM messages"
        ).fetchone()

    assert row["status"] == "QUARANTINE"
    assert row["quarantine_reason"]
    meta = json.loads(row["ingest_decision_meta"])
    assert meta["rule_id"] == rule_id
    assert meta["match_field"] == "FROM_DOMAIN"
    assert meta["matched_value"] == "example.com"
    assert meta["timestamp"]
