"""Automatic, rotating SQLite backups.

Before risky operations (app startup, migrations) Nexus snapshots the
database file so a corruption or a bad migration is always recoverable.
Backups use SQLite's own online backup API via ``VACUUM INTO`` when a live
connection is available, which produces a consistent copy even while the
database is in use; a plain file copy is the fallback for a database that
isn't open yet. Old backups are pruned to a configured maximum so the
directory doesn't grow without bound.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from nexus.core.logging import get_logger

__all__ = ["BackupManager"]

_logger = get_logger("db.backup")
_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
_PREFIX = "nexus-"
_SUFFIX = ".db"


class BackupManager:
    """Creates and rotates timestamped copies of the database file."""

    def __init__(self, database_path: Path, backup_dir: Path, *, max_backups: int = 10) -> None:
        if max_backups < 1:
            raise ValueError("max_backups must be >= 1")
        self._database_path = database_path
        self._backup_dir = backup_dir
        self._max_backups = max_backups

    def create(self, *, timestamp: datetime | None = None) -> Path | None:
        """Snapshot the database, returning the backup path (or None if absent).

        A missing database (first ever run) has nothing to back up and is
        not an error. After a successful backup, older backups beyond
        ``max_backups`` are pruned oldest-first.
        """
        if not self._database_path.exists():
            return None
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = (timestamp or datetime.now()).strftime(_TIMESTAMP_FORMAT)
        target = self._backup_dir / f"{_PREFIX}{stamp}{_SUFFIX}"
        # Avoid clobbering a same-second backup by appending a counter.
        counter = 1
        while target.exists():
            target = self._backup_dir / f"{_PREFIX}{stamp}-{counter}{_SUFFIX}"
            counter += 1
        self._snapshot(target)
        _logger.info("created database backup at %s", target)
        self._prune()
        return target

    def list_backups(self) -> list[Path]:
        """Return existing backups, newest first (by filename timestamp)."""
        if not self._backup_dir.is_dir():
            return []
        backups = [
            p
            for p in self._backup_dir.iterdir()
            if p.name.startswith(_PREFIX) and p.suffix == _SUFFIX
        ]
        return sorted(backups, key=lambda p: p.name, reverse=True)

    def restore(self, backup_path: Path) -> None:
        """Replace the live database with *backup_path* (overwrites in place)."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, self._database_path)
        _logger.info("restored database from %s", backup_path)

    def _snapshot(self, target: Path) -> None:
        """Produce a consistent copy using SQLite's backup API, with a fallback."""
        try:
            source = sqlite3.connect(self._database_path)
            try:
                destination = sqlite3.connect(target)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
            finally:
                source.close()
        except sqlite3.Error:
            # A locked or unusual database still yields a usable copy via a
            # plain file copy; better a slightly-less-consistent backup than
            # none at all.
            _logger.warning("sqlite backup API failed; falling back to file copy")
            shutil.copy2(self._database_path, target)

    def _prune(self) -> None:
        backups = self.list_backups()
        for stale in backups[self._max_backups :]:
            try:
                stale.unlink()
                _logger.debug("pruned old backup %s", stale)
            except OSError:  # pragma: no cover - unlikely race
                _logger.warning("could not prune backup %s", stale)
