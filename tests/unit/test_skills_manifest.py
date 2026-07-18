"""Tests for aiforge.skills.manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from aiforge.core.errors import SkillValidationError
from aiforge.skills.manifest import SkillManifest


def test_from_dict_minimal() -> None:
    manifest = SkillManifest.from_dict({"name": "python", "description": "Python skill"})
    assert manifest.name == "python"
    assert manifest.description == "Python skill"
    assert manifest.languages == ()
    assert manifest.priority == 0
    assert manifest.enabled is True


def test_from_dict_full() -> None:
    data = {
        "name": "python",
        "description": "Python skill",
        "languages": ["python"],
        "frameworks": ["Django"],
        "libraries": ["requests"],
        "file_globs": ["*.py"],
        "keywords": ["python", "pip"],
        "patterns": ["use comprehensions"],
        "best_practices": ["follow PEP 8"],
        "debugging": ["use pdb"],
        "optimization": ["profile first"],
        "testing": ["pytest"],
        "review_rules": ["no mutable defaults"],
        "documentation_style": "Google-style",
        "requires": [],
        "priority": 10,
        "enabled": False,
    }
    manifest = SkillManifest.from_dict(data)
    assert manifest.languages == ("python",)
    assert manifest.priority == 10
    assert manifest.enabled is False


def test_from_dict_missing_required_field_raises() -> None:
    with pytest.raises(SkillValidationError, match="name"):
        SkillManifest.from_dict({"description": "no name"})


def test_from_dict_unknown_field_raises() -> None:
    with pytest.raises(SkillValidationError, match="unknown field"):
        SkillManifest.from_dict({"name": "x", "description": "y", "bogus_field": True})


def test_from_dict_wrong_type_for_list_field_raises() -> None:
    with pytest.raises(SkillValidationError, match="must be a list"):
        SkillManifest.from_dict({"name": "x", "description": "y", "languages": "python"})


def test_from_toml_parses_file(tmp_path: Path) -> None:
    toml_path = tmp_path / "skill.toml"
    toml_path.write_text('name = "python"\ndescription = "Python skill"\nlanguages = ["python"]\n')
    manifest = SkillManifest.from_toml(toml_path)
    assert manifest.name == "python"
    assert manifest.languages == ("python",)
    assert manifest.source == str(toml_path)


def test_from_toml_invalid_syntax_raises(tmp_path: Path) -> None:
    toml_path = tmp_path / "skill.toml"
    toml_path.write_text("this is not [valid toml")
    with pytest.raises(SkillValidationError, match="invalid TOML"):
        SkillManifest.from_toml(toml_path)


def test_from_toml_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SkillValidationError, match="cannot read"):
        SkillManifest.from_toml(tmp_path / "missing.toml")


def test_prompt_guidance_includes_name_and_sections() -> None:
    manifest = SkillManifest(
        name="python",
        description="Python skill",
        languages=("python",),
        best_practices=("follow PEP 8",),
    )
    guidance = manifest.prompt_guidance()
    assert "python skill" in guidance.lower()
    assert "Python skill" in guidance
    assert "follow PEP 8" in guidance


def test_prompt_guidance_omits_empty_sections() -> None:
    manifest = SkillManifest(name="x", description="y")
    guidance = manifest.prompt_guidance()
    assert "Languages" not in guidance
    assert "Best practices" not in guidance
