"""Tests for nexus.services.tasks."""

from __future__ import annotations

import datetime as dt

import pytest

from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.db.database import Database
from nexus.services.tasks import TasksService, next_occurrence


@pytest.fixture
def service() -> TasksService:
    return TasksService(Database.in_memory(), EventBus())


def _project(service: TasksService) -> int:
    return service.create_project("Work").id


# -- recurrence math ------------------------------------------------------


def test_next_occurrence_daily_weekly() -> None:
    base = dt.datetime(2024, 1, 1, 9, 0, tzinfo=dt.UTC)
    assert next_occurrence(base, "daily") == base + dt.timedelta(days=1)
    assert next_occurrence(base, "weekly") == base + dt.timedelta(weeks=1)


def test_next_occurrence_interval_days() -> None:
    base = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert next_occurrence(base, "P3D") == base + dt.timedelta(days=3)


def test_next_occurrence_monthly_clamps_to_month_end() -> None:
    jan31 = dt.datetime(2024, 1, 31, tzinfo=dt.UTC)
    # 2024 is a leap year, so Jan 31 -> Feb 29.
    assert next_occurrence(jan31, "monthly") == dt.datetime(2024, 2, 29, tzinfo=dt.UTC)


def test_next_occurrence_december_rolls_year() -> None:
    dec = dt.datetime(2024, 12, 15, tzinfo=dt.UTC)
    assert next_occurrence(dec, "monthly") == dt.datetime(2025, 1, 15, tzinfo=dt.UTC)


def test_next_occurrence_invalid_rule() -> None:
    with pytest.raises(ValidationError):
        next_occurrence(dt.datetime(2024, 1, 1, tzinfo=dt.UTC), "fortnightly")


# -- projects -------------------------------------------------------------


def test_create_and_list_projects(service: TasksService) -> None:
    service.create_project("Alpha")
    service.create_project("Beta")
    assert [p.name for p in service.list_projects()] == ["Alpha", "Beta"]


def test_duplicate_project_rejected(service: TasksService) -> None:
    service.create_project("Dup")
    with pytest.raises(ValidationError, match="already exists"):
        service.create_project("Dup")


def test_blank_project_rejected(service: TasksService) -> None:
    with pytest.raises(ValidationError):
        service.create_project("  ")


def test_delete_project_cascades_tasks(service: TasksService) -> None:
    pid = _project(service)
    service.add_task(pid, "t1")
    service.delete_project(pid)
    assert service.list_projects() == []


# -- tasks / kanban -------------------------------------------------------


def test_add_task_positions_increment(service: TasksService) -> None:
    pid = _project(service)
    a = service.add_task(pid, "A")
    b = service.add_task(pid, "B")
    assert a.position == 0
    assert b.position == 1


def test_board_groups_by_status(service: TasksService) -> None:
    pid = _project(service)
    service.add_task(pid, "todo task")
    service.add_task(pid, "doing task", status="doing")
    board = service.board(pid)
    assert set(board) == {"todo", "doing"}
    assert board["todo"][0].title == "todo task"


def test_add_task_to_missing_project(service: TasksService) -> None:
    with pytest.raises(NotFoundError):
        service.add_task(999, "orphan")


def test_move_across_columns_renumbers(service: TasksService) -> None:
    pid = _project(service)
    a = service.add_task(pid, "A")
    b = service.add_task(pid, "B")
    service.add_task(pid, "C")
    # Move A to the front of "doing".
    service.move(a.id, status="doing", position=0)
    board = service.board(pid)
    assert [t.title for t in board["todo"]] == ["B", "C"]
    assert [t.position for t in board["todo"]] == [0, 1]  # densified, no gap
    assert [t.title for t in board["doing"]] == ["A"]
    # unused var guard
    assert b.id != a.id


def test_move_within_column_reorders(service: TasksService) -> None:
    pid = _project(service)
    service.add_task(pid, "A")
    service.add_task(pid, "B")
    c = service.add_task(pid, "C")
    service.move(c.id, status="todo", position=0)
    board = service.board(pid)
    assert [t.title for t in board["todo"]] == ["C", "A", "B"]


def test_update_task_due_at_sentinel_vs_none(service: TasksService) -> None:
    pid = _project(service)
    due = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    task = service.add_task(pid, "T", due_at=due)
    # Omitting due_at leaves it unchanged.
    after_title = service.update_task(task.id, title="T2")
    assert after_title.due_at == due
    # Explicit None clears it.
    cleared = service.update_task(task.id, due_at=None)
    assert cleared.due_at is None


def test_complete_non_recurring(service: TasksService) -> None:
    pid = _project(service)
    task = service.add_task(pid, "One-off")
    done = service.complete(task.id)
    assert done.is_done
    assert done.status == "done"


def test_complete_recurring_spawns_next(service: TasksService) -> None:
    pid = _project(service)
    due = dt.datetime(2024, 1, 1, 9, 0, tzinfo=dt.UTC)
    task = service.add_task(pid, "Water plants", due_at=due, recurrence="weekly")
    service.complete(task.id)
    board = service.board(pid)
    # The original is done; a fresh todo occurrence exists a week later.
    todos = board.get("todo", [])
    assert len(todos) == 1
    assert todos[0].due_at == due + dt.timedelta(weeks=1)
    assert todos[0].recurrence == "weekly"


def test_recurring_without_due_does_not_spawn(service: TasksService) -> None:
    pid = _project(service)
    task = service.add_task(pid, "no due", recurrence="daily")
    service.complete(task.id)
    assert service.board(pid).get("todo", []) == []


def test_invalid_recurrence_rejected_on_add(service: TasksService) -> None:
    pid = _project(service)
    with pytest.raises(ValidationError):
        service.add_task(pid, "bad", recurrence="sometimes")


# -- calendar / reminders -------------------------------------------------


def test_calendar_range(service: TasksService) -> None:
    pid = _project(service)
    service.add_task(pid, "in range", due_at=dt.datetime(2024, 3, 15, tzinfo=dt.UTC))
    service.add_task(pid, "out of range", due_at=dt.datetime(2024, 5, 1, tzinfo=dt.UTC))
    service.add_task(pid, "no due")
    hits = service.calendar(
        dt.datetime(2024, 3, 1, tzinfo=dt.UTC), dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    )
    assert [t.title for t in hits] == ["in range"]


def test_due_soon(service: TasksService) -> None:
    pid = _project(service)
    now = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.UTC)
    service.add_task(pid, "soon", due_at=now + dt.timedelta(hours=1))
    service.add_task(pid, "later", due_at=now + dt.timedelta(days=3))
    done = service.add_task(pid, "already done", due_at=now + dt.timedelta(hours=1))
    service.complete(done.id, now=now)
    soon = service.due_soon(within=dt.timedelta(hours=2), now=now)
    assert [t.title for t in soon] == ["soon"]  # "later" out of window, done excluded


def test_events_published() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    svc = TasksService(Database.in_memory(), bus)
    pid = svc.create_project("P").id
    t = svc.add_task(pid, "x")
    svc.move(t.id, status="doing", position=0)
    svc.complete(t.id)
    svc.delete_task(t.id)
    assert seen == [
        "project.created",
        "task.created",
        "task.moved",
        "task.completed",
        "task.deleted",
    ]
