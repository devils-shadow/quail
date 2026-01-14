"""SQLite helpers for Quail."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at TEXT NOT NULL,
        envelope_rcpt TEXT NOT NULL,
        from_addr TEXT,
        subject TEXT,
        date TEXT,
        message_id TEXT,
        size_bytes INTEGER NOT NULL,
        eml_path TEXT NOT NULL,
        quarantined INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'INBOX',
        quarantine_reason TEXT,
        ingest_decision_meta TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        content_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        actor TEXT,
        entity TEXT,
        before_state TEXT,
        after_state TEXT,
        source_ip TEXT NOT NULL,
        performed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_rate_limits (
        source_ip TEXT PRIMARY KEY,
        attempts INTEGER NOT NULL,
        window_start TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS domain_policy (
        id INTEGER PRIMARY KEY,
        domain TEXT UNIQUE NOT NULL,
        mode TEXT NOT NULL,
        default_action TEXT NOT NULL,
        quarantine_retention_days INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS address_rule (
        id INTEGER PRIMARY KEY,
        domain TEXT NOT NULL,
        rule_type TEXT NOT NULL,
        match_field TEXT NOT NULL,
        pattern TEXT NOT NULL,
        priority INTEGER NOT NULL,
        action TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT,
        recipient_domain TEXT,
        recipient_localpart TEXT,
        sender_domain TEXT,
        source_ip TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at TEXT NOT NULL,
        envelope_rcpt TEXT,
        status TEXT NOT NULL,
        error_summary TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inbox_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at TEXT NOT NULL,
        event_type TEXT NOT NULL,
        message_id INTEGER,
        envelope_rcpt TEXT,
        quarantined INTEGER NOT NULL DEFAULT 0
    )
    """,
]


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        _ensure_message_columns(conn)
        _ensure_admin_action_columns(conn)
        _ensure_domain_policy_columns(conn)
        conn.commit()


def _ensure_message_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
    }
    if "status" not in existing_columns:
        conn.execute("ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'INBOX'")
    if "quarantine_reason" not in existing_columns:
        conn.execute("ALTER TABLE messages ADD COLUMN quarantine_reason TEXT")
    if "ingest_decision_meta" not in existing_columns:
        conn.execute("ALTER TABLE messages ADD COLUMN ingest_decision_meta TEXT")


def _ensure_domain_policy_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(domain_policy)").fetchall()
    }
    if "quarantine_retention_days" not in existing_columns:
        conn.execute("ALTER TABLE domain_policy ADD COLUMN quarantine_retention_days INTEGER")


def _ensure_admin_action_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(admin_actions)").fetchall()
    }
    if "actor" not in existing_columns:
        conn.execute("ALTER TABLE admin_actions ADD COLUMN actor TEXT")
    if "entity" not in existing_columns:
        conn.execute("ALTER TABLE admin_actions ADD COLUMN entity TEXT")
    if "before_state" not in existing_columns:
        conn.execute("ALTER TABLE admin_actions ADD COLUMN before_state TEXT")
    if "after_state" not in existing_columns:
        conn.execute("ALTER TABLE admin_actions ADD COLUMN after_state TEXT")


def get_setting(db_path: Path, key: str) -> str | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(db_path: Path, key: str, value: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def iter_settings(db_path: Path) -> Iterable[sqlite3.Row]:
    with get_connection(db_path) as conn:
        yield from conn.execute("SELECT key, value FROM settings ORDER BY key")


def log_admin_action(
    db_path: Path,
    action: str,
    source_ip: str,
    performed_at: str,
    actor: str | None = None,
    entity: str | None = None,
    before_state: str | None = None,
    after_state: str | None = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO admin_actions (
                action,
                actor,
                entity,
                before_state,
                after_state,
                source_ip,
                performed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                actor,
                entity,
                before_state,
                after_state,
                source_ip,
                performed_at,
            ),
        )
        conn.commit()


def log_ingest_decision(
    db_path: Path,
    message_id: int,
    decision: str,
    reason: str | None,
    recipient_domain: str | None,
    recipient_localpart: str | None,
    sender_domain: str | None,
    source_ip: str | None,
    created_at: str,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingest_decisions (
                message_id,
                decision,
                reason,
                recipient_domain,
                recipient_localpart,
                sender_domain,
                source_ip,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                decision,
                reason,
                recipient_domain,
                recipient_localpart,
                sender_domain,
                source_ip,
                created_at,
            ),
        )
        conn.commit()


def log_ingest_attempt(
    db_path: Path,
    occurred_at: str,
    status: str,
    envelope_rcpt: str | None = None,
    error_summary: str | None = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingest_attempts (occurred_at, envelope_rcpt, status, error_summary)
            VALUES (?, ?, ?, ?)
            """,
            (occurred_at, envelope_rcpt, status, error_summary),
        )
        conn.commit()


def list_ingest_attempts(db_path: Path, limit: int = 20) -> Iterable[sqlite3.Row]:
    with get_connection(db_path) as conn:
        yield from conn.execute(
            """
            SELECT occurred_at, envelope_rcpt, status, error_summary
            FROM ingest_attempts
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (limit,),
        )


def log_inbox_event(
    db_path: Path,
    occurred_at: str,
    event_type: str,
    message_id: int | None = None,
    envelope_rcpt: str | None = None,
    quarantined: int = 0,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO inbox_events (
                occurred_at,
                event_type,
                message_id,
                envelope_rcpt,
                quarantined
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (occurred_at, event_type, message_id, envelope_rcpt, quarantined),
        )
        conn.commit()


def list_inbox_events(db_path: Path, since_id: int, limit: int = 100) -> Iterable[sqlite3.Row]:
    with get_connection(db_path) as conn:
        yield from conn.execute(
            """
            SELECT id, event_type, message_id, envelope_rcpt, quarantined
            FROM inbox_events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (since_id, limit),
        )


def get_last_inbox_event_id(db_path: Path) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS last_id FROM inbox_events").fetchone()
        return int(row["last_id"] or 0)


def get_rate_limit_state(db_path: Path, source_ip: str) -> sqlite3.Row | None:
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT source_ip, attempts, window_start FROM admin_rate_limits WHERE source_ip = ?",
            (source_ip,),
        ).fetchone()


def set_rate_limit_state(db_path: Path, source_ip: str, attempts: int, window_start: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO admin_rate_limits (source_ip, attempts, window_start) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(source_ip) DO UPDATE SET "
            "attempts = excluded.attempts, window_start = excluded.window_start",
            (source_ip, attempts, window_start),
        )
        conn.commit()


def clear_rate_limit_state(db_path: Path, source_ip: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM admin_rate_limits WHERE source_ip = ?", (source_ip,))
        conn.commit()


def list_domain_policies(db_path: Path) -> list[sqlite3.Row]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                domain,
                mode,
                default_action,
                quarantine_retention_days,
                created_at,
                updated_at
            FROM domain_policy
            ORDER BY domain ASC
            """
        ).fetchall()
    return list(rows)


def get_domain_policy(db_path: Path, domain: str) -> sqlite3.Row | None:
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT
                domain,
                mode,
                default_action,
                quarantine_retention_days,
                created_at,
                updated_at
            FROM domain_policy
            WHERE domain = ?
            """,
            (domain,),
        ).fetchone()


def upsert_domain_policy(
    db_path: Path,
    domain: str,
    mode: str,
    default_action: str,
    quarantine_retention_days: int | None,
    now: str,
) -> sqlite3.Row:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO domain_policy (
                domain,
                mode,
                default_action,
                quarantine_retention_days,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                mode = excluded.mode,
                default_action = excluded.default_action,
                quarantine_retention_days = excluded.quarantine_retention_days,
                updated_at = excluded.updated_at
            """,
            (domain, mode, default_action, quarantine_retention_days, now, now),
        )
        row = conn.execute(
            """
            SELECT
                domain,
                mode,
                default_action,
                quarantine_retention_days,
                created_at,
                updated_at
            FROM domain_policy
            WHERE domain = ?
            """,
            (domain,),
        ).fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("Failed to upsert domain policy.")
    return row


def list_address_rules(db_path: Path, domain: str) -> list[sqlite3.Row]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                created_at,
                updated_at
            FROM address_rule
            WHERE domain = ?
            ORDER BY priority ASC, id ASC
            """,
            (domain,),
        ).fetchall()
    return list(rows)


def get_domain_quarantine_retention_overrides(db_path: Path) -> dict[str, int]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT domain, quarantine_retention_days
            FROM domain_policy
            WHERE quarantine_retention_days IS NOT NULL
            """
        ).fetchall()
    overrides: dict[str, int] = {}
    for row in rows:
        try:
            value = int(row["quarantine_retention_days"])
        except (TypeError, ValueError):
            continue
        if value > 0:
            overrides[row["domain"]] = value
    return overrides


def create_address_rule(
    db_path: Path,
    domain: str,
    rule_type: str,
    match_field: str,
    pattern: str,
    priority: int,
    action: str,
    enabled: int,
    note: str | None,
    now: str,
) -> sqlite3.Row:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO address_rule (
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                now,
                now,
            ),
        )
        rule_id = cursor.lastrowid
        row = conn.execute(
            """
            SELECT
                id,
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                created_at,
                updated_at
            FROM address_rule
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("Failed to create address rule.")
    return row


def get_address_rule(db_path: Path, rule_id: int) -> sqlite3.Row | None:
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT
                id,
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                created_at,
                updated_at
            FROM address_rule
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()


def update_address_rule(
    db_path: Path,
    rule_id: int,
    rule_type: str,
    match_field: str,
    pattern: str,
    priority: int,
    action: str,
    enabled: int,
    note: str | None,
    now: str,
) -> sqlite3.Row | None:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE address_rule
            SET
                rule_type = ?,
                match_field = ?,
                pattern = ?,
                priority = ?,
                action = ?,
                enabled = ?,
                note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                now,
                rule_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT
                id,
                domain,
                rule_type,
                match_field,
                pattern,
                priority,
                action,
                enabled,
                note,
                created_at,
                updated_at
            FROM address_rule
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        conn.commit()
    return row


def delete_address_rule(db_path: Path, rule_id: int) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM address_rule WHERE id = ?", (rule_id,))
        conn.commit()
        return cursor.rowcount > 0


def list_messages(db_path: Path, include_quarantined: bool) -> Iterable[sqlite3.Row]:
    query = """
        SELECT
            id,
            received_at,
            envelope_rcpt,
            from_addr,
            subject,
            date,
            message_id,
            size_bytes,
            eml_path,
            quarantined
        FROM messages
    """
    params: tuple[()] | tuple[int]
    if include_quarantined:
        params = ()
    else:
        query += " WHERE quarantined = ?"
        params = (0,)
    query += " ORDER BY received_at DESC"
    with get_connection(db_path) as conn:
        yield from conn.execute(query, params)
