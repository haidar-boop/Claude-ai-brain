"""Tests for nexus.core.paths and nexus.core.logging."""

from __future__ import annotations

import logging
from pathlib import Path

from nexus.core.config import LoggingConfig
from nexus.core.logging import _reset_for_tests, configure, get_logger
from nexus.core.paths import AppPaths


def test_app_paths_create_makes_directories(tmp_path: Path) -> None:
    paths = AppPaths.create(tmp_path / "data")
    assert paths.base.is_dir()
    assert paths.backups.is_dir()
    assert paths.logs.is_dir()
    assert paths.attachments.is_dir()
    assert paths.exports.is_dir()
    # The database and key files are not created merely by resolving paths.
    assert not paths.database.exists()
    assert not paths.encryption_key.exists()


def test_app_paths_are_under_base(tmp_path: Path) -> None:
    paths = AppPaths.create(tmp_path / "data")
    assert paths.database.parent == paths.base
    assert paths.encryption_key.parent == paths.base


def test_get_logger_namespaces_under_nexus() -> None:
    assert get_logger("database").name == "nexus.database"
    assert get_logger("nexus.already").name == "nexus.already"


def test_configure_is_idempotent(tmp_path: Path) -> None:
    _reset_for_tests()
    try:
        configure(LoggingConfig(level="DEBUG", to_file=True), log_dir=tmp_path)
        logger = logging.getLogger("nexus")
        count_after_first = len(logger.handlers)
        configure(LoggingConfig(level="INFO"), log_dir=tmp_path)
        assert len(logger.handlers) == count_after_first  # no duplicate handlers
        assert logger.level == logging.DEBUG  # first call wins
    finally:
        _reset_for_tests()


def test_configure_writes_log_file(tmp_path: Path) -> None:
    _reset_for_tests()
    try:
        configure(LoggingConfig(level="INFO", to_file=True), log_dir=tmp_path)
        get_logger("test").info("hello nexus")
        for handler in logging.getLogger("nexus").handlers:
            handler.flush()
        assert (tmp_path / "nexus.log").exists()
        assert "hello nexus" in (tmp_path / "nexus.log").read_text(encoding="utf-8")
    finally:
        _reset_for_tests()
