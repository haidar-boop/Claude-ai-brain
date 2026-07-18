"""Tests for aiforge.skills.registry."""

from __future__ import annotations

import pytest

from aiforge.core.errors import SkillNotFoundError
from aiforge.skills.manifest import SkillManifest
from aiforge.skills.registry import SkillRegistry


def _manifest(name: str, **overrides: object) -> SkillManifest:
    defaults: dict[str, object] = {"name": name, "description": f"{name} skill"}
    defaults.update(overrides)
    return SkillManifest(**defaults)  # type: ignore[arg-type]


def test_register_and_require() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python"))
    assert registry.require("python").name == "python"


def test_require_missing_raises() -> None:
    registry = SkillRegistry()
    with pytest.raises(SkillNotFoundError):
        registry.require("missing")


def test_names_enabled_only_filters_disabled() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python", enabled=True))
    registry.register(_manifest("rust", enabled=False))
    assert registry.names(enabled_only=True) == ["python"]
    assert registry.names() == ["python", "rust"]


def test_apply_policy_explicit_enabled_list_restricts() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python"))
    registry.register(_manifest("rust"))
    registry.apply_policy(enabled=("python",), disabled=())
    assert registry.require("python").enabled is True
    assert registry.require("rust").enabled is False


def test_apply_policy_none_enabled_keeps_manifest_defaults() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python", enabled=True))
    registry.register(_manifest("rust", enabled=False))
    registry.apply_policy(enabled=None, disabled=())
    assert registry.require("python").enabled is True
    assert registry.require("rust").enabled is False


def test_apply_policy_disabled_overrides_enabled() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python"))
    registry.apply_policy(enabled=("python",), disabled=("python",))
    assert registry.require("python").enabled is False


def test_candidates_matches_by_language_keyword() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python", languages=("python",), keywords=("django",)))
    registry.register(_manifest("rust", languages=("rust",)))
    candidates = registry.candidates(["python"])
    assert [m.name for m in candidates] == ["python"]


def test_candidates_excludes_disabled_skills() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python", languages=("python",), enabled=False))
    assert registry.candidates(["python"]) == []


def test_all_enabled_excludes_disabled() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python", enabled=True))
    registry.register(_manifest("rust", enabled=False))
    names = {m.name for m in registry.all_enabled()}
    assert names == {"python"}


def test_register_duplicate_without_replace_raises() -> None:
    registry = SkillRegistry()
    registry.register(_manifest("python"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_manifest("python"))


def test_register_all_registers_multiple() -> None:
    registry = SkillRegistry()
    registry.register_all([_manifest("python"), _manifest("rust")])
    assert registry.names() == ["python", "rust"]
