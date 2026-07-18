"""Skill manifest schema: the ``skill.toml`` contract.

A skill packages the knowledge the engine composes into its system prompt
when a task matches it: languages, frameworks, libraries, coding patterns,
best practices, debugging/optimization strategies, documentation style,
testing approach, and code review rules. Adding a new skill means adding a
new ``skill.toml`` folder (or shipping an installable package registered
under the ``aiforge.skills`` entry-point group) -- nothing here changes.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiforge.core.errors import SkillValidationError

__all__ = ["SkillManifest"]

_REQUIRED_FIELDS = ("name", "description")
_LIST_FIELDS = (
    "languages",
    "frameworks",
    "libraries",
    "file_globs",
    "keywords",
    "patterns",
    "best_practices",
    "debugging",
    "optimization",
    "testing",
    "review_rules",
    "requires",
)
_STR_FIELDS = ("name", "description", "documentation_style")


@dataclass(frozen=True, slots=True)
class SkillManifest:
    """A parsed, validated ``skill.toml``."""

    name: str
    description: str
    languages: tuple[str, ...] = ()
    frameworks: tuple[str, ...] = ()
    libraries: tuple[str, ...] = ()
    file_globs: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    best_practices: tuple[str, ...] = ()
    debugging: tuple[str, ...] = ()
    optimization: tuple[str, ...] = ()
    testing: tuple[str, ...] = ()
    review_rules: tuple[str, ...] = ()
    documentation_style: str = ""
    requires: tuple[str, ...] = ()
    """Names of other skills this one composes with or depends on."""
    priority: int = 0
    """Higher priority wins conflict-resolution tie-breaks when two skills
    score equally for the same task."""
    enabled: bool = True
    source: str = ""
    """Where this manifest was loaded from (a file path or entry-point
    name), for diagnostics -- not part of the ``skill.toml`` schema itself."""

    def prompt_guidance(self) -> str:
        """Render this skill's knowledge as system-prompt guidance text."""
        sections: list[tuple[str, tuple[str, ...] | str]] = [
            ("Languages", self.languages),
            ("Frameworks", self.frameworks),
            ("Libraries", self.libraries),
            ("Coding patterns", self.patterns),
            ("Best practices", self.best_practices),
            ("Debugging strategies", self.debugging),
            ("Optimization strategies", self.optimization),
            ("Testing approach", self.testing),
            ("Code review rules", self.review_rules),
            ("Documentation style", self.documentation_style),
        ]
        lines = [f"## {self.name} skill", self.description, ""]
        for title, value in sections:
            if not value:
                continue
            lines.append(f"### {title}")
            if isinstance(value, str):
                lines.append(value)
            else:
                lines.extend(f"- {item}" for item in value)
            lines.append("")
        return "\n".join(lines).strip()

    @classmethod
    def from_toml(cls, path: Path) -> SkillManifest:
        """Parse and validate a ``skill.toml`` file at *path*."""
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except OSError as exc:
            raise SkillValidationError(f"cannot read manifest: {exc}", source=str(path)) from exc
        except tomllib.TOMLDecodeError as exc:
            raise SkillValidationError(f"invalid TOML: {exc}", source=str(path)) from exc
        except RecursionError as exc:
            # tomllib raises bare RecursionError for pathologically nested
            # documents; keep the "manifest failures are SkillValidationError
            # naming their source" contract.
            raise SkillValidationError("TOML nested too deeply to parse", source=str(path)) from exc
        return cls.from_dict(data, source=str(path))

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "") -> SkillManifest:
        """Validate a parsed manifest mapping and build a :class:`SkillManifest`."""
        missing = [name for name in _REQUIRED_FIELDS if not data.get(name)]
        if missing:
            raise SkillValidationError(
                f"missing required field(s): {', '.join(missing)}", source=source
            )
        kwargs: dict[str, Any] = {"source": source}
        for key, value in data.items():
            if key in _LIST_FIELDS:
                if not isinstance(value, list):
                    raise SkillValidationError(
                        f"field {key!r} must be a list, got {type(value).__name__}", source=source
                    )
                # TOML 1.0 permits mixed-type arrays; a non-string element
                # would pass here and crash far away (indexing, scoring,
                # fnmatch) with a traceback that never names this file.
                for item in value:
                    if not isinstance(item, str):
                        raise SkillValidationError(
                            f"field {key!r} must contain only strings, got {type(item).__name__}",
                            source=source,
                        )
                kwargs[key] = tuple(value)
            elif key in _STR_FIELDS:
                kwargs[key] = str(value)
            elif key == "priority":
                # bool is an int subclass -- reject it explicitly, and reject
                # strings rather than int()-coercing, so `priority = "high"`
                # raises SkillValidationError instead of a raw ValueError.
                if isinstance(value, bool) or not isinstance(value, int):
                    raise SkillValidationError(
                        f"field 'priority' must be an integer, got {type(value).__name__}",
                        source=source,
                    )
                kwargs[key] = value
            elif key == "enabled":
                # bool(value) would silently turn the string "false" into
                # True; require a real TOML boolean instead.
                if not isinstance(value, bool):
                    raise SkillValidationError(
                        f"field 'enabled' must be a boolean, got {type(value).__name__}",
                        source=source,
                    )
                kwargs[key] = value
            else:
                raise SkillValidationError(f"unknown field {key!r}", source=source)
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise SkillValidationError(f"invalid manifest shape: {exc}", source=source) from exc
