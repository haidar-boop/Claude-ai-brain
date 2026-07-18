"""A small thread-based job scheduler for interval and daily-time jobs.

The design keeps the *when should this run* logic pure and injectable so it
can be tested without sleeping: :class:`IntervalSchedule` and
:class:`DailySchedule` compute the next run time from a given "now", and
:meth:`Scheduler.run_due` runs every job due at a given "now" and advances
it. The background thread (:meth:`Scheduler.start`) is a thin loop that calls
``run_due`` periodically -- so the tricky logic is covered by fast, exact
unit tests and the thread just drives it.

Thread-safety: the job table is guarded by a lock, and a job's callback is
invoked outside the lock so a slow or blocking callback never stalls
scheduling of other jobs or ``add_job``/``remove_job`` from other threads.
"""

from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from nexus.core.errors import ValidationError
from nexus.core.logging import get_logger

__all__ = [
    "DailySchedule",
    "IntervalSchedule",
    "Schedule",
    "ScheduledJob",
    "Scheduler",
]

_logger = get_logger("automation.scheduler")


class Schedule(Protocol):
    """Computes the next run time strictly after a reference moment."""

    def next_run(self, after: dt.datetime) -> dt.datetime:
        """Return the first scheduled time strictly after *after*."""
        ...


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    """Run every *seconds* seconds."""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValidationError("interval seconds must be > 0")

    def next_run(self, after: dt.datetime) -> dt.datetime:
        return after + dt.timedelta(seconds=self.seconds)


@dataclass(frozen=True, slots=True)
class DailySchedule:
    """Run once a day at *hour*:*minute* (in the timezone of the given now)."""

    hour: int
    minute: int = 0

    def __post_init__(self) -> None:
        if not (0 <= self.hour <= 23) or not (0 <= self.minute <= 59):
            raise ValidationError("daily schedule time must be a valid 24h HH:MM")

    def next_run(self, after: dt.datetime) -> dt.datetime:
        candidate = after.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += dt.timedelta(days=1)
        return candidate


@dataclass(slots=True)
class ScheduledJob:
    """A registered job: what to run, on what schedule, and when it's next due."""

    name: str
    schedule: Schedule
    callback: Callable[[], None]
    next_run: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Scheduler:
    """Runs registered jobs on their schedules from a background thread."""

    def __init__(self, *, poll_interval: float = 1.0, clock: Callable[[], dt.datetime] = _utcnow):
        self._jobs: dict[str, ScheduledJob] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._poll_interval = poll_interval
        self._clock = clock

    def add_job(self, name: str, schedule: Schedule, callback: Callable[[], None]) -> None:
        """Register *callback* under *name*; its first run is one interval out.

        Registering a duplicate name replaces the prior job, so reconfiguring
        a schedule is idempotent.
        """
        now = self._clock()
        with self._lock:
            self._jobs[name] = ScheduledJob(
                name=name, schedule=schedule, callback=callback, next_run=schedule.next_run(now)
            )
        _logger.debug("scheduled job %r", name)

    def remove_job(self, name: str) -> None:
        with self._lock:
            self._jobs.pop(name, None)

    def job_names(self) -> list[str]:
        with self._lock:
            return sorted(self._jobs)

    def run_due(self, now: dt.datetime | None = None) -> int:
        """Run every job due at *now* and advance it; return how many ran.

        A job whose callback raises is logged and still rescheduled, so one
        misbehaving job never stops the scheduler or starves the others.
        Callbacks run outside the lock.
        """
        moment = now or self._clock()
        with self._lock:
            due = [job for job in self._jobs.values() if job.next_run <= moment]
        for job in due:
            try:
                job.callback()
            except Exception:
                _logger.exception("scheduled job %r failed", job.name)
            with self._lock:
                # The job may have been removed while its callback ran.
                if job.name in self._jobs:
                    job.next_run = job.schedule.next_run(moment)
        return len(due)

    def start(self) -> None:
        """Start the background scheduling thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="nexus-scheduler", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the thread to stop and wait for it to finish."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_due()
            self._stop.wait(self._poll_interval)
