"""Files service: full-text search, duplicate finding, and organization.

This service indexes files on disk into the database so they can be searched
and de-duplicated without re-walking the filesystem each time:

- **Full-text search** uses SQLite's FTS5 index (``file_fts``), kept in sync
  as files are indexed and removed. Queries return ranked matches.
- **Duplicate finding** is a memory-efficient two stage process: group by
  size first (cheap, already in the DB), then hash only the files whose size
  collides -- a unique-sized file is never read. Hashing streams the file in
  chunks so a huge file never loads into memory.
- **Organization** is rule-based and dry-run by default: a rule maps a file
  (by extension or filename glob) to a destination folder, and ``organize``
  reports or performs the moves.
- **Previews** extract lightweight metadata plus a text snippet.

OCR for scanned PDFs and images is a documented extension point rather than
a hard dependency: pass any object implementing :class:`TextExtractor` to
pull text out of formats the default extractor can't read. The default
handles UTF-8 text files and returns ``""`` for binary content, so the
service works out of the box with zero extra dependencies.
"""

from __future__ import annotations

import fnmatch
import hashlib
import mimetypes
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import FileEntry

__all__ = [
    "DuplicateGroup",
    "FileDTO",
    "FilePreview",
    "FilesService",
    "OrganizeRule",
    "PlannedMove",
    "TextExtractor",
]

_logger = get_logger("services.files")
_HASH_CHUNK = 1 << 20  # 1 MiB streaming chunks
_SNIPPET_CHARS = 500


class TextExtractor(Protocol):
    """Pulls searchable text out of a file.

    Implement this to add OCR (e.g. pytesseract over an image/PDF) or format
    specific extraction; the service will index whatever text you return.
    """

    def extract(self, path: Path) -> str:
        """Return searchable text for *path* (``""`` if none)."""
        ...


class PlainTextExtractor:
    """Default extractor: reads UTF-8 text files, ignores binary content."""

    _TEXT_SUFFIXES = frozenset(
        {
            ".txt",
            ".md",
            ".markdown",
            ".rst",
            ".csv",
            ".json",
            ".yaml",
            ".yml",
            ".py",
            ".js",
            ".ts",
            ".html",
            ".css",
            ".log",
            ".ini",
            ".toml",
            ".sh",
            ".xml",
            ".sql",
        }
    )

    def extract(self, path: Path) -> str:
        if path.suffix.lower() not in self._TEXT_SUFFIXES:
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""


@dataclass(frozen=True, slots=True)
class FileDTO:
    """A detached view of an indexed file."""

    id: int
    path: str
    name: str
    extension: str
    size_bytes: int
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """A set of indexed files with identical content (same size and hash)."""

    content_hash: str
    size_bytes: int
    files: tuple[FileDTO, ...]


@dataclass(frozen=True, slots=True)
class FilePreview:
    """Lightweight metadata and a text snippet for a file."""

    path: str
    name: str
    size_bytes: int
    mime_type: str | None
    snippet: str


@dataclass(frozen=True, slots=True)
class OrganizeRule:
    """Route files matching *extensions* or a filename *glob* to *destination*."""

    destination: str
    extensions: tuple[str, ...] = ()
    glob: str | None = None

    def matches(self, path: Path) -> bool:
        if self.extensions and path.suffix.lower().lstrip(".") in {
            e.lower().lstrip(".") for e in self.extensions
        }:
            return True
        return bool(self.glob and fnmatch.fnmatch(path.name, self.glob))


@dataclass(frozen=True, slots=True)
class PlannedMove:
    """A single move the organizer would perform (or performed)."""

    source: str
    destination: str


class FilesService:
    """Index files for search, find duplicates, and organize folders."""

    def __init__(
        self,
        database: Database,
        events: EventBus | None = None,
        *,
        extractor: TextExtractor | None = None,
    ) -> None:
        self._db = database
        self._events = events or EventBus()
        self._extractor: TextExtractor = extractor or PlainTextExtractor()

    # -- indexing ---------------------------------------------------------

    def index_file(self, path: Path | str, *, compute_hash: bool = False) -> FileDTO:
        """Index a single file, extracting its text for full-text search.

        By default the content hash is left unset (it's only needed for
        duplicate detection, which fills it in on demand). Pass
        ``compute_hash=True`` to hash eagerly.
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise ValidationError(f"not a file: {file_path}")
        resolved = str(file_path.resolve())
        size = file_path.stat().st_size
        text_content = self._extractor.extract(file_path)
        digest = _hash_file(file_path) if compute_hash else None

        with self._db.session() as session:
            entry = session.scalar(select(FileEntry).where(FileEntry.path == resolved))
            if entry is None:
                entry = FileEntry(path=resolved)
                session.add(entry)
            entry.name = file_path.name
            entry.extension = file_path.suffix.lower().lstrip(".")
            entry.size_bytes = size
            entry.text_content = text_content
            entry.content_hash = digest
            session.flush()
            self._reindex_fts(session, entry.id, entry.name, text_content)
            dto = _file_dto(entry)
        self._events.publish("file.indexed", file_id=dto.id, path=dto.path)
        return dto

    def index_directory(
        self, directory: Path | str, *, recursive: bool = True, compute_hash: bool = False
    ) -> list[FileDTO]:
        """Index every file under *directory*; returns the indexed files."""
        root = Path(directory)
        if not root.is_dir():
            raise ValidationError(f"not a directory: {root}")
        paths = (p for p in (root.rglob("*") if recursive else root.iterdir()) if p.is_file())
        return [self.index_file(p, compute_hash=compute_hash) for p in paths]

    def remove(self, file_id: int) -> None:
        """Remove a file from the index (does not touch the file on disk)."""
        with self._db.session() as session:
            entry = session.get(FileEntry, file_id)
            if entry is None:
                raise NotFoundError("file", file_id)
            session.delete(entry)
            session.execute(text("DELETE FROM file_fts WHERE rowid = :id"), {"id": file_id})
        self._events.publish("file.removed", file_id=file_id)

    # -- search -----------------------------------------------------------

    def search(self, query: str, *, limit: int = 50) -> list[FileDTO]:
        """Full-text search over indexed file names and contents (FTS5).

        The query is passed to FTS5's MATCH; a plain word or phrase works as
        expected. Results are ranked by relevance (FTS5 ``rank``).
        """
        term = query.strip()
        if not term:
            return []
        with self._db.session() as session:
            rows = session.execute(
                text(
                    "SELECT rowid FROM file_fts WHERE file_fts MATCH :q ORDER BY rank LIMIT :limit"
                ),
                {"q": _fts_query(term), "limit": limit},
            ).all()
            ids = [row[0] for row in rows]
            if not ids:
                return []
            entries = session.scalars(select(FileEntry).where(FileEntry.id.in_(ids))).all()
            by_id = {e.id: e for e in entries}
            return [_file_dto(by_id[i]) for i in ids if i in by_id]

    # -- duplicates -------------------------------------------------------

    def find_duplicates(self) -> list[DuplicateGroup]:
        """Find indexed files with identical content, two-stage (size, hash).

        Stage 1 groups by size using data already in the DB, so only files
        whose size collides with another are considered. Stage 2 hashes just
        those candidates (streaming, filling in any missing hash) and groups
        by hash. A file with a unique size is never opened.
        """
        with self._db.session() as session:
            size_groups = self._colliding_sizes(session)
            groups: list[DuplicateGroup] = []
            for size in size_groups:
                by_hash: dict[str, list[FileEntry]] = {}
                candidates = session.scalars(
                    select(FileEntry).where(FileEntry.size_bytes == size)
                ).all()
                for entry in candidates:
                    digest = entry.content_hash or self._ensure_hash(session, entry)
                    if digest is not None:
                        by_hash.setdefault(digest, []).append(entry)
                for digest, members in by_hash.items():
                    if len(members) > 1:
                        groups.append(
                            DuplicateGroup(
                                content_hash=digest,
                                size_bytes=size,
                                files=tuple(_file_dto(m) for m in members),
                            )
                        )
        return groups

    # -- previews ---------------------------------------------------------

    def preview(self, path: Path | str) -> FilePreview:
        """Return metadata and a text snippet for a file (without indexing)."""
        file_path = Path(path)
        if not file_path.is_file():
            raise ValidationError(f"not a file: {file_path}")
        mime, _ = mimetypes.guess_type(file_path.name)
        snippet = self._extractor.extract(file_path)[:_SNIPPET_CHARS]
        return FilePreview(
            path=str(file_path.resolve()),
            name=file_path.name,
            size_bytes=file_path.stat().st_size,
            mime_type=mime,
            snippet=snippet,
        )

    # -- organization -----------------------------------------------------

    def organize(
        self,
        directory: Path | str,
        rules: Iterable[OrganizeRule],
        *,
        dry_run: bool = True,
    ) -> list[PlannedMove]:
        """Plan (and optionally perform) moving files into rule destinations.

        Dry-run by default so a caller can preview the plan before touching
        anything. The first matching rule wins; a file matching no rule is
        left alone. Destination folders are created as needed, and a name
        collision is resolved by appending a numeric suffix rather than
        overwriting.
        """
        root = Path(directory)
        if not root.is_dir():
            raise ValidationError(f"not a directory: {root}")
        rule_list = list(rules)
        moves: list[PlannedMove] = []
        for path in sorted(p for p in root.iterdir() if p.is_file()):
            rule = next((r for r in rule_list if r.matches(path)), None)
            if rule is None:
                continue
            dest_dir = root / rule.destination
            target = dest_dir / path.name
            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                target = _non_clobbering(target)
                path.rename(target)
            moves.append(PlannedMove(source=str(path), destination=str(target)))
        if not dry_run and moves:
            self._events.publish("files.organized", count=len(moves))
        return moves

    # -- internals --------------------------------------------------------

    def _reindex_fts(self, session: Session, file_id: int, name: str, body: str) -> None:
        session.execute(text("DELETE FROM file_fts WHERE rowid = :id"), {"id": file_id})
        session.execute(
            text("INSERT INTO file_fts (rowid, name, body) VALUES (:id, :name, :body)"),
            {"id": file_id, "name": name, "body": body},
        )

    def _colliding_sizes(self, session: Session) -> list[int]:
        rows = session.execute(
            text(
                "SELECT size_bytes FROM file_entries "
                "GROUP BY size_bytes HAVING COUNT(*) > 1 AND size_bytes > 0"
            )
        ).all()
        return [int(row[0]) for row in rows]

    def _ensure_hash(self, session: Session, entry: FileEntry) -> str | None:
        """Compute and persist *entry*'s content hash, or None if unreadable."""
        path = Path(entry.path)
        if not path.is_file():
            return None
        digest = _hash_file(path)
        entry.content_hash = digest
        session.flush()
        return digest


def _file_dto(entry: FileEntry) -> FileDTO:
    return FileDTO(
        id=entry.id,
        path=entry.path,
        name=entry.name,
        extension=entry.extension,
        size_bytes=entry.size_bytes,
        content_hash=entry.content_hash,
    )


def _hash_file(path: Path) -> str:
    """Return the SHA-256 of *path*, streaming so memory stays constant."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _fts_query(term: str) -> str:
    """Turn user text into a safe FTS5 MATCH expression.

    Wrapping each whitespace-separated token in double quotes makes FTS5
    treat punctuation as literal text rather than query syntax, so a search
    like ``report(final)`` can't raise an FTS5 syntax error.
    """
    tokens = [t.replace('"', "") for t in term.split() if t]
    return " ".join(f'"{token}"' for token in tokens) if tokens else '""'


def _non_clobbering(target: Path) -> Path:
    """Return *target*, or ``name-1.ext``/``name-2.ext`` if it already exists."""
    if not target.exists():
        return target
    counter = 1
    while True:
        candidate = target.with_name(f"{target.stem}-{counter}{target.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
