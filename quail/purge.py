"""Retention purge job for Quail.

This module implements the periodic purge task that removes email
messages older than a configured retention period. The retention
period is stored in the settings table under the key ``retention_days``.
If the key is absent the default value of 30 days is used and seeded
into the database automatically. In addition to removing database rows
this job will delete the corresponding `.eml` files from disk.
"""

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
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quail.logging_config import configure_logging
from quail import db
from quail.settings import get_settings


LOGGER = logging.getLogger(__name__)
RETENTION_KEY = "retention_days"
DEFAULT_RETENTION_DAYS = 30


def _get_retention_days(db_path: Path) -> int:
    """Retrieve the retention period from the settings table.

    If no value is configured the default is written to the database.

    Parameters
    ----------
    db_path: Path
        Database path.

    Returns
    -------
    int
        Number of days to retain messages.
    """
    value = db.get_setting(db_path, RETENTION_KEY)
    if value is None:
        db.set_setting(db_path, RETENTION_KEY, str(DEFAULT_RETENTION_DAYS))
        return DEFAULT_RETENTION_DAYS
    try:
        days = int(value)
        return days if days > 0 else DEFAULT_RETENTION_DAYS
    except ValueError:
        LOGGER.warning("Invalid retention_days setting %s; using default %s", value, DEFAULT_RETENTION_DAYS)
        return DEFAULT_RETENTION_DAYS


def purge_expired_messages() -> int:
    """Purge messages older than the configured retention period.

    Returns
    -------
    int
        Number of messages purged.
    """
    settings = get_settings()
    db.init_db(settings.db_path)
    retention_days = _get_retention_days(settings.db_path)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
    cutoff_iso = cutoff.isoformat()

    deleted_count = 0
    with db.get_connection(settings.db_path) as conn:
        rows = list(
            conn.execute(
                "SELECT id, eml_path FROM messages WHERE received_at < ?",
                (cutoff_iso,),
            )
        )
        for row in rows:
            eml_path = Path(row["eml_path"])
            try:
                os.remove(eml_path)
            except FileNotFoundError:
                LOGGER.debug("EML file %s already removed", eml_path)
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            deleted_count += 1
        conn.commit()
    return deleted_count


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
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)

    purged_messages = _purge_messages(settings.db_path, cutoff)
    purged_attachments = _purge_old_attachments(settings.attachment_dir, cutoff)

    LOGGER.info(
        "Retention purge complete (retention=%s days, messages=%s, attachments=%s).",
        retention_days,
        purged_messages,
        purged_attachments,
    )
    purged = purge_expired_messages()
    LOGGER.info("Purged %s expired messages", purged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
