"""Basic smoke tests for Quail."""

from __future__ import annotations

import sqlite3

from quail import db, settings


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "quail.db"
    db.init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()

    table_names = {row[0] for row in rows}

    assert "messages" in table_names
    assert "attachments" in table_names
    assert "settings" in table_names
    assert "admin_actions" in table_names
    assert "admin_rate_limits" in table_names


def test_get_retention_days_sets_default(tmp_path):
    db_path = tmp_path / "quail.db"
    db.init_db(db_path)

    retention = settings.get_retention_days(db_path)

    assert retention == settings.DEFAULT_RETENTION_DAYS
    assert db.get_setting(db_path, settings.SETTINGS_RETENTION_DAYS_KEY) == str(
        settings.DEFAULT_RETENTION_DAYS
    )
