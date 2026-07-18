"""Export and import a workspace as a portable ZIP archive.

The archive holds a single human-readable ``workspace.json`` describing the
user-authored content: notes, projects and their tasks, and automation
rules. That is deliberately the *source* content, not derived state -- indexed
file references, embeddings, chat history, and backups are local or
regenerable, so leaving them out keeps an export portable and privacy-plain
(you can read exactly what leaves your machine).

Import replays the data through the ordinary services, so every validation,
event, and side effect that applies to hand-created content also applies to
imported content -- there is no privileged back door into the database.
"""

from __future__ import annotations

import datetime as dt
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.app_context import AppContext
from nexus.automation.rules import ActionSpec, Condition
from nexus.core.errors import ExportError
from nexus.core.logging import get_logger

__all__ = ["ExportSummary", "export_workspace", "import_workspace"]

_logger = get_logger("transfer")

EXPORT_VERSION = 1
_ARCHIVE_MEMBER = "workspace.json"


@dataclass(frozen=True, slots=True)
class ExportSummary:
    """How many of each entity were exported or imported."""

    notes: int
    projects: int
    tasks: int
    rules: int


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExportError(f"expected an ISO datetime string, got {value!r}")
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ExportError(f"invalid datetime {value!r}") from exc


def export_workspace(context: AppContext, path: Path | str) -> ExportSummary:
    """Write the workspace's authored content to a ZIP archive at *path*."""
    notes_payload = [
        {"title": note.title, "body": note.body, "tags": list(note.tags)}
        for note in context.notes.list_notes()
    ]

    projects_payload = []
    task_count = 0
    for project in context.tasks.list_projects():
        board = context.tasks.board(project.id)
        tasks_payload = []
        for column in board.values():
            for task in column:
                task_count += 1
                tasks_payload.append(
                    {
                        "title": task.title,
                        "description": task.description,
                        "status": task.status,
                        "due_at": _iso(task.due_at),
                        "completed": task.is_done,
                        "recurrence": task.recurrence,
                    }
                )
        projects_payload.append(
            {
                "name": project.name,
                "description": project.description,
                "tasks": tasks_payload,
            }
        )

    rules_payload = [
        {
            "name": rule.name,
            "trigger": rule.trigger,
            "conditions": [c.to_dict() for c in rule.conditions],
            "actions": [a.to_dict() for a in rule.actions],
            "enabled": rule.enabled,
        }
        for rule in context.automation.list_rules()
    ]

    document = {
        "nexus_export_version": EXPORT_VERSION,
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "notes": notes_payload,
        "projects": projects_payload,
        "automation_rules": rules_payload,
    }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_ARCHIVE_MEMBER, json.dumps(document, indent=2, ensure_ascii=False))

    summary = ExportSummary(
        notes=len(notes_payload),
        projects=len(projects_payload),
        tasks=task_count,
        rules=len(rules_payload),
    )
    _logger.info("exported workspace to %s (%s)", target, summary)
    return summary


def _load_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ExportError(f"no such export archive: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            if _ARCHIVE_MEMBER not in archive.namelist():
                raise ExportError(f"archive is missing {_ARCHIVE_MEMBER!r}")
            raw = archive.read(_ARCHIVE_MEMBER)
    except zipfile.BadZipFile as exc:
        raise ExportError(f"{path} is not a valid ZIP archive") from exc

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExportError("workspace.json is not valid JSON") from exc
    if not isinstance(document, dict):
        raise ExportError("workspace.json must contain a JSON object")

    version = document.get("nexus_export_version")
    if version != EXPORT_VERSION:
        raise ExportError(
            f"unsupported export version {version!r} (this build reads v{EXPORT_VERSION})"
        )
    return document


def import_workspace(context: AppContext, path: Path | str) -> ExportSummary:
    """Recreate content from a ZIP archive, replaying it through the services."""
    document = _load_document(Path(path))

    notes = document.get("notes", [])
    for note in notes:
        context.notes.create(note["title"], note.get("body", ""), tags=list(note.get("tags", [])))

    projects = document.get("projects", [])
    task_count = 0
    for project in projects:
        created = context.tasks.create_project(project["name"], project.get("description", ""))
        for task in project.get("tasks", []):
            task_count += 1
            dto = context.tasks.add_task(
                created.id,
                task["title"],
                description=task.get("description", ""),
                status=task.get("status", "todo"),
                due_at=_parse_dt(task.get("due_at")),
                recurrence=task.get("recurrence"),
            )
            if task.get("completed"):
                context.tasks.complete(dto.id)

    rules = document.get("automation_rules", [])
    for rule in rules:
        context.automation.create_rule(
            rule["name"],
            rule["trigger"],
            conditions=[Condition.from_dict(c) for c in rule.get("conditions", [])],
            actions=[ActionSpec.from_dict(a) for a in rule.get("actions", [])],
            enabled=rule.get("enabled", True),
        )

    summary = ExportSummary(
        notes=len(notes),
        projects=len(projects),
        tasks=task_count,
        rules=len(rules),
    )
    _logger.info("imported workspace from %s (%s)", path, summary)
    return summary
