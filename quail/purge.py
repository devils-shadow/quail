"""Retention purge job for Quail.

This module implements the periodic purge task that removes email
messages older than a configured retention period. The retention
period is stored in the settings table under the key ``retention_days``.
If the key is absent the default value of 30 days is used and seeded
into the database automatically. Quarantine messages have a separate
retention policy configured via ``quarantine_retention_days``, with
optional per-domain overrides. In addition to removing database rows
this job will delete the corresponding `.eml` files and attachments
from disk.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quail import db
from quail.logging_config import configure_logging
from quail.settings import get_quarantine_retention_days, get_retention_days, get_settings

LOGGER = logging.getLogger(__name__)
BATCH_SIZE = 200
AUDIT_RETENTION_DAYS = 30


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _delete_eml(eml_path: Path) -> None:
    try:
        eml_path.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("Failed to delete eml file at %s", eml_path)


def _delete_attachment(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("Failed to delete attachment at %s", path)


def _parse_received_at(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        LOGGER.warning("Invalid received_at timestamp %s", value)
        return None


def _extract_domain(envelope_rcpt: str) -> str | None:
    if "@" not in envelope_rcpt:
        return None
    domain = envelope_rcpt.rsplit("@", maxsplit=1)[1].strip().lower()
    return domain or None


def _purge_inbox_messages(
    db_path: Path,
    conn: sqlite3.Connection,
    cutoff: datetime,
    batch_size: int,
) -> tuple[int, int]:
    purged_messages = 0
    purged_attachments = 0
    last_seen: tuple[str, int] | None = None
    while True:
        query = """
            SELECT id, received_at, envelope_rcpt, eml_path, quarantined
            FROM messages
            WHERE received_at < ?
              AND status = 'INBOX'
              AND quarantined = 0
        """
        params: list[str | int] = [cutoff.isoformat()]
        if last_seen:
            query += " AND (received_at > ? OR (received_at = ? AND id > ?))"
            params.extend([last_seen[0], last_seen[0], last_seen[1]])
        query += " ORDER BY received_at ASC, id ASC LIMIT ?"
        params.append(batch_size)
        rows = conn.execute(query, params).fetchall()
        if not rows:
            break
        for row in rows:
            attachments = conn.execute(
                "SELECT stored_path FROM attachments WHERE message_id = ?",
                (row["id"],),
            ).fetchall()
            for attachment in attachments:
                _delete_attachment(Path(attachment["stored_path"]))
                purged_attachments += 1
            _delete_eml(Path(row["eml_path"]))
            db.log_inbox_event(
                db_path,
                _now_iso(),
                "deleted",
                message_id=row["id"],
                envelope_rcpt=row["envelope_rcpt"],
                quarantined=row["quarantined"],
            )
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            purged_messages += 1
        last_seen = (rows[-1]["received_at"], rows[-1]["id"])
        conn.commit()
    return purged_messages, purged_attachments


def _purge_quarantine_messages(
    db_path: Path,
    conn: sqlite3.Connection,
    now: datetime,
    default_retention_days: int,
    overrides: dict[str, int],
    batch_size: int,
) -> tuple[int, int]:
    retention_values = [default_retention_days, *overrides.values()]
    min_retention_days = min(retention_values) if retention_values else default_retention_days
    cutoff_min = now - timedelta(days=min_retention_days)
    purged_messages = 0
    purged_attachments = 0
    last_seen: tuple[str, int] | None = None
    while True:
        query = """
            SELECT id, received_at, envelope_rcpt, eml_path, status, quarantined
            FROM messages
            WHERE received_at < ?
              AND (status != 'INBOX' OR quarantined = 1)
        """
        params: list[str | int] = [cutoff_min.isoformat()]
        if last_seen:
            query += " AND (received_at > ? OR (received_at = ? AND id > ?))"
            params.extend([last_seen[0], last_seen[0], last_seen[1]])
        query += " ORDER BY received_at ASC, id ASC LIMIT ?"
        params.append(batch_size)
        rows = conn.execute(query, params).fetchall()
        if not rows:
            break
        for row in rows:
            received_at = _parse_received_at(row["received_at"])
            if not received_at:
                last_seen = (row["received_at"], row["id"])
                continue
            domain = _extract_domain(row["envelope_rcpt"] or "")
            retention_days = overrides.get(domain, default_retention_days)
            cutoff = now - timedelta(days=retention_days)
            if received_at >= cutoff:
                last_seen = (row["received_at"], row["id"])
                continue
            attachments = conn.execute(
                "SELECT stored_path FROM attachments WHERE message_id = ?",
                (row["id"],),
            ).fetchall()
            for attachment in attachments:
                _delete_attachment(Path(attachment["stored_path"]))
                purged_attachments += 1
            _delete_eml(Path(row["eml_path"]))
            db.log_inbox_event(
                db_path,
                _now_iso(),
                "deleted",
                message_id=row["id"],
                envelope_rcpt=row["envelope_rcpt"],
                quarantined=row["quarantined"],
            )
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            purged_messages += 1
            last_seen = (row["received_at"], row["id"])
        conn.commit()
    return purged_messages, purged_attachments


def _purge_messages(
    db_path: Path,
    now: datetime,
    retention_days: int,
    quarantine_retention_days: int,
    overrides: dict[str, int],
    batch_size: int = BATCH_SIZE,
) -> tuple[int, int]:
    cutoff = now - timedelta(days=retention_days)
    with db.get_connection(db_path) as conn:
        inbox_messages, inbox_attachments = _purge_inbox_messages(
            db_path, conn, cutoff, batch_size
        )
        quarantine_messages, quarantine_attachments = _purge_quarantine_messages(
            db_path,
            conn,
            now,
            quarantine_retention_days,
            overrides,
            batch_size,
        )
    return (
        inbox_messages + quarantine_messages,
        inbox_attachments + quarantine_attachments,
    )


def _purge_admin_actions(conn: sqlite3.Connection, cutoff: datetime) -> int:
    cursor = conn.execute(
        "DELETE FROM admin_actions WHERE performed_at < ?",
        (cutoff.isoformat(),),
    )
    conn.commit()
    return cursor.rowcount


def main() -> int:
    """Entry point for the purge job.

    Configures logging, performs the purge and logs a summary.

    Returns
    -------
    int
        Exit code where 0 indicates success.
    """
    configure_logging()
    settings = get_settings()
    db.init_db(settings.db_path)

    retention_days = get_retention_days(settings.db_path)
    quarantine_retention_days = get_quarantine_retention_days(settings.db_path)
    overrides = db.get_domain_quarantine_retention_overrides(settings.db_path)
    now = datetime.now(tz=timezone.utc)

    purged_messages, purged_attachments = _purge_messages(
        settings.db_path,
        now,
        retention_days,
        quarantine_retention_days,
        overrides,
    )
    with db.get_connection(settings.db_path) as conn:
        purged_audit_actions = _purge_admin_actions(
            conn, now - timedelta(days=AUDIT_RETENTION_DAYS)
        )

    LOGGER.info(
        "Retention purge complete (retention=%s days, quarantine_retention=%s days, "
        "messages=%s, attachments=%s, audit_actions=%s).",
        retention_days,
        quarantine_retention_days,
        purged_messages,
        purged_attachments,
        purged_audit_actions,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
