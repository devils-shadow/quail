"""Retention purge job for Quail."""

from __future__ import annotations

from quail.logging_config import configure_logging


def main() -> int:
    configure_logging()
    # TODO: implement retention purge job.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
