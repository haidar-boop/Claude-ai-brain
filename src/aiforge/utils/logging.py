"""Structured (JSON-lines) logging setup and secret-redaction helpers."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Any

__all__ = ["configure", "get_logger", "redact"]

_CONFIGURED = False
_CONFIGURE_LOCK = threading.Lock()
_REDACT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "x-api-key",
        "authorization",
        "token",
        "secret",
        "password",
        "access_token",
    }
)


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(level: str | int | None = None) -> None:
    """Configure the ``aiforge`` logger tree once; safe to call repeatedly.

    Thread-safe: the double-checked lock prevents concurrent first callers
    from each attaching their own handler (which would duplicate every
    subsequent log record).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    with _CONFIGURE_LOCK:
        if _CONFIGURED:
            return
        resolved_level = (
            level if level is not None else os.environ.get("AIFORGE_LOG_LEVEL", "WARNING")
        )
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(_StructuredFormatter())
        root = logging.getLogger("aiforge")
        root.addHandler(handler)
        root.setLevel(resolved_level)
        root.propagate = False
        _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger, configuring the aiforge logging tree on first use."""
    configure()
    return logging.getLogger(name)


def redact(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *data* with sensitive-looking keys masked."""
    return {
        key: ("***REDACTED***" if key.lower() in _REDACT_KEYS else value)
        for key, value in data.items()
    }
