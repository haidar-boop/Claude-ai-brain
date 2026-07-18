"""Persistence layer: SQLAlchemy 2.0 models, migrations, encryption, backups.

The public surface is intentionally narrow -- callers get a
:class:`~nexus.db.database.Database` (an engine + session factory that has
already run migrations and taken a startup backup) and the ORM models. The
encrypted column type and backup manager are wired in automatically; nothing
outside this package needs to know how encryption keys or backup rotation
work.
"""
