"""Tests for nexus.db.backup."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from nexus.db.backup import BackupManager


def _make_db(path: Path, marker: str = "hello") -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    connection.execute("DELETE FROM t")
    connection.execute("INSERT INTO t VALUES (?)", (marker,))
    connection.commit()
    connection.close()


def test_backup_missing_database_returns_none(tmp_path: Path) -> None:
    manager = BackupManager(tmp_path / "nope.db", tmp_path / "backups")
    assert manager.create() is None


def test_backup_creates_readable_copy(tmp_path: Path) -> None:
    db_path = tmp_path / "nexus.db"
    _make_db(db_path, "backed-up")
    manager = BackupManager(db_path, tmp_path / "backups")
    backup = manager.create()
    assert backup is not None and backup.exists()
    connection = sqlite3.connect(backup)
    value = connection.execute("SELECT v FROM t").fetchone()[0]
    connection.close()
    assert value == "backed-up"


def test_rotation_keeps_only_max_backups(tmp_path: Path) -> None:
    db_path = tmp_path / "nexus.db"
    _make_db(db_path)
    manager = BackupManager(db_path, tmp_path / "backups", max_backups=3)
    for i in range(5):
        manager.create(timestamp=datetime(2024, 1, 1, 12, 0, i))
    assert len(manager.list_backups()) == 3


def test_same_second_backups_do_not_clobber(tmp_path: Path) -> None:
    db_path = tmp_path / "nexus.db"
    _make_db(db_path)
    manager = BackupManager(db_path, tmp_path / "backups", max_backups=10)
    stamp = datetime(2024, 1, 1, 12, 0, 0)
    a = manager.create(timestamp=stamp)
    b = manager.create(timestamp=stamp)
    assert a is not None and b is not None and a != b


def test_restore_overwrites_live_database(tmp_path: Path) -> None:
    db_path = tmp_path / "nexus.db"
    _make_db(db_path, "original")
    manager = BackupManager(db_path, tmp_path / "backups")
    backup = manager.create()
    assert backup is not None
    _make_db(db_path, "changed")  # overwrite the live db
    manager.restore(backup)
    connection = sqlite3.connect(db_path)
    value = connection.execute("SELECT v FROM t").fetchone()[0]
    connection.close()
    assert value == "original"


def test_max_backups_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_backups"):
        BackupManager(tmp_path / "x.db", tmp_path / "b", max_backups=0)
