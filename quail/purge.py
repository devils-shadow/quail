"""Retention purge job for Quail."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quail import db
from quail.logging_config import configure_logging
from quail.settings import get_retention_days, get_settings

LOGGER = logging.getLogger(__name__)


def _delete_eml(eml_path: Path) -> None:
    try:
        eml_path.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("Failed to delete eml file at %s", eml_path)


def _purge_old_attachments(attachment_dir: Path, cutoff: datetime) -> int:
    if not attachment_dir.exists():
        return 0
    deleted = 0
    for path in attachment_dir.rglob("*"):
        if path.is_file():
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                LOGGER.exception("Failed to stat attachment %s", path)
                continue
            if mtime < cutoff:
                try:
                    path.unlink()
                    deleted += 1
                except OSError:
                    LOGGER.exception("Failed to delete attachment %s", path)
    for path in sorted(attachment_dir.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                continue
    return deleted


def _purge_messages(db_path: Path, cutoff: datetime) -> int:
    with db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, eml_path FROM messages WHERE received_at < ? ORDER BY received_at",
            (cutoff.isoformat(),),
        ).fetchall()
        purged = 0
        for row in rows:
            _delete_eml(Path(row["eml_path"]))
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            purged += 1
        conn.commit()
        return purged


def main() -> int:
    configure_logging()
    settings = get_settings()
    db.init_db(settings.db_path)

    retention_days = get_retention_days(settings.db_path)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)

    purged_messages = _purge_messages(settings.db_path, cutoff)
    purged_attachments = _purge_old_attachments(settings.attachment_dir, cutoff)

    LOGGER.info(
        "Retention purge complete (retention=%s days, messages=%s, attachments=%s).",
        retention_days,
        purged_messages,
        purged_attachments,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
