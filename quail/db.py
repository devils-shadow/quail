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
        quarantined INTEGER NOT NULL DEFAULT 0
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
]


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


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


def set_rate_limit_state(
    db_path: Path, source_ip: str, attempts: int, window_start: str
) -> None:
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
