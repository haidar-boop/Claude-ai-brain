"""Example out-of-tree AIForge skill: Elixir.

Demonstrates the plugin contract for shipping a skill as an installable
package rather than adding it to AIForge's own builtin/ directory. Register
the exposed callable under the ``aiforge.skills`` entry-point group in
pyproject.toml; AIForge discovers it automatically once this package is
installed -- no AIForge core file changes.
"""

from __future__ import annotations

from pathlib import Path

from aiforge.skills.manifest import SkillManifest

__all__ = ["load_manifest"]

_MANIFEST_PATH = Path(__file__).parent / "skill.toml"


def load_manifest() -> SkillManifest:
    """Entry-point target: parses and returns this package's :class:`SkillManifest`."""
    return SkillManifest.from_toml(_MANIFEST_PATH)
