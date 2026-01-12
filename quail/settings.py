"""Configuration helpers for Quail."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from quail import db


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    eml_dir: Path
    attachment_dir: Path
    db_path: Path
    max_message_size_mb: int


DEFAULT_DATA_DIR = Path(os.getenv("QUAIL_DATA_DIR", "/var/lib/quail"))
DEFAULT_EML_DIR = Path(os.getenv("QUAIL_EML_DIR", str(DEFAULT_DATA_DIR / "eml")))
DEFAULT_ATTACHMENT_DIR = Path(os.getenv("QUAIL_ATTACHMENT_DIR", str(DEFAULT_DATA_DIR / "att")))
DEFAULT_DB_PATH = Path(os.getenv("QUAIL_DB_PATH", str(DEFAULT_DATA_DIR / "quail.db")))
DEFAULT_MAX_MESSAGE_SIZE_MB = int(os.getenv("QUAIL_MAX_MESSAGE_SIZE_MB", "10"))
DEFAULT_RETENTION_DAYS = int(os.getenv("QUAIL_RETENTION_DAYS", "30"))
DEFAULT_QUARANTINE_RETENTION_DAYS = int(os.getenv("QUAIL_QUARANTINE_RETENTION_DAYS", "3"))
SETTINGS_RETENTION_DAYS_KEY = "retention_days"
SETTINGS_QUARANTINE_RETENTION_DAYS_KEY = "quarantine_retention_days"


def get_settings() -> Settings:
    return Settings(
        data_dir=DEFAULT_DATA_DIR,
        eml_dir=DEFAULT_EML_DIR,
        attachment_dir=DEFAULT_ATTACHMENT_DIR,
        db_path=DEFAULT_DB_PATH,
        max_message_size_mb=DEFAULT_MAX_MESSAGE_SIZE_MB,
    )


def get_retention_days(db_path: Path) -> int:
    value = db.get_setting(db_path, SETTINGS_RETENTION_DAYS_KEY)
    if value is None:
        db.set_setting(db_path, SETTINGS_RETENTION_DAYS_KEY, str(DEFAULT_RETENTION_DAYS))
        return DEFAULT_RETENTION_DAYS
    try:
        retention_days = int(value)
    except ValueError:
        retention_days = DEFAULT_RETENTION_DAYS
    if retention_days < 1:
        retention_days = DEFAULT_RETENTION_DAYS
    if str(retention_days) != value:
        db.set_setting(db_path, SETTINGS_RETENTION_DAYS_KEY, str(retention_days))
    return retention_days


def get_quarantine_retention_days(db_path: Path) -> int:
    value = db.get_setting(db_path, SETTINGS_QUARANTINE_RETENTION_DAYS_KEY)
    if value is None:
        db.set_setting(
            db_path,
            SETTINGS_QUARANTINE_RETENTION_DAYS_KEY,
            str(DEFAULT_QUARANTINE_RETENTION_DAYS),
        )
        return DEFAULT_QUARANTINE_RETENTION_DAYS
    try:
        retention_days = int(value)
    except ValueError:
        retention_days = DEFAULT_QUARANTINE_RETENTION_DAYS
    if retention_days < 1:
        retention_days = DEFAULT_QUARANTINE_RETENTION_DAYS
    if str(retention_days) != value:
        db.set_setting(db_path, SETTINGS_QUARANTINE_RETENTION_DAYS_KEY, str(retention_days))
    return retention_days
