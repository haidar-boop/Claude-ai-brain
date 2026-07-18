"""Notes service: markdown notes with wiki-links, tags, and version history.

Responsibilities kept here (and out of the UI):
- CRUD over notes, returning frozen :class:`NoteDTO` snapshots.
- Every content-changing save first snapshots the previous state into
  ``note_versions``, so history is automatic and the editor never has to
  remember to record it.
- ``[[wiki links]]`` in a note body are parsed and resolved to the ids of
  notes with matching titles, powering backlinks and a knowledge graph.
- Tags are managed as a set of names; the service creates tags on demand and
  keeps the many-to-many link in sync.

Markdown is stored as raw text -- rendering to HTML is a presentation
concern handled in the UI layer, so the service stays render-agnostic and
equally usable from the CLI or REST API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import Note, NoteVersion, Tag

__all__ = ["NoteDTO", "NoteVersionDTO", "NotesService", "extract_wiki_links"]

_logger = get_logger("services.notes")

# Matches [[Target]] and [[Target|display text]]; captures the target title.
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def extract_wiki_links(body: str) -> list[str]:
    """Return the distinct target titles referenced by ``[[wiki links]]``.

    Order is preserved (first mention wins) and whitespace is trimmed, so
    ``[[ Project Ideas ]]`` and ``[[Project Ideas]]`` resolve to the same
    target. Duplicates are removed so a note linking the same target twice
    yields one backlink, not two.
    """
    seen: dict[str, None] = {}
    for match in _WIKI_LINK_RE.finditer(body):
        title = match.group(1).strip()
        if title:
            seen.setdefault(title, None)
    return list(seen)


@dataclass(frozen=True, slots=True)
class NoteVersionDTO:
    """An immutable snapshot of a note at a past point in time."""

    id: int
    title: str
    body: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NoteDTO:
    """A detached, read-only view of a note returned to callers."""

    id: int
    title: str
    body: str
    tags: tuple[str, ...]
    links: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    resolved_link_ids: dict[str, int] = field(default_factory=dict)


class NotesService:
    """Create, read, update, and search markdown notes."""

    def __init__(self, database: Database, events: EventBus | None = None) -> None:
        self._db = database
        self._events = events or EventBus()

    def create(self, title: str, body: str = "", tags: list[str] | None = None) -> NoteDTO:
        """Create a new note, returning its snapshot.

        A blank title is rejected -- an untitled note is almost always a bug
        in the caller (an empty form submit) rather than an intent, and a
        title is what wiki-links resolve against.
        """
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("note title must not be empty")
        with self._db.session() as session:
            note = Note(title=clean_title, body=body)
            self._sync_tags(session, note, tags or [])
            session.add(note)
            session.flush()
            dto = self._to_dto(session, note)
        self._events.publish("note.created", note_id=dto.id, title=dto.title)
        _logger.info("created note %d", dto.id)
        return dto

    def get(self, note_id: int) -> NoteDTO:
        """Return the note with *note_id*, or raise :class:`NotFoundError`."""
        with self._db.session() as session:
            note = session.get(Note, note_id)
            if note is None:
                raise NotFoundError("note", note_id)
            return self._to_dto(session, note)

    def update(
        self,
        note_id: int,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
    ) -> NoteDTO:
        """Update fields of a note, snapshotting the previous content first.

        Only the arguments you pass are changed (``None`` means "leave as
        is"). A version is recorded whenever the title or body actually
        changes, so pure tag edits don't clutter history.
        """
        with self._db.session() as session:
            note = session.get(Note, note_id)
            if note is None:
                raise NotFoundError("note", note_id)

            content_changed = (title is not None and title.strip() != note.title) or (
                body is not None and body != note.body
            )
            if content_changed:
                session.add(NoteVersion(note_id=note.id, title=note.title, body=note.body))

            if title is not None:
                clean_title = title.strip()
                if not clean_title:
                    raise ValidationError("note title must not be empty")
                note.title = clean_title
            if body is not None:
                note.body = body
            if tags is not None:
                self._sync_tags(session, note, tags)

            session.flush()
            dto = self._to_dto(session, note)
        self._events.publish("note.updated", note_id=dto.id, title=dto.title)
        return dto

    def delete(self, note_id: int) -> None:
        """Delete a note and its version history (cascade)."""
        with self._db.session() as session:
            note = session.get(Note, note_id)
            if note is None:
                raise NotFoundError("note", note_id)
            session.delete(note)
        self._events.publish("note.deleted", note_id=note_id)
        _logger.info("deleted note %d", note_id)

    def list_notes(self, *, tag: str | None = None, limit: int | None = None) -> list[NoteDTO]:
        """List notes newest-first, optionally filtered to a single tag."""
        with self._db.session() as session:
            stmt = select(Note).order_by(Note.updated_at.desc())
            if tag is not None:
                stmt = stmt.join(Note.tags).where(Tag.name == tag.strip().lower())
            if limit is not None:
                stmt = stmt.limit(limit)
            return [self._to_dto(session, note) for note in session.scalars(stmt)]

    def search(self, query: str, *, limit: int = 50) -> list[NoteDTO]:
        """Case-insensitive substring search over note titles and bodies."""
        needle = query.strip()
        if not needle:
            return []
        pattern = f"%{needle}%"
        with self._db.session() as session:
            stmt = (
                select(Note)
                .where(Note.title.ilike(pattern) | Note.body.ilike(pattern))
                .order_by(Note.updated_at.desc())
                .limit(limit)
            )
            return [self._to_dto(session, note) for note in session.scalars(stmt)]

    def history(self, note_id: int) -> list[NoteVersionDTO]:
        """Return the note's saved versions, newest first."""
        with self._db.session() as session:
            note = session.get(Note, note_id)
            if note is None:
                raise NotFoundError("note", note_id)
            return [
                NoteVersionDTO(id=v.id, title=v.title, body=v.body, created_at=v.created_at)
                for v in note.versions
            ]

    def restore_version(self, note_id: int, version_id: int) -> NoteDTO:
        """Restore a past version's content as a new current save.

        The current content is itself snapshotted first, so restoring is
        non-destructive and can be undone by restoring again.
        """
        with self._db.session() as session:
            version = session.get(NoteVersion, version_id)
            if version is None or version.note_id != note_id:
                raise NotFoundError("note version", version_id)
        return self.update(note_id, title=version.title, body=version.body)

    def backlinks(self, note_id: int) -> list[NoteDTO]:
        """Return notes whose body links to *note_id*'s title via ``[[...]]``."""
        target = self.get(note_id)
        results: list[NoteDTO] = []
        for candidate in self.list_notes():
            if candidate.id == note_id:
                continue
            if any(link.lower() == target.title.lower() for link in candidate.links):
                results.append(candidate)
        return results

    def _sync_tags(self, session: Session, note: Note, tag_names: list[str]) -> None:
        """Set *note*'s tags to exactly *tag_names*, creating tags as needed."""
        normalized = list(dict.fromkeys(n.strip().lower() for n in tag_names if n.strip()))
        tags: list[Tag] = []
        for name in normalized:
            existing = session.scalar(select(Tag).where(Tag.name == name))
            tags.append(existing if existing is not None else Tag(name=name))
        note.tags = tags

    def _to_dto(self, session: Session, note: Note) -> NoteDTO:
        links = extract_wiki_links(note.body)
        resolved: dict[str, int] = {}
        for title in links:
            match = session.scalar(select(Note.id).where(Note.title == title))
            if match is not None:
                resolved[title] = match
        return NoteDTO(
            id=note.id,
            title=note.title,
            body=note.body,
            tags=tuple(sorted(tag.name for tag in note.tags)),
            links=tuple(links),
            created_at=note.created_at,
            updated_at=note.updated_at,
            version_count=len(note.versions),
            resolved_link_ids=resolved,
        )
