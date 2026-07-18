"""Skill discovery: scans directories and entry points for ``skill.toml`` manifests.

Adding a new skill means adding a new ``skill.toml`` (in-tree under the
built-in skills directory, or an extra configured directory) or shipping an
installable package registered under the ``aiforge.skills`` entry-point
group -- no core file changes.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import entry_points
from pathlib import Path

from aiforge.skills.manifest import SkillManifest

__all__ = ["BUILTIN_SKILLS_DIR", "discover_skills"]

BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin"
_ENTRY_POINT_GROUP = "aiforge.skills"
_MANIFEST_FILENAME = "skill.toml"


def discover_skills(*, extra_dirs: Iterable[Path | str] = ()) -> list[SkillManifest]:
    """Discover every skill from the built-in directory, *extra_dirs*, and entry points.

    Directory-discovered manifests come from immediate subdirectories
    containing a ``skill.toml``. Entry-point-discovered manifests point at
    either a :class:`SkillManifest` instance or a zero-argument callable
    that returns one, for skill packages that build their manifest in
    Python rather than shipping a TOML file.
    """
    manifests: list[SkillManifest] = []
    for directory in (BUILTIN_SKILLS_DIR, *(Path(d) for d in extra_dirs)):
        manifests.extend(_scan_directory(directory))
    manifests.extend(_discover_entry_points())
    return manifests


def _scan_directory(directory: Path) -> list[SkillManifest]:
    if not directory.is_dir():
        return []
    manifests = []
    for child in sorted(directory.iterdir()):
        manifest_path = child / _MANIFEST_FILENAME
        if child.is_dir() and manifest_path.is_file():
            manifests.append(SkillManifest.from_toml(manifest_path))
    return manifests


def _discover_entry_points() -> list[SkillManifest]:
    manifests = []
    for entry_point in entry_points(group=_ENTRY_POINT_GROUP):
        loaded = entry_point.load()
        manifest = loaded() if callable(loaded) else loaded
        if not isinstance(manifest, SkillManifest):
            raise TypeError(
                f"entry point {entry_point.name!r} in group {_ENTRY_POINT_GROUP!r} must "
                f"resolve to a SkillManifest, got {type(manifest).__name__}"
            )
        manifests.append(manifest)
    return manifests
