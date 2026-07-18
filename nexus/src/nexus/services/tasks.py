"""Tasks service: projects, a kanban board, a calendar view, and recurrence.

Design notes that keep this UI-free and testable:
- A *project* is a board; a *task* lives in a status column (``todo`` /
  ``doing`` / ``done`` by default, but any string a board wants) at an
  integer ``position`` that orders it within that column. Moving a task is a
  single ``move`` call that re-numbers the affected column densely, so the
  UI never has to compute positions itself.
- The calendar view is a date-range query over ``due_at``.
- Recurrence is expressed as a small rule string (``daily`` / ``weekly`` /
  ``monthly`` / ``P<n>D`` for "every n days"). Completing a recurring task
  spawns the next occurrence with ``due_at`` advanced by the rule, so a
  recurring task is never "used up" -- exactly what a UI expects when you
  tick off "water the plants (weekly)".
- ``due_soon`` computes which tasks warrant a reminder, leaving the actual
  notification delivery to the UI/automation layer.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import Project, Task

__all__ = [
    "ProjectDTO",
    "TaskDTO",
    "TasksService",
    "next_occurrence",
]

_logger = get_logger("services.tasks")

_INTERVAL_DAYS_RE = re.compile(r"^P(\d+)D$")


class _Unset:
    """Sentinel type distinguishing "argument omitted" from "explicitly None"."""

    __slots__ = ()


_UNSET = _Unset()


def next_occurrence(due: dt.datetime, recurrence: str) -> dt.datetime:
    """Return the next due date after *due* for a *recurrence* rule.

    Supports ``daily``, ``weekly``, ``monthly``, and ``P<n>D`` (every n
    days). ``monthly`` clamps to the last valid day of the target month, so
    a task due Jan 31 recurs to Feb 28/29 rather than overflowing.
    """
    rule = recurrence.strip().lower()
    if rule == "daily":
        return due + dt.timedelta(days=1)
    if rule == "weekly":
        return due + dt.timedelta(weeks=1)
    if rule == "monthly":
        return _add_month(due)
    match = _INTERVAL_DAYS_RE.match(recurrence.strip())
    if match:
        return due + dt.timedelta(days=int(match.group(1)))
    raise ValidationError(f"unsupported recurrence rule: {recurrence!r}")


def _add_month(moment: dt.datetime) -> dt.datetime:
    month = moment.month % 12 + 1
    year = moment.year + (moment.month // 12)
    last_day = calendar.monthrange(year, month)[1]
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


@dataclass(frozen=True, slots=True)
class ProjectDTO:
    """A detached view of a project (board)."""

    id: int
    name: str
    description: str
    task_count: int
    created_at: dt.datetime


@dataclass(frozen=True, slots=True)
class TaskDTO:
    """A detached view of a task."""

    id: int
    project_id: int
    title: str
    description: str
    status: str
    position: int
    due_at: dt.datetime | None
    completed_at: dt.datetime | None
    recurrence: str | None

    @property
    def is_done(self) -> bool:
        return self.completed_at is not None


class TasksService:
    """Manage projects and their tasks across a kanban board and calendar."""

    def __init__(self, database: Database, events: EventBus | None = None) -> None:
        self._db = database
        self._events = events or EventBus()

    # -- projects ---------------------------------------------------------

    def create_project(self, name: str, description: str = "") -> ProjectDTO:
        clean = name.strip()
        if not clean:
            raise ValidationError("project name must not be empty")
        with self._db.session() as session:
            if session.scalar(select(Project).where(Project.name == clean)) is not None:
                raise ValidationError(f"a project named {clean!r} already exists")
            project = Project(name=clean, description=description)
            session.add(project)
            session.flush()
            dto = self._project_dto(session, project)
        self._events.publish("project.created", project_id=dto.id, name=dto.name)
        return dto

    def list_projects(self) -> list[ProjectDTO]:
        with self._db.session() as session:
            projects = session.scalars(select(Project).order_by(Project.name)).all()
            return [self._project_dto(session, p) for p in projects]

    def delete_project(self, project_id: int) -> None:
        with self._db.session() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise NotFoundError("project", project_id)
            session.delete(project)
        self._events.publish("project.deleted", project_id=project_id)

    # -- tasks ------------------------------------------------------------

    def add_task(
        self,
        project_id: int,
        title: str,
        *,
        description: str = "",
        status: str = "todo",
        due_at: dt.datetime | None = None,
        recurrence: str | None = None,
    ) -> TaskDTO:
        """Add a task to the end of a project's *status* column."""
        clean = title.strip()
        if not clean:
            raise ValidationError("task title must not be empty")
        if recurrence is not None:
            _validate_recurrence(recurrence)
        with self._db.session() as session:
            if session.get(Project, project_id) is None:
                raise NotFoundError("project", project_id)
            position = self._next_position(session, project_id, status)
            task = Task(
                project_id=project_id,
                title=clean,
                description=description,
                status=status,
                position=position,
                due_at=due_at,
                recurrence=recurrence,
            )
            session.add(task)
            session.flush()
            dto = self._task_dto(task)
        self._events.publish("task.created", task_id=dto.id, project_id=project_id)
        return dto

    def get_task(self, task_id: int) -> TaskDTO:
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise NotFoundError("task", task_id)
            return self._task_dto(task)

    def update_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        due_at: dt.datetime | None | _Unset = _UNSET,
        recurrence: str | None | _Unset = _UNSET,
    ) -> TaskDTO:
        """Update task fields. ``due_at``/``recurrence`` accept explicit None.

        Because ``None`` is a meaningful value for those two fields (clear
        the due date / make non-recurring), a sentinel distinguishes "leave
        unchanged" from "set to None" -- the classic falsy-argument trap.
        """
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise NotFoundError("task", task_id)
            if title is not None:
                clean = title.strip()
                if not clean:
                    raise ValidationError("task title must not be empty")
                task.title = clean
            if description is not None:
                task.description = description
            if not isinstance(due_at, _Unset):
                task.due_at = due_at
            if not isinstance(recurrence, _Unset):
                if recurrence is not None:
                    _validate_recurrence(recurrence)
                task.recurrence = recurrence
            session.flush()
            dto = self._task_dto(task)
        self._events.publish("task.updated", task_id=dto.id)
        return dto

    def move(self, task_id: int, *, status: str, position: int) -> TaskDTO:
        """Move a task to *status* at *position*, re-densifying columns.

        Positions in the source and destination columns are renumbered
        0..n-1 so there are never gaps or collisions, which keeps the kanban
        board's ordering stable no matter how the UI drags things around.
        """
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise NotFoundError("task", task_id)
            old_status = task.status
            task.status = status
            session.flush()
            self._renumber(session, task.project_id, old_status)
            if status != old_status:
                self._insert_at(session, task, status, position)
            else:
                self._reorder_within(session, task, position)
            session.flush()
            dto = self._task_dto(task)
        self._events.publish("task.moved", task_id=dto.id, status=status)
        return dto

    def complete(self, task_id: int, *, now: dt.datetime | None = None) -> TaskDTO:
        """Mark a task done. A recurring task also spawns its next occurrence.

        Returns the completed task. When the task recurs and has a due date,
        a fresh task is created (same title/column/recurrence) with ``due_at``
        advanced by the rule, so ticking off a recurring task rolls it
        forward instead of ending it.
        """
        moment = now or dt.datetime.now(dt.UTC)
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise NotFoundError("task", task_id)
            task.completed_at = moment
            task.status = "done"
            spawn: Task | None = None
            if task.recurrence and task.due_at is not None:
                spawn = Task(
                    project_id=task.project_id,
                    title=task.title,
                    description=task.description,
                    status="todo",
                    position=self._next_position(session, task.project_id, "todo"),
                    due_at=next_occurrence(task.due_at, task.recurrence),
                    recurrence=task.recurrence,
                )
                session.add(spawn)
            session.flush()
            dto = self._task_dto(task)
            spawn_id = spawn.id if spawn is not None else None
        self._events.publish("task.completed", task_id=dto.id, spawned_task_id=spawn_id)
        return dto

    def delete_task(self, task_id: int) -> None:
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise NotFoundError("task", task_id)
            session.delete(task)
        self._events.publish("task.deleted", task_id=task_id)

    # -- views ------------------------------------------------------------

    def board(self, project_id: int) -> dict[str, list[TaskDTO]]:
        """Return the project's tasks grouped by status, each column ordered."""
        with self._db.session() as session:
            if session.get(Project, project_id) is None:
                raise NotFoundError("project", project_id)
            tasks = session.scalars(
                select(Task)
                .where(Task.project_id == project_id)
                .order_by(Task.status, Task.position)
            ).all()
        board: dict[str, list[TaskDTO]] = {}
        for task in tasks:
            board.setdefault(task.status, []).append(self._task_dto(task))
        return board

    def calendar(self, start: dt.datetime, end: dt.datetime) -> list[TaskDTO]:
        """Return tasks with a ``due_at`` in ``[start, end)``, chronologically."""
        with self._db.session() as session:
            tasks = session.scalars(
                select(Task)
                .where(Task.due_at.is_not(None), Task.due_at >= start, Task.due_at < end)
                .order_by(Task.due_at)
            ).all()
            return [self._task_dto(t) for t in tasks]

    def due_soon(self, *, within: dt.timedelta, now: dt.datetime | None = None) -> list[TaskDTO]:
        """Return not-yet-completed tasks due within *within* of *now*.

        This is the reminder source: the automation/UI layer decides how to
        surface these (a toast, a tray notification), the service just says
        which tasks qualify.
        """
        moment = now or dt.datetime.now(dt.UTC)
        horizon = moment + within
        with self._db.session() as session:
            tasks = session.scalars(
                select(Task)
                .where(
                    Task.completed_at.is_(None),
                    Task.due_at.is_not(None),
                    Task.due_at <= horizon,
                )
                .order_by(Task.due_at)
            ).all()
            return [self._task_dto(t) for t in tasks]

    # -- internals --------------------------------------------------------

    def _next_position(self, session: Session, project_id: int, status: str) -> int:
        current_max = session.scalar(
            select(func.max(Task.position)).where(
                Task.project_id == project_id, Task.status == status
            )
        )
        return 0 if current_max is None else current_max + 1

    def _column_tasks(self, session: Session, project_id: int, status: str) -> list[Task]:
        return list(
            session.scalars(
                select(Task)
                .where(Task.project_id == project_id, Task.status == status)
                .order_by(Task.position)
            )
        )

    def _renumber(self, session: Session, project_id: int, status: str) -> None:
        for index, task in enumerate(self._column_tasks(session, project_id, status)):
            task.position = index

    def _insert_at(self, session: Session, task: Task, status: str, position: int) -> None:
        others = [
            t for t in self._column_tasks(session, task.project_id, status) if t.id != task.id
        ]
        clamped = max(0, min(position, len(others)))
        others.insert(clamped, task)
        for index, member in enumerate(others):
            member.position = index

    def _reorder_within(self, session: Session, task: Task, position: int) -> None:
        self._insert_at(session, task, task.status, position)

    def _project_dto(self, session: Session, project: Project) -> ProjectDTO:
        count = session.scalar(select(func.count(Task.id)).where(Task.project_id == project.id))
        return ProjectDTO(
            id=project.id,
            name=project.name,
            description=project.description,
            task_count=int(count or 0),
            created_at=project.created_at,
        )

    def _task_dto(self, task: Task) -> TaskDTO:
        return TaskDTO(
            id=task.id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status,
            position=task.position,
            due_at=task.due_at,
            completed_at=task.completed_at,
            recurrence=task.recurrence,
        )


def _validate_recurrence(recurrence: str) -> None:
    # Reuse next_occurrence's parser against a throwaway date to validate the
    # rule string without duplicating the accepted-rule list.
    next_occurrence(dt.datetime(2000, 1, 1, tzinfo=dt.UTC), recurrence)
