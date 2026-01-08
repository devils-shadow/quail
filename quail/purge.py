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
    purged = purge_expired_messages()
    LOGGER.info("Purged %s expired messages", purged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
