"""The Database facade: one object that hands out ready-to-use sessions.

Constructing a :class:`Database` wires everything together in the right
order: install the field cipher (so encrypted columns work), enable SQLite
pragmas (foreign-key enforcement, WAL journaling for better concurrency),
take a startup backup, and run pending migrations. Callers then use
``with db.session() as session:`` and get a transactional unit of work that
commits on success and rolls back on error.

Everything is injectable for tests: an in-memory database with encryption
off and backups skipped spins up in microseconds.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from types import TracebackType
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from nexus.core.config import DatabaseConfig
from nexus.core.logging import get_logger
from nexus.db.backup import BackupManager
from nexus.db.crypto import FieldCipher
from nexus.db.migrations import run_migrations
from nexus.db.models import set_cipher

__all__ = ["Database"]

_logger = get_logger("db")


def _enable_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    """Turn on foreign-key enforcement and WAL mode for every connection.

    SQLite disables foreign keys by default (per-connection), so without
    this the ``ondelete="CASCADE"`` rules on the models would be silently
    ignored. WAL journaling lets readers and a writer coexist, which matters
    once the UI and a background worker touch the database at once.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL is a no-op (and silently ignored) for pure in-memory databases;
    # it only matters for the on-disk workspace database, so a failure here
    # must never block opening the database.
    with suppress(Exception):
        cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


class Database:
    """Owns the engine and session factory for a Nexus workspace."""

    def __init__(
        self,
        url: str,
        *,
        config: DatabaseConfig | None = None,
        cipher: FieldCipher | None = None,
        backup_manager: BackupManager | None = None,
        echo: bool = False,
        connect_args: dict[str, Any] | None = None,
        poolclass: type[Any] | None = None,
    ) -> None:
        self._config = config or DatabaseConfig()
        engine_kwargs: dict[str, Any] = {"echo": echo, "future": True}
        if connect_args is not None:
            engine_kwargs["connect_args"] = connect_args
        if poolclass is not None:
            engine_kwargs["poolclass"] = poolclass
        self._engine: Engine = create_engine(url, **engine_kwargs)
        event.listen(self._engine, "connect", _enable_sqlite_pragmas)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

        # The cipher must be installed before any session touches an
        # encrypted column, and before migrations create the schema.
        set_cipher(cipher)

        if backup_manager is not None and self._config.backup_on_start:
            backup_manager.create()

        run_migrations(self._engine)
        _logger.info("database ready at %s", url)

    @classmethod
    def open(
        cls,
        database_path: Path,
        *,
        config: DatabaseConfig,
        key_path: Path,
        backup_dir: Path,
    ) -> Database:
        """Open the on-disk workspace database with encryption and backups.

        This is the normal production entry point. Encryption is enabled per
        ``config.encrypt_sensitive``; when on, the field cipher is loaded
        (generating the key file on first run).
        """
        cipher = FieldCipher.from_key_file(key_path) if config.encrypt_sensitive else None
        backups = BackupManager(database_path, backup_dir, max_backups=config.max_backups)
        return cls(
            f"sqlite:///{database_path}",
            config=config,
            cipher=cipher,
            backup_manager=backups,
            echo=config.echo_sql,
        )

    @classmethod
    def in_memory(cls, *, cipher: FieldCipher | None = None) -> Database:
        """Create an isolated, throwaway in-memory database (used by tests).

        A plain ``sqlite://`` in-memory database vanishes when its connection
        is returned to the pool; :class:`~sqlalchemy.pool.StaticPool` keeps a
        single connection alive for the object's lifetime, so the schema and
        data persist across ``session()`` calls. Each :meth:`in_memory`
        instance is fully isolated from every other.
        """
        return cls(
            "sqlite://",
            config=DatabaseConfig(backup_on_start=False, encrypt_sensitive=cipher is not None),
            cipher=cipher,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a transactional session: commit on success, roll back on error."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Close all pooled connections (call at application shutdown)."""
        self._engine.dispose()

    def __enter__(self) -> Database:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.dispose()
