"""A tiny, dependency-free schema migration runner.

Nexus doesn't pull in Alembic: the schema is small and single-database, so a
lightweight runner keeps the dependency footprint down while still giving
the important guarantees -- migrations run in order, exactly once, inside a
transaction, tracked in a ``schema_migrations`` table.

A migration is a ``(version, description, apply)`` triple where ``apply``
receives a live :class:`~sqlalchemy.engine.Connection`. The baseline
migration (version 1) creates the whole current schema from the ORM
metadata via ``Base.metadata.create_all``; later migrations are appended to
:data:`MIGRATIONS` as the schema evolves and never edited retroactively,
because a released migration has already run on real databases.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text

from nexus.core.errors import MigrationError
from nexus.core.logging import get_logger
from nexus.db.models import Base

__all__ = ["MIGRATIONS", "Migration", "current_version", "run_migrations"]

_logger = get_logger("db.migrations")

ApplyFn = Callable[[Connection], None]


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered, idempotently-tracked schema change."""

    version: int
    description: str
    apply: ApplyFn


def _baseline(connection: Connection) -> None:
    """Create the entire current schema from the ORM metadata."""
    Base.metadata.create_all(connection)


MIGRATIONS: list[Migration] = [
    Migration(1, "create baseline schema", _baseline),
]


def _ensure_version_table(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, "
            "description TEXT NOT NULL, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
    )


def current_version(engine: Engine) -> int:
    """Return the highest applied migration version (0 if none)."""
    with engine.connect() as connection:
        _ensure_version_table(connection)
        result = connection.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations"))
        return int(result.scalar_one())


def run_migrations(engine: Engine, migrations: list[Migration] | None = None) -> int:
    """Apply every pending migration in order; return the resulting version.

    Each migration runs in its own transaction together with the insert into
    ``schema_migrations``, so a failure leaves the database at the last fully
    applied version rather than half-migrated. Applying an up-to-date
    database is a no-op.
    """
    to_run = MIGRATIONS if migrations is None else migrations
    ordered = sorted(to_run, key=lambda m: m.version)
    _validate_sequence(ordered)

    applied = current_version(engine)
    for migration in ordered:
        if migration.version <= applied:
            continue
        _logger.info("applying migration %d: %s", migration.version, migration.description)
        try:
            with engine.begin() as connection:
                _ensure_version_table(connection)
                migration.apply(connection)
                connection.execute(
                    text("INSERT INTO schema_migrations (version, description) VALUES (:v, :d)"),
                    {"v": migration.version, "d": migration.description},
                )
        except Exception as exc:
            raise MigrationError(
                f"migration {migration.version} ({migration.description}) failed: {exc}"
            ) from exc
        applied = migration.version
    return applied


def _validate_sequence(migrations: list[Migration]) -> None:
    versions = [m.version for m in migrations]
    if len(set(versions)) != len(versions):
        raise MigrationError("duplicate migration version detected")
    if versions and versions[0] < 1:
        raise MigrationError("migration versions must start at 1")
