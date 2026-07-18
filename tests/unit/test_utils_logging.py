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


def test_redact_masks_compound_secret_keys() -> None:
    # Regression: exact-name matching leaked compound keys -- including this
    # project's own canonical ANTHROPIC_API_KEY.
    data = {
        "anthropic_api_key": "sk-ant-secret",
        "ANTHROPIC_API_KEY": "sk-ant-secret",
        "client_secret": "cs-secret",
        "auth_token": "tok-secret",
        "x-api-key": "xk-secret",
    }
    result = aiforge_logging.redact(data)
    assert all(value == "***REDACTED***" for value in result.values())


def test_redact_leaves_token_count_fields_alone() -> None:
    # "token" substring matching must not mask usage counters.
    data = {"max_tokens": 4096, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    assert aiforge_logging.redact(data) == data


def test_configure_falls_back_to_warning_on_invalid_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: AIFORGE_LOG_LEVEL=debug (lowercase) crashed configure() --
    # at import time, via module-level get_logger calls -- with ValueError.
    monkeypatch.setattr(aiforge_logging, "_CONFIGURED", False)
    root = stdlib_logging.getLogger("aiforge")
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setenv("AIFORGE_LOG_LEVEL", "debug")
    aiforge_logging.configure()
    assert root.level == stdlib_logging.DEBUG  # lowercase normalized, not crashed


def test_configure_warns_and_uses_warning_for_garbage_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aiforge_logging, "_CONFIGURED", False)
    root = stdlib_logging.getLogger("aiforge")
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setenv("AIFORGE_LOG_LEVEL", "chatty")
    with pytest.warns(UserWarning, match="invalid AIFORGE_LOG_LEVEL"):
        aiforge_logging.configure()
    assert root.level == stdlib_logging.WARNING


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
