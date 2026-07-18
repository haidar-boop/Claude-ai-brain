"""Tests for aiforge.skills.loader."""

from __future__ import annotations

from pathlib import Path

from aiforge.skills.loader import BUILTIN_SKILLS_DIR, discover_skills


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
