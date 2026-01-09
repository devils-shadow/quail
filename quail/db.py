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


def log_admin_action(db_path: Path, action: str, source_ip: str, performed_at: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO admin_actions (action, source_ip, performed_at) VALUES (?, ?, ?)",
            (action, source_ip, performed_at),
        )
        conn.commit()


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
            SELECT domain, mode, default_action, created_at, updated_at
            FROM domain_policy
            ORDER BY domain ASC
            """
        ).fetchall()
    return list(rows)


def upsert_domain_policy(
    db_path: Path, domain: str, mode: str, default_action: str, now: str
) -> sqlite3.Row:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO domain_policy (domain, mode, default_action, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                mode = excluded.mode,
                default_action = excluded.default_action,
                updated_at = excluded.updated_at
            """,
            (domain, mode, default_action, now, now),
        )
        row = conn.execute(
            """
            SELECT domain, mode, default_action, created_at, updated_at
            FROM domain_policy
            WHERE domain = ?
            """,
            (domain,),
        ).fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("Failed to upsert domain policy.")
    return row


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
