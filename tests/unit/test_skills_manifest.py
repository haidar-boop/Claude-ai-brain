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


def test_from_dict_string_enabled_raises_instead_of_silently_inverting() -> None:
    # Regression: bool("false") is True, so a quoted TOML string silently
    # shipped the skill ENABLED. Must raise a clear validation error.
    with pytest.raises(SkillValidationError, match="'enabled' must be a boolean"):
        SkillManifest.from_dict({"name": "x", "description": "y", "enabled": "false"})


def test_from_dict_string_priority_raises_skill_validation_error() -> None:
    # Regression: int("high") raised a raw ValueError, escaping the
    # documented "every manifest failure is SkillValidationError" contract.
    with pytest.raises(SkillValidationError, match="'priority' must be an integer"):
        SkillManifest.from_dict({"name": "x", "description": "y", "priority": "high"})


def test_from_dict_bool_priority_raises() -> None:
    # bool is an int subclass; `priority = true` is a mistake, not priority=1.
    with pytest.raises(SkillValidationError, match="'priority' must be an integer"):
        SkillManifest.from_dict({"name": "x", "description": "y", "priority": True})


def test_from_dict_non_string_list_element_raises() -> None:
    # Regression: TOML 1.0 allows mixed arrays; languages = ["python", 3]
    # passed validation and crashed later in indexing/scoring/fnmatch with a
    # traceback that never named the offending manifest.
    with pytest.raises(SkillValidationError, match="'languages' must contain only strings"):
        SkillManifest.from_dict({"name": "x", "description": "y", "languages": ["python", 3]})
    with pytest.raises(SkillValidationError, match="'file_globs' must contain only strings"):
        SkillManifest.from_dict({"name": "x", "description": "y", "file_globs": [1]})


def test_from_toml_deeply_nested_raises_skill_validation_error(tmp_path: Path) -> None:
    # tomllib raises bare RecursionError on pathological nesting; the
    # contract is that every manifest failure is a SkillValidationError
    # naming its source file.
    toml_path = tmp_path / "skill.toml"
    toml_path.write_text("keywords = " + "[" * 5000 + "]" * 5000 + "\n")
    with pytest.raises(SkillValidationError, match="nested too deeply"):
        SkillManifest.from_toml(toml_path)


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
