"""Dashboard service: cross-module stats, activity, metrics, and search.

The dashboard is the one place that reads *across* modules, so it depends on
the database directly (for counts and metrics) and on the event bus (for a
live recent-activity feed) rather than on the other services -- which keeps
it from tangling every module together. Unified search runs one query per
content type and merges the results, so "find X" spans notes, tasks, files,
and chat messages at once.

Recent activity is an in-memory ring buffer fed by the event bus: cheap,
requires no schema, and reflects what's happened since the app started
(exactly what a dashboard's "recent activity" panel wants).
"""

from __future__ import annotations

import datetime as dt
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nexus.core.events import Event, EventBus
from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import ChatMessage, ChatSession, FileEntry, Note, Task

__all__ = [
    "ActivityItem",
    "DashboardService",
    "ProductivityMetrics",
    "SearchResult",
    "Stats",
    "StorageUsage",
]

_logger = get_logger("services.dashboard")
_DEFAULT_ACTIVITY_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Stats:
    """Headline counts across every module."""

    notes: int
    tasks: int
    open_tasks: int
    completed_tasks: int
    files: int
    chat_sessions: int


@dataclass(frozen=True, slots=True)
class StorageUsage:
    """Where disk is going."""

    database_bytes: int
    indexed_file_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.database_bytes + self.indexed_file_bytes


@dataclass(frozen=True, slots=True)
class ActivityItem:
    """One entry in the recent-activity feed."""

    topic: str
    at: dt.datetime
    detail: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProductivityMetrics:
    """Task-completion counts bucketed by day, oldest to newest."""

    completed_per_day: dict[str, int]

    @property
    def total_completed(self) -> int:
        return sum(self.completed_per_day.values())


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single unified-search hit from some module."""

    kind: str  # "note" | "task" | "file" | "chat"
    id: int
    title: str
    snippet: str


class DashboardService:
    """Aggregates statistics, activity, metrics, and search across modules."""

    def __init__(
        self,
        database: Database,
        events: EventBus | None = None,
        *,
        activity_limit: int = _DEFAULT_ACTIVITY_LIMIT,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._db = database
        self._events = events or EventBus()
        self._activity: deque[ActivityItem] = deque(maxlen=activity_limit)
        # Injectable clock keeps activity timestamps deterministic in tests.
        self._now: Callable[[], dt.datetime] = clock or _utcnow
        self._events.subscribe("*", self._record_activity)

    # -- statistics -------------------------------------------------------

    def stats(self) -> Stats:
        """Return headline counts for every module."""
        with self._db.session() as session:
            completed = session.scalar(
                select(func.count(Task.id)).where(Task.completed_at.is_not(None))
            )
            total_tasks = session.scalar(select(func.count(Task.id)))
            return Stats(
                notes=_count(session, Note),
                tasks=int(total_tasks or 0),
                open_tasks=int((total_tasks or 0) - (completed or 0)),
                completed_tasks=int(completed or 0),
                files=_count(session, FileEntry),
                chat_sessions=_count(session, ChatSession),
            )

    def storage_usage(self) -> StorageUsage:
        """Return database and indexed-file byte totals."""
        with self._db.session() as session:
            file_bytes = session.scalar(select(func.coalesce(func.sum(FileEntry.size_bytes), 0)))
        return StorageUsage(
            database_bytes=self._database_file_bytes(),
            indexed_file_bytes=int(file_bytes or 0),
        )

    # -- activity ---------------------------------------------------------

    def recent_activity(self, *, limit: int = 50) -> list[ActivityItem]:
        """Return the most recent activity items, newest first."""
        items = list(self._activity)
        items.reverse()
        return items[:limit]

    # -- productivity -----------------------------------------------------

    def productivity(self, *, days: int = 7, now: dt.datetime | None = None) -> ProductivityMetrics:
        """Tasks completed per day over the last *days* days (inclusive of today).

        Every day in the window appears in the result (with a 0 count if
        nothing was completed), so a UI can render a gap-free bar chart
        without post-processing.
        """
        if days < 1:
            days = 1
        moment = now or self._now()
        start = (moment - dt.timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        buckets = {
            (start + dt.timedelta(days=offset)).date().isoformat(): 0 for offset in range(days)
        }
        with self._db.session() as session:
            rows = session.scalars(
                select(Task.completed_at).where(
                    Task.completed_at.is_not(None), Task.completed_at >= start
                )
            ).all()
        for completed_at in rows:
            if completed_at is None:
                continue
            key = completed_at.date().isoformat()
            if key in buckets:
                buckets[key] += 1
        return ProductivityMetrics(completed_per_day=buckets)

    # -- unified search ---------------------------------------------------

    def search(self, query: str, *, limit_per_kind: int = 10) -> list[SearchResult]:
        """Search notes, tasks, files, and chat messages in one call.

        Each content type contributes up to *limit_per_kind* hits. Results
        are grouped by kind in a stable order (notes, tasks, files, chats) so
        a combined results panel is easy to render and deterministic to test.
        """
        needle = query.strip()
        if not needle:
            return []
        pattern = f"%{needle}%"
        results: list[SearchResult] = []
        with self._db.session() as session:
            for note in session.scalars(
                select(Note)
                .where(Note.title.ilike(pattern) | Note.body.ilike(pattern))
                .order_by(Note.updated_at.desc())
                .limit(limit_per_kind)
            ):
                results.append(
                    SearchResult("note", note.id, note.title, _snippet(note.body, needle))
                )
            for task in session.scalars(
                select(Task)
                .where(Task.title.ilike(pattern) | Task.description.ilike(pattern))
                .limit(limit_per_kind)
            ):
                results.append(
                    SearchResult("task", task.id, task.title, _snippet(task.description, needle))
                )
            for entry in session.scalars(
                select(FileEntry)
                .where(FileEntry.name.ilike(pattern) | FileEntry.text_content.ilike(pattern))
                .limit(limit_per_kind)
            ):
                results.append(
                    SearchResult("file", entry.id, entry.name, _snippet(entry.text_content, needle))
                )
            for message in session.scalars(
                select(ChatMessage)
                .where(ChatMessage.content.ilike(pattern))
                .order_by(ChatMessage.created_at.desc())
                .limit(limit_per_kind)
            ):
                results.append(
                    SearchResult(
                        "chat",
                        message.session_id,
                        "Chat message",
                        _snippet(message.content, needle),
                    )
                )
        return results

    # -- internals --------------------------------------------------------

    def _record_activity(self, event: Event) -> None:
        self._activity.append(
            ActivityItem(topic=event.name, at=self._now(), detail=dict(event.payload))
        )

    def _database_file_bytes(self) -> int:
        url = str(self._db.engine.url)
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            return 0
        path = Path(url[len(prefix) :])
        return path.stat().st_size if path.is_file() else 0


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _snippet(text: str, needle: str, *, width: int = 80) -> str:
    """Return a short excerpt of *text* centered on the first *needle* match."""
    if not text:
        return ""
    lowered = text.lower()
    index = lowered.find(needle.lower())
    if index < 0:
        return text[:width].strip()
    start = max(0, index - width // 2)
    return text[start : start + width].strip()
