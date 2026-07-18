"""Tests for nexus.db.database, models, and migrations."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select

from nexus.core.config import DatabaseConfig
from nexus.db.crypto import FieldCipher
from nexus.db.database import Database
from nexus.db.migrations import MIGRATIONS, current_version, run_migrations
from nexus.db.models import Note, Project, Setting, Tag, Task, set_cipher


def _fresh_db(tmp_path: Path, *, encrypt: bool = False) -> Database:
    cipher = FieldCipher(Fernet.generate_key()) if encrypt else None
    return (
        Database.open(
            tmp_path / "nexus.db",
            config=DatabaseConfig(backup_on_start=False, encrypt_sensitive=encrypt),
            key_path=tmp_path / "nexus.key",
            backup_dir=tmp_path / "backups",
        )
        if encrypt is False
        else Database(
            f"sqlite:///{tmp_path / 'nexus.db'}",
            config=DatabaseConfig(backup_on_start=False, encrypt_sensitive=True),
            cipher=cipher,
        )
    )


def test_migrations_bring_db_to_current_version(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    try:
        expected = max(m.version for m in MIGRATIONS)
        assert current_version(db.engine) == expected
    finally:
        db.dispose()


def test_running_migrations_twice_is_a_noop(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    try:
        first = current_version(db.engine)
        again = run_migrations(db.engine)
        assert again == first
    finally:
        db.dispose()


def test_session_commit_and_query(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    try:
        with db.session() as session:
            session.add(Note(title="First note", body="hello"))
        with db.session() as session:
            note = session.scalar(select(Note).where(Note.title == "First note"))
            assert note is not None
            assert note.body == "hello"
            assert note.created_at is not None
    finally:
        db.dispose()


def test_session_rolls_back_on_error(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    try:
        try:
            with db.session() as session:
                session.add(Note(title="doomed", body="x"))
                session.flush()
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        with db.session() as session:
            assert session.scalar(select(Note).where(Note.title == "doomed")) is None
    finally:
        db.dispose()


def test_foreign_key_cascade_delete(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    try:
        with db.session() as session:
            project = Project(name="Work")
            project.tasks.append(Task(title="Do a thing"))
            session.add(project)
        with db.session() as session:
            project = session.scalar(select(Project).where(Project.name == "Work"))
            assert project is not None
            session.delete(project)
        with db.session() as session:
            # The cascade requires PRAGMA foreign_keys=ON, which the engine sets.
            assert session.scalar(select(Task)) is None
    finally:
        db.dispose()


def test_tags_many_to_many(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    try:
        with db.session() as session:
            tag = Tag(name="idea")
            note = Note(title="tagged", body="")
            note.tags.append(tag)
            session.add(note)
        with db.session() as session:
            note = session.scalar(select(Note).where(Note.title == "tagged"))
            assert note is not None
            assert [t.name for t in note.tags] == ["idea"]
    finally:
        db.dispose()


def test_encrypted_setting_is_ciphertext_on_disk(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path, encrypt=True)
    try:
        with db.session() as session:
            session.add(Setting(key="api_token", secret_value="sk-super-secret"))
        # Read back through the ORM: decrypted transparently.
        with db.session() as session:
            setting = session.get(Setting, "api_token")
            assert setting is not None
            assert setting.secret_value == "sk-super-secret"
        # Read the raw stored bytes: must NOT contain the plaintext.
        with db.engine.connect() as connection:
            from sqlalchemy import text

            raw = connection.execute(
                text("SELECT secret_value FROM settings WHERE key = 'api_token'")
            ).scalar_one()
        assert "sk-super-secret" not in raw
    finally:
        db.dispose()
        set_cipher(None)


def test_in_memory_database_works() -> None:
    db = Database.in_memory()
    try:
        with db.session() as session:
            session.add(Project(name="mem"))
        with db.session() as session:
            assert session.scalar(select(Project).where(Project.name == "mem")) is not None
    finally:
        db.dispose()
