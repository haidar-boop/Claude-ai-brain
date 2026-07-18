"""Skill registry: enable/disable policy and lookup, indexed for fast task matching."""

from __future__ import annotations

import dataclasses

from aiforge.core.errors import SkillNotFoundError
from aiforge.core.registry import Registry
from aiforge.skills.manifest import SkillManifest
from aiforge.utils.indexing import InvertedIndex

__all__ = ["SkillRegistry"]


class SkillRegistry:
    """Holds discovered skills, applies enable/disable policy, and indexes them for lookup."""

    def __init__(self) -> None:
        self._registry: Registry[SkillManifest] = Registry(kind="skill")
        self._index = InvertedIndex()

    def register(self, manifest: SkillManifest, *, replace: bool = False) -> None:
        """Register *manifest*, indexing its languages/frameworks/keywords for lookup."""
        self._registry.register(manifest.name, manifest, replace=replace)
        tokens = (*manifest.languages, *manifest.frameworks, *manifest.keywords, manifest.name)
        self._index.add(manifest.name, tokens)

    def register_all(self, manifests: list[SkillManifest], *, replace: bool = False) -> None:
        """Register every manifest in *manifests*."""
        for manifest in manifests:
            self.register(manifest, replace=replace)

    def apply_policy(self, *, enabled: tuple[str, ...] | None, disabled: tuple[str, ...]) -> None:
        """Apply config-driven enable/disable policy across all registered skills.

        *enabled* of ``None`` leaves each skill's own ``enabled`` flag as
        the manifest declared it; an explicit tuple restricts to exactly
        those names. Names in *disabled* are always turned off, regardless
        of *enabled*.
        """
        for name in self.names():
            manifest = self.require(name)
            is_enabled = name in enabled if enabled is not None else manifest.enabled
            if name in disabled:
                is_enabled = False
            if is_enabled != manifest.enabled:
                updated = dataclasses.replace(manifest, enabled=is_enabled)
                self._registry.register(name, updated, replace=True)

    def require(self, name: str) -> SkillManifest:
        """Return the manifest registered under *name*, raising :class:`SkillNotFoundError`."""
        try:
            return self._registry.require(name)
        except KeyError:
            raise SkillNotFoundError(name, available=tuple(self.names())) from None

    def get(self, name: str) -> SkillManifest | None:
        return self._registry.get(name)

    def names(self, *, enabled_only: bool = False) -> list[str]:
        if not enabled_only:
            return self._registry.names()
        return sorted(name for name, manifest in self._registry.items() if manifest.enabled)

    def candidates(self, tokens: list[str]) -> list[SkillManifest]:
        """Return enabled skills indexed under any of *tokens*, via the inverted index."""
        ids = self._index.query(tokens)
        result = []
        for name in sorted(ids):
            manifest = self._registry.get(name)
            if manifest is not None and manifest.enabled:
                result.append(manifest)
        return result

    def all_enabled(self) -> list[SkillManifest]:
        return [manifest for _, manifest in self._registry.items() if manifest.enabled]
