"""Seed a workspace with realistic sample data.

Handy for a first look at the app or for screenshots: it creates a few linked
notes, a couple of projects with tasks (including a due date, a recurring
task, and a completed one), an automation rule, and a chat session. Everything
goes through the ordinary services, so the seeded data is indistinguishable
from hand-entered data.

Run it against a throwaway data directory::

    python -m nexus.demo --data-dir /tmp/nexus-demo
    nexus --data-dir /tmp/nexus-demo gui
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections.abc import Sequence

from nexus.app_context import AppContext
from nexus.automation.rules import ActionSpec, Condition
from nexus.core.logging import get_logger

__all__ = ["main", "seed_workspace"]

_logger = get_logger("demo")


def seed_workspace(context: AppContext, *, now: dt.datetime | None = None) -> None:
    """Populate *context* with a small, coherent set of sample content."""
    moment = now or dt.datetime.now(dt.UTC)

    # Notes, linked together with [[wiki links]].
    context.notes.create(
        "Welcome to Nexus",
        "This is your workspace. Try linking to [[Project Ideas]] or "
        "[[Meeting Notes]].\n\nEverything is stored locally and encrypted.",
        tags=["intro"],
    )
    context.notes.create(
        "Project Ideas",
        "- A calmer inbox\n- Weekend woodworking\n- Learn [[Rust]]",
        tags=["ideas"],
    )
    context.notes.create(
        "Meeting Notes",
        "Discussed the roadmap. Follow up in [[Project Ideas]].",
        tags=["work"],
    )
    context.notes.create("Rust", "Ownership, borrowing, lifetimes.", tags=["learning"])

    # A work board with a spread of task states and due dates.
    work = context.tasks.create_project("Work", "Day-to-day work")
    context.tasks.add_task(work.id, "Reply to emails", status="doing")
    context.tasks.add_task(
        work.id, "Prepare quarterly report", due_at=moment + dt.timedelta(days=3)
    )
    context.tasks.add_task(work.id, "Weekly standup", recurrence="weekly")
    done = context.tasks.add_task(work.id, "Book flights", status="done")
    context.tasks.complete(done.id)

    home = context.tasks.create_project("Home", "Personal chores")
    context.tasks.add_task(home.id, "Water the plants", recurrence="P3D")
    context.tasks.add_task(home.id, "Grocery run", due_at=moment + dt.timedelta(days=1))

    # An automation rule: announce whenever a note is created.
    context.automation.create_rule(
        "Announce new notes",
        "note.created",
        conditions=[Condition(field="note_id", op="exists", value=True)],
        actions=[ActionSpec(type="notify", params={"message": "A new note was created"})],
    )
    context.reload_automation()

    # A chat session so the AI panel opens with history.
    session = context.ai.create_session(title="Getting started")
    context.ai.send_message(session.id, "What can this workspace do?")

    _logger.info("seeded demo workspace")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI wrapper: seed the workspace at ``--data-dir`` (or the default)."""
    parser = argparse.ArgumentParser(prog="nexus.demo", description="Seed sample Nexus data.")
    parser.add_argument("--data-dir", help="data directory to seed (default: platform data dir)")
    parser.add_argument("--config", help="path to a config.yaml")
    args = parser.parse_args(argv)

    with AppContext.create(data_dir=args.data_dir, config_path=args.config) as context:
        seed_workspace(context)
    print("Seeded a demo workspace. Launch it with:  nexus", end="")
    print(f" --data-dir {args.data_dir}" if args.data_dir else "")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
