"""Central logging setup for Nexus.

Provides a single ``configure`` entry point (idempotent, thread-safe) and a
``get_logger`` helper. Logs can be emitted as human-readable lines or as
JSON (one object per line) for machine ingestion, and optionally mirrored to
a rotating file under the app's log directory. Everything hangs off the
``nexus`` logger so third-party library noise stays separate.
"""

from __future__ import annotations

import json
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from nexus.core.config import LoggingConfig

__all__ = ["configure", "get_logger"]

_ROOT = "nexus"
_LOCK = threading.Lock()
_configured = False

_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 5


class _JsonFormatter(logging.Formatter):
    """Render each record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(config: LoggingConfig | None = None, *, log_dir: Path | None = None) -> None:
    """Configure the ``nexus`` logger tree once; later calls are no-ops.

    Safe to call from multiple threads: the first caller wins and the
    double-checked lock prevents duplicate handlers (which would otherwise
    emit every record more than once).
    """
    global _configured
    if _configured:
        return
    with _LOCK:
        if _configured:
            return
        cfg = config or LoggingConfig()
        logger = logging.getLogger(_ROOT)
        logger.setLevel(cfg.level.upper())
        logger.propagate = False
        formatter: logging.Formatter = (
            _JsonFormatter()
            if cfg.json
            else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)
        if cfg.to_file and log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "nexus.log",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``nexus`` namespace.

    Accepts either a bare component name (``"database"``) or a dotted module
    name (``__name__``); the ``nexus.`` prefix is added if not present so all
    records route through the configured handlers.
    """
    if name == _ROOT or name.startswith(f"{_ROOT}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT}.{name}")


def _reset_for_tests() -> None:  # pragma: no cover - test helper
    """Tear down configuration so a test can reconfigure from scratch."""
    global _configured
    with _LOCK:
        logger = logging.getLogger(_ROOT)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        _configured = False
