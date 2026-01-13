"""Tests for ingest metrics aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quail import db, web


def _insert_message(
    db_path,
    *,
    received_at: datetime,
    envelope_rcpt: str,
    from_addr: str,
    status: str,
    quarantined: int,
) -> None:
    with db.get_connection(db_path) as conn:
        conn.execute(
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
                from_addr,
                "Metrics",
                received_at.isoformat(),
                f"msg-{received_at.timestamp()}",
                12,
                "metrics.eml",
                quarantined,
                status,
                None,
                None,
            ),
        )
        conn.commit()


def test_ingest_metrics_last_24h(tmp_path) -> None:
    db_path = tmp_path / "quail.db"
    db.init_db(db_path)
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)

    _insert_message(
        db_path,
        received_at=now - timedelta(hours=1),
        envelope_rcpt="inbox@mail.example.test",
        from_addr="Alice <alice@example.com>",
        status="INBOX",
        quarantined=0,
    )
    _insert_message(
        db_path,
        received_at=now - timedelta(hours=2),
        envelope_rcpt="quarantine@mail.example.test",
        from_addr="Bob <bob@sample.com>",
        status="QUARANTINE",
        quarantined=1,
    )
    _insert_message(
        db_path,
        received_at=now - timedelta(hours=3),
        envelope_rcpt="drop@mail.example.test",
        from_addr="Eve <eve@example.com>",
        status="DROP",
        quarantined=1,
    )
    _insert_message(
        db_path,
        received_at=now - timedelta(days=2),
        envelope_rcpt="old@mail.example.test",
        from_addr="Old <old@old.com>",
        status="INBOX",
        quarantined=0,
    )

    metrics = web._get_ingest_metrics(db_path, now=now)

    assert metrics["inbox_count"] == 2
    assert metrics["quarantine_count"] == 1
    assert metrics["dropped_last_24h"] == 1
    assert metrics["ingest_last_24h"] == 3
    assert metrics["recent_ingest_rate"] == pytest.approx(3 / 24)
    assert metrics["top_sender_domains"][0] == {"domain": "example.com", "count": 2}
