"""A minimal inverted index for keyword -> item-id lookup.

Used by the skill registry to resolve candidate skills for a task without a
linear scan over every registered skill.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

__all__ = ["InvertedIndex"]


class InvertedIndex:
    """Maps normalized tokens to the set of item ids that declared them."""

    def __init__(self) -> None:
        self._index: dict[str, set[str]] = defaultdict(set)
        self._items: dict[str, frozenset[str]] = {}

    def add(self, item_id: str, tokens: Iterable[str]) -> None:
        """Index *item_id* under each of *tokens* (case-insensitively).

        Replaces any tokens previously indexed for the same *item_id*.
        """
        normalized = frozenset(_normalize(t) for t in tokens if t)
        self.remove(item_id)
        self._items[item_id] = normalized
        for token in normalized:
            self._index[token].add(item_id)

    def remove(self, item_id: str) -> None:
        """Remove *item_id* from the index, if present."""
        tokens = self._items.pop(item_id, None)
        if tokens is None:
            return
        for token in tokens:
            bucket = self._index.get(token)
            if bucket is None:
                continue
            bucket.discard(item_id)
            if not bucket:
                del self._index[token]

    def query(self, tokens: Iterable[str]) -> set[str]:
        """Return the union of item ids indexed under any of *tokens*."""
        result: set[str] = set()
        for token in tokens:
            result |= self._index.get(_normalize(token), set())
        return result

    def query_all(self, tokens: Iterable[str]) -> set[str]:
        """Return the intersection of item ids indexed under every one of *tokens*."""
        normalized = [_normalize(t) for t in tokens if t]
        if not normalized:
            return set()
        buckets = [self._index.get(t, set()) for t in normalized]
        result = set(buckets[0])
        for bucket in buckets[1:]:
            result &= bucket
        return result

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._items


def _normalize(token: str) -> str:
    return token.strip().lower()
