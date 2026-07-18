"""Tests for nexus.automation.scheduler."""

from __future__ import annotations

import datetime as dt
import threading

import pytest

from nexus.automation.scheduler import DailySchedule, IntervalSchedule, Scheduler
from nexus.core.errors import ValidationError


def test_interval_next_run() -> None:
    base = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.UTC)
    assert IntervalSchedule(60).next_run(base) == base + dt.timedelta(seconds=60)


def test_interval_rejects_nonpositive() -> None:
    with pytest.raises(ValidationError):
        IntervalSchedule(0)


def test_daily_next_run_today_then_tomorrow() -> None:
    morning = dt.datetime(2024, 1, 1, 8, 0, tzinfo=dt.UTC)
    # 09:00 is still ahead today.
    assert DailySchedule(9, 0).next_run(morning) == dt.datetime(2024, 1, 1, 9, 0, tzinfo=dt.UTC)
    # 07:00 already passed -> tomorrow.
    assert DailySchedule(7, 0).next_run(morning) == dt.datetime(2024, 1, 2, 7, 0, tzinfo=dt.UTC)


def test_daily_rejects_bad_time() -> None:
    with pytest.raises(ValidationError):
        DailySchedule(25, 0)


def test_run_due_runs_and_advances() -> None:
    fired: list[str] = []
    now = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.UTC)
    sched = Scheduler(clock=lambda: now)
    sched.add_job("tick", IntervalSchedule(10), lambda: fired.append("x"))
    # Job's next_run is now+10; nothing due yet.
    assert sched.run_due(now) == 0
    # At now+10 it's due.
    assert sched.run_due(now + dt.timedelta(seconds=10)) == 1
    assert fired == ["x"]
    # It advanced; not due again immediately.
    assert sched.run_due(now + dt.timedelta(seconds=10)) == 0


def test_failing_job_is_rescheduled_not_fatal() -> None:
    now = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.UTC)
    calls: list[int] = []

    def boom() -> None:
        calls.append(1)
        raise RuntimeError("job bug")

    sched = Scheduler(clock=lambda: now)
    sched.add_job("bad", IntervalSchedule(5), boom)
    later = now + dt.timedelta(seconds=5)
    sched.run_due(later)
    # Still scheduled and runs again at the next due time.
    sched.run_due(now + dt.timedelta(seconds=10))
    assert len(calls) == 2


def test_remove_job() -> None:
    now = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.UTC)
    sched = Scheduler(clock=lambda: now)
    sched.add_job("a", IntervalSchedule(1), lambda: None)
    sched.remove_job("a")
    assert sched.job_names() == []


def test_start_stop_actually_runs_a_job() -> None:
    fired = threading.Event()
    # A real (tiny) interval plus a short poll so the loop runs the job fast.
    sched = Scheduler(poll_interval=0.01)
    sched.add_job("quick", IntervalSchedule(0.01), fired.set)
    sched.start()
    try:
        assert fired.wait(timeout=2.0), "scheduled job did not fire"
    finally:
        sched.stop()
    assert "quick" in sched.job_names()
