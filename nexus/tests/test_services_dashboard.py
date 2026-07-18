"""Tests for nexus.services.dashboard."""

from __future__ import annotations

import datetime as dt

import pytest

from nexus.core.config import AIConfig
from nexus.core.events import EventBus
from nexus.db.database import Database
from nexus.services.ai import AIService
from nexus.services.dashboard import DashboardService
from nexus.services.files import FilesService
from nexus.services.notes import NotesService
from nexus.services.tasks import TasksService


@pytest.fixture
def wired() -> tuple[Database, EventBus, DashboardService]:
    db = Database.in_memory()
    bus = EventBus()
    dash = DashboardService(db, bus)
    return db, bus, dash


def test_stats_counts_across_modules(wired: tuple[Database, EventBus, DashboardService]) -> None:
    db, bus, dash = wired
    notes = NotesService(db, bus)
    tasks = TasksService(db, bus)
    notes.create("Note A")
    notes.create("Note B")
    pid = tasks.create_project("P").id
    t1 = tasks.add_task(pid, "open task")
    t2 = tasks.add_task(pid, "done task")
    tasks.complete(t2.id)

    stats = dash.stats()
    assert stats.notes == 2
    assert stats.tasks == 2
    assert stats.open_tasks == 1
    assert stats.completed_tasks == 1
    assert t1.id != t2.id


def test_storage_usage(wired: tuple[Database, EventBus, DashboardService], tmp_path) -> None:
    db, bus, dash = wired
    files = FilesService(db, bus)
    path = tmp_path / "doc.txt"
    path.write_text("some content here", encoding="utf-8")
    files.index_file(path)
    usage = dash.storage_usage()
    assert usage.indexed_file_bytes > 0
    assert usage.total_bytes >= usage.indexed_file_bytes


def test_recent_activity_records_events(
    wired: tuple[Database, EventBus, DashboardService],
) -> None:
    db, bus, dash = wired
    notes = NotesService(db, bus)
    notes.create("X")
    notes.create("Y")
    activity = dash.recent_activity()
    topics = [a.topic for a in activity]
    assert "note.created" in topics
    # newest first
    assert activity[0].at >= activity[-1].at


def test_activity_is_bounded() -> None:
    bus = EventBus()
    dash = DashboardService(Database.in_memory(), bus, activity_limit=5)
    for i in range(10):
        bus.publish("thing.happened", n=i)
    assert len(dash.recent_activity(limit=100)) == 5


def test_productivity_buckets_include_empty_days() -> None:
    db = Database.in_memory()
    bus = EventBus()
    now = dt.datetime(2024, 3, 10, 12, 0, tzinfo=dt.UTC)
    dash = DashboardService(db, bus, clock=lambda: now)
    tasks = TasksService(db, bus)
    pid = tasks.create_project("P").id
    t = tasks.add_task(pid, "done today")
    tasks.complete(t.id, now=now)

    metrics = dash.productivity(days=7, now=now)
    assert len(metrics.completed_per_day) == 7  # every day present
    assert metrics.completed_per_day["2024-03-10"] == 1
    assert metrics.total_completed == 1


def test_unified_search_spans_modules(
    wired: tuple[Database, EventBus, DashboardService], tmp_path
) -> None:
    db, bus, dash = wired
    notes = NotesService(db, bus)
    tasks = TasksService(db, bus)
    files = FilesService(db, bus)
    ai = AIService(db, AIConfig(default_provider="fake"), bus)

    notes.create("Budget plan", "the annual budget notes")
    pid = tasks.create_project("Finance").id
    tasks.add_task(pid, "Review budget", description="quarterly budget review")
    path = tmp_path / "budget.txt"
    path.write_text("budget spreadsheet contents", encoding="utf-8")
    files.index_file(path)
    chat = ai.create_session("Money talk")
    ai.send_message(chat.id, "help me with my budget")

    results = dash.search("budget")
    kinds = {r.kind for r in results}
    assert kinds == {"note", "task", "file", "chat"}


def test_unified_search_empty_query(
    wired: tuple[Database, EventBus, DashboardService],
) -> None:
    _, _, dash = wired
    assert dash.search("   ") == []


def test_search_snippet_centers_on_match(
    wired: tuple[Database, EventBus, DashboardService],
) -> None:
    db, bus, dash = wired
    notes = NotesService(db, bus)
    notes.create("Doc", "lots of preamble text " * 10 + "IMPORTANT KEYWORD here " + "trailer " * 10)
    results = dash.search("IMPORTANT KEYWORD")
    assert results
    assert "IMPORTANT KEYWORD" in results[0].snippet
