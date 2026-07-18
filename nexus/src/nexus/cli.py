"""The ``nexus`` command-line interface.

One entry point over the same services the GUI uses. With no subcommand it
launches the desktop app; the subcommands give headless access to the
workspace (notes, tasks, export/import), start the local REST API, and list
plugins -- so Nexus is scriptable without a display.

GUI and API imports are deferred into the handlers that need them, so a
headless ``nexus notes list`` never imports PySide6 or aiohttp.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from nexus.__about__ import __version__
from nexus.app_context import AppContext
from nexus.core.errors import NexusError
from nexus.core.logging import get_logger

__all__ = ["main"]

_logger = get_logger("cli")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the ``nexus`` command."""
    parser = argparse.ArgumentParser(prog="nexus", description="Nexus personal workspace.")
    parser.add_argument("--version", action="version", version=f"nexus {__version__}")
    parser.add_argument("--data-dir", help="override the data directory")
    parser.add_argument("--config", help="path to a config.yaml")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="launch the desktop application (default)")

    serve = sub.add_parser("serve", help="run the local REST API")
    serve.add_argument("--host", default=None, help="bind host (default from config)")
    serve.add_argument("--port", type=int, default=None, help="bind port (default from config)")

    notes = sub.add_parser("notes", help="work with notes")
    notes_sub = notes.add_subparsers(dest="notes_command", required=True)
    notes_sub.add_parser("list", help="list notes")
    notes_add = notes_sub.add_parser("add", help="add a note")
    notes_add.add_argument("title")
    notes_add.add_argument("--body", default="")
    notes_add.add_argument("--tags", default="", help="comma-separated tags")

    tasks = sub.add_parser("tasks", help="work with tasks")
    tasks_sub = tasks.add_subparsers(dest="tasks_command", required=True)
    tasks_sub.add_parser("projects", help="list projects")
    tasks_add = tasks_sub.add_parser("add", help="add a task to a project")
    tasks_add.add_argument("project_id", type=int)
    tasks_add.add_argument("title")
    tasks_board = tasks_sub.add_parser("board", help="show a project's board")
    tasks_board.add_argument("project_id", type=int)

    export = sub.add_parser("export", help="export the workspace to a .zip")
    export.add_argument("path")
    imp = sub.add_parser("import", help="import a workspace .zip")
    imp.add_argument("path")

    sub.add_parser("plugins", help="list discovered plugins")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch; return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "gui"):
        return _run_gui(args)

    try:
        with AppContext.create(data_dir=args.data_dir, config_path=args.config) as context:
            return _dispatch(args, context)
    except NexusError as exc:
        print(f"error: {exc}")
        return 1


def _dispatch(args: argparse.Namespace, context: AppContext) -> int:
    if args.command == "serve":
        return _serve(args, context)
    if args.command == "notes":
        return _notes(args, context)
    if args.command == "tasks":
        return _tasks(args, context)
    if args.command == "export":
        return _export(args, context)
    if args.command == "import":
        return _import(args, context)
    if args.command == "plugins":
        return _plugins(context)
    print(f"unknown command: {args.command}")
    return 2


def _run_gui(args: argparse.Namespace) -> int:
    try:
        from nexus.ui.app import run
    except ImportError as exc:  # pragma: no cover - only when PySide6 absent
        print(f"the desktop UI requires PySide6: {exc}")
        return 1
    return run(data_dir=args.data_dir, config_path=args.config)


def _serve(args: argparse.Namespace, context: AppContext) -> int:
    from nexus.api import generate_token, run_server

    host = args.host or context.config.api.host
    port = args.port or context.config.api.port
    token = os.environ.get("NEXUS_API_TOKEN") or generate_token()
    print(f"Nexus API on http://{host}:{port}")
    print(f"Bearer token: {token}")
    print("Set NEXUS_API_TOKEN to reuse a fixed token. Press Ctrl+C to stop.")
    try:
        run_server(context, host=host, port=port, token=token)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nstopped")
    return 0


def _notes(args: argparse.Namespace, context: AppContext) -> int:
    if args.notes_command == "list":
        notes = context.notes.list_notes()
        if not notes:
            print("(no notes)")
        for note in notes:
            label = f"  [{', '.join(note.tags)}]" if note.tags else ""
            print(f"#{note.id}  {note.title}{label}")
        return 0
    if args.notes_command == "add":
        tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
        note = context.notes.create(args.title, args.body, tags=tag_list)
        print(f"created note #{note.id}: {note.title}")
        return 0
    return 2


def _tasks(args: argparse.Namespace, context: AppContext) -> int:
    if args.tasks_command == "projects":
        projects = context.tasks.list_projects()
        if not projects:
            print("(no projects)")
        for project in projects:
            print(f"#{project.id}  {project.name}  ({project.task_count} tasks)")
        return 0
    if args.tasks_command == "add":
        task = context.tasks.add_task(args.project_id, args.title)
        print(f"created task #{task.id} in project {args.project_id}: {task.title}")
        return 0
    if args.tasks_command == "board":
        board = context.tasks.board(args.project_id)
        for status, column in board.items():
            print(f"{status.upper()} ({len(column)})")
            for task in column:
                print(f"  #{task.id}  {task.title}")
        return 0
    return 2


def _export(args: argparse.Namespace, context: AppContext) -> int:
    from nexus.services.transfer import export_workspace

    summary = export_workspace(context, args.path)
    print(
        f"exported {summary.notes} notes, {summary.projects} projects, "
        f"{summary.tasks} tasks, {summary.rules} rules to {args.path}"
    )
    return 0


def _import(args: argparse.Namespace, context: AppContext) -> int:
    from nexus.services.transfer import import_workspace

    summary = import_workspace(context, args.path)
    print(
        f"imported {summary.notes} notes, {summary.projects} projects, "
        f"{summary.tasks} tasks, {summary.rules} rules from {args.path}"
    )
    return 0


def _plugins(context: AppContext) -> int:
    from nexus.plugins import PluginManager

    manager = PluginManager(context)
    names = manager.discover()
    if not names:
        print("(no plugins installed)")
    for name in names:
        print(name)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
