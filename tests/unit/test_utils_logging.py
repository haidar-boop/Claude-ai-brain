"""Tests for aiforge.utils.logging."""

from __future__ import annotations

import json
import logging as stdlib_logging

import pytest

from aiforge.utils import logging as aiforge_logging


def test_get_logger_returns_named_logger() -> None:
    logger = aiforge_logging.get_logger("aiforge.tests.example")
    assert logger.name == "aiforge.tests.example"
    assert isinstance(logger, stdlib_logging.Logger)


def test_get_logger_configures_root_handler_once(monkeypatch: pytest.MonkeyPatch) -> None:
    root = stdlib_logging.getLogger("aiforge")
    monkeypatch.setattr(aiforge_logging, "_CONFIGURED", False)
    monkeypatch.setattr(root, "handlers", [])
    aiforge_logging.get_logger("aiforge.tests.a")
    aiforge_logging.get_logger("aiforge.tests.b")
    assert len(root.handlers) == 1


def test_redact_masks_known_secret_keys() -> None:
    data = {"api_key": "sk-secret", "user": "alice", "Authorization": "Bearer xyz"}
    result = aiforge_logging.redact(data)
    assert result["api_key"] == "***REDACTED***"
    assert result["Authorization"] == "***REDACTED***"
    assert result["user"] == "alice"


def test_redact_does_not_mutate_input() -> None:
    data = {"token": "abc"}
    aiforge_logging.redact(data)
    assert data["token"] == "abc"


def test_structured_formatter_emits_valid_json() -> None:
    formatter = aiforge_logging._StructuredFormatter()
    record = stdlib_logging.LogRecord(
        name="aiforge.tests",
        level=stdlib_logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload == {"level": "INFO", "logger": "aiforge.tests", "message": "hello world"}
