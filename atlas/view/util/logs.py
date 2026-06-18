import logging
import os
from logging import INFO
from logging.handlers import RotatingFileHandler

from atlas.api.paths import APP_LOG_DIR, APP_LOG_FILE

FORMAT = '%(asctime)s %(levelname)s [%(module_path)s:%(lineno)s - %(funcName)s()] - %(message)s'

# Keep a small rotating on-disk record of recent runs so an issue (e.g. from a GUI session) can be
# diagnosed after the fact without re-running. Capped so it never becomes a standing disk cost.
_MAX_BYTES = 1024 * 1024   # 1 MiB per file
_BACKUP_COUNT = 3          # → at most ~4 MiB total


class FilePathFilter(logging.Filter):

    def filter(self, record):
        record.module_path = record.pathname.split('site-packages/')[1] if 'site-packages' in record.pathname else str(record.pathname)
        return True


def _file_handler():
    """A rotating handler writing to APP_LOG_FILE; None if it can't be created (never break boot)."""
    try:
        os.makedirs(APP_LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(APP_LOG_FILE, maxBytes=_MAX_BYTES,
                                      backupCount=_BACKUP_COUNT, encoding='utf-8')
        handler.setFormatter(logging.Formatter(FORMAT))
        return handler
    except Exception:
        return None


def new_logger(name: str, enabled: bool) -> logging.Logger:
    instance = logging.Logger(name, level=INFO)
    instance.addFilter(FilePathFilter())

    # Always persist to the rotating file — so a crash on a normal run is still captured — even
    # though terminal output stays gated by `--logs`.
    file_handler = _file_handler()
    if file_handler is not None:
        instance.addHandler(file_handler)

    if enabled:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(FORMAT))
        instance.addHandler(stream_handler)

    # The logger now always runs (the file handler needs it); `--logs` only controls the terminal.
    # If the file handler couldn't be created and `--logs` is off, silence it to match the old
    # behaviour rather than falling through to logging's last-resort stderr handler.
    instance.disabled = file_handler is None and not enabled

    return instance
