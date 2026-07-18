"""Tests for aiforge.skills.resolver."""

from __future__ import annotations

import pytest

from aiforge.core.errors import SkillNotFoundError
from aiforge.skills.manifest import SkillManifest
from aiforge.skills.registry import SkillRegistry
from aiforge.skills.resolver import SkillResolver


def _manifest(name: str, **overrides: object) -> SkillManifest:
    defaults: dict[str, object] = {"name": name, "description": f"{name} skill"}
    defaults.update(overrides)
    return SkillManifest(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(
        _manifest(
            "python",
            languages=("python",),
            keywords=("django", "flask"),
            file_globs=("*.py",),
            priority=10,
        )
    )
    reg.register(
        _manifest(
            "typescript",
            languages=("typescript",),
            keywords=("react", "node"),
            file_globs=("*.ts", "*.tsx"),
        )
    )
    return reg


def test_resolve_by_prompt_language_match(registry: SkillRegistry) -> None:
    resolver = SkillResolver(registry)
    result = resolver.resolve(prompt="write a python function")
    assert [m.name for m in result.selected] == ["python"]
    assert result.composed_guidance is not None
    assert "python" in result.composed_guidance.lower()


def test_resolve_by_file_hint_glob(registry: SkillRegistry) -> None:
    resolver = SkillResolver(registry)
    result = resolver.resolve(prompt="fix this bug", file_hints=("src/app.tsx",))
    assert [m.name for m in result.selected] == ["typescript"]


def test_resolve_explicit_overrides_scoring(registry: SkillRegistry) -> None:
    resolver = SkillResolver(registry)
    result = resolver.resolve(explicit=("typescript",), prompt="write python code")
    assert [m.name for m in result.selected] == ["typescript"]


def test_resolve_explicit_missing_skill_raises(registry: SkillRegistry) -> None:
    resolver = SkillResolver(registry)
    with pytest.raises(SkillNotFoundError):
        resolver.resolve(explicit=("nonexistent",))


def test_resolve_no_match_returns_empty() -> None:
    resolver = SkillResolver(SkillRegistry())
    result = resolver.resolve(prompt="something unrelated to any skill")
    assert result.selected == ()
    assert result.composed_guidance is None


def test_resolve_respects_max_skills(registry: SkillRegistry) -> None:
    resolver = SkillResolver(registry, max_skills=1)
    result = resolver.resolve(prompt="python and typescript and django and react code")
    assert len(result.selected) == 1


def test_resolve_conflict_resolution_uses_priority_tiebreak() -> None:
    tie_registry = SkillRegistry()
    tie_registry.register(_manifest("a", languages=("shared",), priority=1))
    tie_registry.register(_manifest("b", languages=("shared",), priority=5))
    resolver = SkillResolver(tie_registry, max_skills=1)
    result = resolver.resolve(prompt="shared")
    assert result.selected[0].name == "b"


def test_resolve_excludes_disabled_skills_from_scoring() -> None:
    disabled_registry = SkillRegistry()
    disabled_registry.register(_manifest("python", languages=("python",), enabled=False))
    resolver = SkillResolver(disabled_registry)
    result = resolver.resolve(prompt="python")
    assert result.selected == ()


def test_resolve_explicit_skips_disabled_without_raising(registry: SkillRegistry) -> None:
    registry.apply_policy(enabled=(), disabled=())
    resolver = SkillResolver(registry)
    result = resolver.resolve(explicit=("python",))
    assert result.selected == ()
