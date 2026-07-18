"""SQLAlchemy 2.0 ORM models for every Nexus domain.

Uses the typed ``Mapped[...]`` / ``mapped_column`` style so mypy checks
column access, and a single declarative ``Base`` so one ``create_all`` (or
the migration runner) builds the whole schema. Models are deliberately thin
-- behaviour lives in the service layer -- but they carry the relationships,
constraints, and indexes that keep the data correct and queries fast.

The ``EncryptedString`` column type transparently encrypts on write and
decrypts on read using the app's :class:`~nexus.db.crypto.FieldCipher`, so a
sensitive column is declared once and every read/write is protected without
the service layer thinking about it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from nexus.db.crypto import FieldCipher

__all__ = [
    "Attachment",
    "Base",
    "ChatMessage",
    "ChatSession",
    "EncryptedString",
    "FileEntry",
    "Note",
    "NoteTagLink",
    "NoteVersion",
    "Project",
    "Setting",
    "Tag",
    "Task",
    "UtcDateTime",
    "VectorRecord",
    "WorkflowRule",
    "all_models",
    "set_cipher",
]

# A process-wide cipher, injected once at startup by the Database layer.
# It's a module global (not a column argument) because SQLAlchemy type
# decorators are instantiated at class-definition time, long before an app
# and its key file exist.
_cipher: FieldCipher | None = None


def set_cipher(cipher: FieldCipher | None) -> None:
    """Install the process-wide field cipher used by :class:`EncryptedString`."""
    global _cipher
    _cipher = cipher


class EncryptedString(TypeDecorator[str]):
    """A ``String`` column encrypted at rest via the app's field cipher.

    Falls back to storing plaintext only if no cipher has been installed
    (which the Database layer only allows when encryption is disabled in
    config); in the normal configured path a cipher is always present.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return _cipher.encrypt(value) if _cipher is not None else value

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return _cipher.decrypt(value) if _cipher is not None else value


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class UtcDateTime(TypeDecorator[dt.datetime]):
    """A timezone-aware datetime column that always round-trips as UTC.

    SQLite has no timezone-aware datetime type: ``DateTime(timezone=True)``
    silently reads values back *naive*, which then blows up the moment they
    are compared with an aware datetime elsewhere in the app. This decorator
    fixes that at the boundary -- every value is stored as naive-UTC and read
    back as aware-UTC, so the entire application can assume "every datetime
    from the database is aware and in UTC" and never mix naive with aware.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect: object) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # A naive value is taken to already be UTC (that's the app's
            # convention); an aware value is converted to UTC first.
            return value
        return value.astimezone(dt.UTC).replace(tzinfo=None)

    def process_result_value(
        self, value: dt.datetime | None, dialect: object
    ) -> dt.datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=dt.UTC)


class Base(DeclarativeBase):
    """Declarative base carrying shared type conventions."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dt.datetime: UtcDateTime,
    }


class TimestampMixin:
    """Adds created/updated timestamps maintained by the database."""

    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )


class Tag(Base):
    """A label attachable to notes (and reusable across the workspace)."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    notes: Mapped[list[Note]] = relationship(secondary="note_tag_link", back_populates="tags")


class Note(Base, TimestampMixin):
    """A markdown note with tags, wiki-links, and version history."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    body: Mapped[str] = mapped_column(Text, default="")

    tags: Mapped[list[Tag]] = relationship(secondary="note_tag_link", back_populates="notes")
    versions: Mapped[list[NoteVersion]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="NoteVersion.created_at.desc()",
    )


class NoteVersion(Base):
    """An immutable historical snapshot of a note's title and body."""

    __tablename__ = "note_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, server_default=func.now())

    note: Mapped[Note] = relationship(back_populates="versions")


class NoteTagLink(Base):
    """Association row linking a note to a tag (explicit for a clean m2m)."""

    __tablename__ = "note_tag_link"

    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Project(Base, TimestampMixin):
    """A container for tasks (a board / list)."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")

    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Task(Base, TimestampMixin):
    """A task within a project, positioned on a kanban board.

    ``status`` is a kanban column ("todo"/"doing"/"done" by default, but any
    string a board defines); ``position`` orders tasks within a column;
    ``due_at`` powers the calendar view; ``recurrence`` (an interval like
    "daily"/"weekly"/"P3D") drives recurring-task generation in the service.
    """

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="todo")
    position: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[dt.datetime | None] = mapped_column(default=None, index=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    recurrence: Mapped[str | None] = mapped_column(String(32), default=None)

    project: Mapped[Project] = relationship(back_populates="tasks")


class FileEntry(Base, TimestampMixin):
    """An indexed file on disk, with extracted text for full-text search."""

    __tablename__ = "file_entries"
    __table_args__ = (
        UniqueConstraint("path", name="uq_file_entries_path"),
        Index("ix_file_entries_hash_size", "content_hash", "size_bytes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    extension: Mapped[str] = mapped_column(String(32), default="", index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    text_content: Mapped[str] = mapped_column(Text, default="")
    indexed_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)


class Attachment(Base, TimestampMixin):
    """A file attached to a note or task."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1024))
    note_id: Mapped[int | None] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), default=None, index=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), default=None, index=True
    )


class ChatSession(Base, TimestampMixin):
    """A conversation with the AI assistant."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    provider: Mapped[str] = mapped_column(String(64), default="fake")
    model: Mapped[str | None] = mapped_column(String(128), default=None)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """A single message in a chat session (role = user/assistant/system)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class VectorRecord(Base):
    """An embedding vector for a piece of content, for semantic file search.

    The vector is stored as raw little-endian float32 bytes (compact and
    dependency-free to read back with numpy). ``source_type``/``source_id``
    identify what was embedded (e.g. a file entry) so results can be
    resolved back to real objects.
    """

    __tablename__ = "vector_records"
    __table_args__ = (Index("ix_vector_source", "source_type", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[int] = mapped_column(Integer)
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column()
    snippet: Mapped[str] = mapped_column(Text, default="")


class WorkflowRule(Base, TimestampMixin):
    """A stored automation rule: a trigger plus JSON conditions and actions."""

    __tablename__ = "workflow_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    trigger: Mapped[str] = mapped_column(String(64))
    conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    actions_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(default=True)


class Setting(Base):
    """A persisted key/value setting; the value may be encrypted at rest.

    Non-sensitive UI state (last layout, window geometry) and sensitive
    values (integration tokens) share this table; sensitive ones are written
    to :attr:`secret_value`, which uses the encrypted column type.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, default=None)
    secret_value: Mapped[str | None] = mapped_column(EncryptedString, default=None)


def all_models() -> tuple[type[Any], ...]:
    """Return every mapped model class (handy for tests and introspection)."""
    return (
        Tag,
        Note,
        NoteVersion,
        NoteTagLink,
        Project,
        Task,
        FileEntry,
        Attachment,
        ChatSession,
        ChatMessage,
        VectorRecord,
        WorkflowRule,
        Setting,
    )
