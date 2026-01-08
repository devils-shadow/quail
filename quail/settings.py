"""Configuration helpers for Quail."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    eml_dir: Path
    attachment_dir: Path
    db_path: Path
    max_message_size_mb: int


DEFAULT_DATA_DIR = Path(os.getenv("QUAIL_DATA_DIR", "/var/lib/quail"))
DEFAULT_EML_DIR = Path(os.getenv("QUAIL_EML_DIR", str(DEFAULT_DATA_DIR / "eml")))
DEFAULT_ATTACHMENT_DIR = Path(
    os.getenv("QUAIL_ATTACHMENT_DIR", str(DEFAULT_DATA_DIR / "att"))
)
DEFAULT_DB_PATH = Path(os.getenv("QUAIL_DB_PATH", str(DEFAULT_DATA_DIR / "quail.db")))
DEFAULT_MAX_MESSAGE_SIZE_MB = int(os.getenv("QUAIL_MAX_MESSAGE_SIZE_MB", "10"))


def get_settings() -> Settings:
    return Settings(
        data_dir=DEFAULT_DATA_DIR,
        eml_dir=DEFAULT_EML_DIR,
        attachment_dir=DEFAULT_ATTACHMENT_DIR,
        db_path=DEFAULT_DB_PATH,
        max_message_size_mb=DEFAULT_MAX_MESSAGE_SIZE_MB,
    )
