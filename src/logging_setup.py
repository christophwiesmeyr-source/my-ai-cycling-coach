"""App-wide logging configuration — call configure_logging() once at startup."""

import logging
from logging.handlers import RotatingFileHandler

from src.constants import APP_DIR, LOG_PATH

_MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
_BACKUP_COUNT = 3


def configure_logging(level: int = logging.DEBUG) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
