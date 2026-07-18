"""Structured (JSON-lines) logging setup and secret-redaction helpers."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import warnings
from typing import Any

__all__ = ["configure", "get_logger", "redact"]

_CONFIGURED = False
_CONFIGURE_LOCK = threading.Lock()
# Substring markers: any key containing one is masked, catching compound
# names like "anthropic_api_key" or "client_secret" -- exact-name matching
# leaked exactly those.
_REDACT_SUBSTRINGS = ("api_key", "api-key", "apikey", "authorization", "secret", "password")
# "token" needs word-boundary treatment: "auth_token"/"access_token" are
# secrets, but "max_tokens"/"input_tokens" are counters that must NOT be
# masked, so match exact "token" or a "_token" suffix only.
_REDACT_EXACT = frozenset({"token"})
_REDACT_SUFFIXES = ("_token",)
_VALID_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"})


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
        resolved_level = _resolve_level(
            level if level is not None else os.environ.get("AIFORGE_LOG_LEVEL", "WARNING")
        )
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(_StructuredFormatter())
        root = logging.getLogger("aiforge")
        root.addHandler(handler)
        root.setLevel(resolved_level)
        root.propagate = False
        _CONFIGURED = True


def _resolve_level(level: str | int) -> str | int:
    """Normalize a level value, falling back to WARNING for invalid strings.

    ``Logger.setLevel`` raises for anything but uppercase registered names --
    and ``configure()`` runs at import time via module-level ``get_logger``
    calls, so ``AIFORGE_LOG_LEVEL=debug`` (a natural spelling) must degrade
    gracefully instead of making the whole library unimportable.
    """
    if isinstance(level, int):
        return level
    normalized = level.strip().upper()
    if normalized in _VALID_LEVELS:
        return normalized
    warnings.warn(
        f"invalid AIFORGE_LOG_LEVEL {level!r}; falling back to WARNING",
        stacklevel=3,
    )
    return "WARNING"


def get_logger(name: str) -> logging.Logger:
    """Return a logger, configuring the aiforge logging tree on first use."""
    configure()
    return logging.getLogger(name)


def redact(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *data* with sensitive-looking keys masked."""
    return {
        key: ("***REDACTED***" if _is_sensitive_key(key) else value) for key, value in data.items()
    }


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _REDACT_EXACT or lowered.endswith(_REDACT_SUFFIXES):
        return True
    return any(marker in lowered for marker in _REDACT_SUBSTRINGS)
