"""Skill resolution: score, select, resolve conflicts, and compose guidance for a task."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from aiforge.skills.manifest import SkillManifest
from aiforge.skills.registry import SkillRegistry

__all__ = ["ResolvedSkills", "SkillResolver"]

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#._-]*")


@dataclass(frozen=True, slots=True)
class ResolvedSkills:
    """The outcome of resolving skills for a task."""

    selected: tuple[SkillManifest, ...]
    composed_guidance: str | None


class SkillResolver:
    """Selects and composes the skills relevant to a task.

    Explicit skill names always win. Otherwise skills are scored against
    the prompt text and any file hints, and the top matches (by score, then
    manifest priority, then name) are composed together -- this is how
    multiple skills work together and how conflicts (competing skills that
    both score highly) resolve deterministically.
    """

    def __init__(self, registry: SkillRegistry, *, max_skills: int = 3) -> None:
        self._registry = registry
        self.max_skills = max_skills

    def resolve(
        self,
        *,
        explicit: tuple[str, ...] = (),
        prompt: str = "",
        file_hints: tuple[str, ...] = (),
    ) -> ResolvedSkills:
        """Resolve the skills applicable to a task."""
        if explicit:
            requested = [self._registry.require(name) for name in explicit]
            selected = [m for m in requested if m.enabled][: self.max_skills]
        else:
            selected = self._score_and_select(prompt=prompt, file_hints=file_hints)
        return ResolvedSkills(selected=tuple(selected), composed_guidance=self._compose(selected))

    def _score_and_select(self, *, prompt: str, file_hints: tuple[str, ...]) -> list[SkillManifest]:
        tokens = _tokenize(prompt)
        candidates = list(self._registry.candidates(tokens)) if tokens else []
        if file_hints:
            for manifest in self._registry.all_enabled():
                if manifest in candidates:
                    continue
                if _matches_any_glob(file_hints, manifest.file_globs):
                    candidates.append(manifest)
        scored = [
            (score, manifest)
            for manifest in candidates
            if (score := self._score(manifest, tokens, file_hints)) > 0
        ]
        scored.sort(key=lambda pair: (-pair[0], -pair[1].priority, pair[1].name))
        return [manifest for _, manifest in scored[: self.max_skills]]

    def _score(
        self, manifest: SkillManifest, tokens: list[str], file_hints: tuple[str, ...]
    ) -> int:
        token_set = {t.lower() for t in tokens}
        score = 0
        score += 3 * len(token_set & {v.lower() for v in manifest.languages})
        score += 2 * len(token_set & {v.lower() for v in manifest.frameworks})
        score += 2 * len(token_set & {v.lower() for v in manifest.libraries})
        score += 1 * len(token_set & {v.lower() for v in manifest.keywords})
        if _matches_any_glob(file_hints, manifest.file_globs):
            score += 4
        return score

    def _compose(self, selected: list[SkillManifest]) -> str | None:
        if not selected:
            return None
        return "\n\n".join(manifest.prompt_guidance() for manifest in selected)


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _matches_any_glob(hints: tuple[str, ...], globs: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatch(Path(hint).name, glob) or fnmatch.fnmatch(hint, glob)
        for hint in hints
        for glob in globs
    )
