"""Task request/context: the data flowing through the engine pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["TaskContext", "TaskRequest"]


@dataclass(slots=True)
class TaskRequest:
    """A user-facing request to the engine."""

    prompt: str
    system: str | None = None
    provider: str | None = None
    model: str | None = None
    skills: tuple[str, ...] = ()
    """Explicit skill names to use. If empty, skills are auto-resolved from
    *prompt* and *file_hints* via the skill resolver."""
    file_hints: tuple[str, ...] = ()
    """File paths or glob patterns relevant to this task, used for skill
    auto-detection (e.g. resolving to the Python skill from a ``*.py`` hint)."""
    max_tokens: int | None = None
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskContext:
    """The request plus everything resolved before calling the provider."""

    request: TaskRequest
    provider_name: str
    model: str
    resolved_skills: tuple[str, ...]
    composed_system: str | None
