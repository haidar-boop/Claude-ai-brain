"""Benchmark: inverted-index skill resolution vs. a naive linear rescan baseline.

"Optimized" = ``SkillResolver.resolve()``, backed by ``SkillRegistry``'s
``InvertedIndex``: candidate lookup touches only skills that share a token
with the prompt, regardless of how many skills are registered in total.

"Naive baseline" = a linear scan over every registered skill, recomputing
the full score from scratch for every resolution -- what resolution would
cost without an index. Implemented locally in this file (not a prior
version of aiforge) using the same scoring weights as
``aiforge.skills.resolver``, for an honest, like-for-like comparison against
the same 10 built-in skills. ``test_indexed_and_naive_resolution_agree_on_top_match``
guards that the two actually agree, so the comparison is measuring the same
work done two different ways, not two different algorithms.

At only 10 built-in skills the absolute difference is small (both are
sub-millisecond); the point of the index is asymptotic -- O(matching tokens)
instead of O(registered skills) -- which matters once a project registers
many custom skills via the plugin entry point.

Run with: pytest benchmarks/bench_skill_loading.py --benchmark-only
"""

from __future__ import annotations

from aiforge.skills.loader import discover_skills
from aiforge.skills.manifest import SkillManifest
from aiforge.skills.registry import SkillRegistry
from aiforge.skills.resolver import SkillResolver

_PROMPT = "Write a Python function using FastAPI and pytest that queries SQL."


def _build_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register_all(discover_skills())
    return registry


def _naive_linear_score(manifests: list[SkillManifest], prompt: str) -> list[SkillManifest]:
    """What resolution would cost with a linear scan instead of an inverted index."""
    tokens = {t.lower() for t in prompt.replace(".", " ").split()}
    scored = []
    for manifest in manifests:
        score = (
            3 * len(tokens & {v.lower() for v in manifest.languages})
            + 2 * len(tokens & {v.lower() for v in manifest.frameworks})
            + 2 * len(tokens & {v.lower() for v in manifest.libraries})
            + 1 * len(tokens & {v.lower() for v in manifest.keywords})
        )
        if score > 0:
            scored.append((score, manifest))
    scored.sort(key=lambda pair: (-pair[0], -pair[1].priority, pair[1].name))
    return [manifest for _, manifest in scored]


def test_bench_discover_skills_cold(benchmark) -> None:
    benchmark(discover_skills)


def test_bench_optimized_indexed_resolution(benchmark) -> None:
    registry = _build_registry()
    resolver = SkillResolver(registry)
    benchmark(resolver.resolve, prompt=_PROMPT)


def test_bench_naive_linear_scan_resolution(benchmark) -> None:
    manifests = discover_skills()
    benchmark(_naive_linear_score, manifests, _PROMPT)


def test_indexed_and_naive_resolution_agree_on_top_match() -> None:
    registry = _build_registry()
    resolver = SkillResolver(registry)
    manifests = discover_skills()
    indexed_top = resolver.resolve(prompt=_PROMPT).selected[0].name
    naive_top = _naive_linear_score(manifests, _PROMPT)[0].name
    assert indexed_top == naive_top
