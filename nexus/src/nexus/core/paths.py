"""Filesystem layout for a Nexus data directory.

All persistent state lives under one base directory so backup, export, and
uninstall are each "one directory" operations. The default location follows
platform conventions; everything accepts an explicit override so tests (and
portable installs) can point Nexus at any directory.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["AppPaths", "default_data_dir"]

_APP_DIR_NAME = "nexus"


def default_data_dir() -> Path:
    """Return the platform-conventional data directory for Nexus.

    Windows uses ``%APPDATA%``, macOS uses ``~/Library/Application Support``,
    and everything else follows the XDG base-directory spec
    (``$XDG_DATA_HOME`` or ``~/.local/share``).
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / _APP_DIR_NAME


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved locations of everything Nexus persists."""

    base: Path

    @property
    def database(self) -> Path:
        return self.base / "nexus.db"

    @property
    def backups(self) -> Path:
        return self.base / "backups"

    @property
    def logs(self) -> Path:
        return self.base / "logs"

    @property
    def attachments(self) -> Path:
        return self.base / "attachments"

    @property
    def exports(self) -> Path:
        return self.base / "exports"

    @property
    def encryption_key(self) -> Path:
        return self.base / "nexus.key"

    @classmethod
    def create(cls, base: Path | str | None = None) -> AppPaths:
        """Build an :class:`AppPaths` and ensure every directory exists.

        The key file's *parent* is created here; the key itself is created
        lazily (and with restrictive permissions) by the crypto layer, so
        merely constructing paths never touches secret material.
        """
        resolved = Path(base) if base is not None else default_data_dir()
        paths = cls(base=resolved)
        for directory in (paths.base, paths.backups, paths.logs, paths.attachments, paths.exports):
            directory.mkdir(parents=True, exist_ok=True)
        return paths
