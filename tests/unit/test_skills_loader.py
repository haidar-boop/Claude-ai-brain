"""Tests for aiforge.skills.loader."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from aiforge.skills.loader import BUILTIN_SKILLS_DIR, discover_skills
from aiforge.skills.manifest import SkillManifest


def test_builtin_skills_dir_exists() -> None:
    assert BUILTIN_SKILLS_DIR.is_dir()


def test_discover_skills_finds_manifests_in_extra_dir(tmp_path: Path) -> None:
    skill_dir = tmp_path / "my_skill"
    skill_dir.mkdir()
    (skill_dir / "skill.toml").write_text('name = "custom"\ndescription = "A custom skill"\n')
    manifests = discover_skills(extra_dirs=[tmp_path])
    names = {m.name for m in manifests}
    assert "custom" in names


def test_discover_skills_ignores_directories_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "not_a_skill").mkdir()
    manifests = discover_skills(extra_dirs=[tmp_path])
    assert all(m.name != "not_a_skill" for m in manifests)


def test_discover_skills_ignores_nonexistent_extra_dir(tmp_path: Path) -> None:
    manifests = discover_skills(extra_dirs=[tmp_path / "does_not_exist"])
    assert isinstance(manifests, list)


def test_discover_skills_skips_broken_entry_point_and_keeps_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: one third-party skill package whose entry point raised on
    # load aborted discovery entirely, taking every other skill with it.
    from aiforge.skills import loader as loader_module

    def _broken_load() -> None:
        raise ModuleNotFoundError("no module named 'missing_dependency'")

    good_manifest = SkillManifest(name="good", description="works")
    fake_eps = [
        types.SimpleNamespace(name="broken", load=_broken_load),
        types.SimpleNamespace(name="wrong-type", load=lambda: lambda: "not a manifest"),
        types.SimpleNamespace(name="good", load=lambda: lambda: good_manifest),
    ]
    monkeypatch.setattr(loader_module, "entry_points", lambda *, group: fake_eps)
    manifests = discover_skills()
    names = {m.name for m in manifests}
    assert "good" in names
    assert "broken" not in names
    # The built-in directory scan still contributes normally.
    assert "python" in names
