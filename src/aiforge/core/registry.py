"""A generic named-item registry: register/get/list/unregister by string name.

Used as the storage primitive underneath the domain-specific provider and
skill registries, which layer typed not-found errors and discovery logic on
top of this generic, independently-testable core.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

T = TypeVar("T")

__all__ = ["Registry"]


class Registry(Generic[T]):
    """A simple name -> item registry with duplicate-registration protection."""

    def __init__(self, *, kind: str = "item") -> None:
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str, item: T, *, replace: bool = False) -> None:
        """Register *item* under *name*.

        Raises :class:`ValueError` if *name* is already registered and
        *replace* is False.
        """
        if not replace and name in self._items:
            raise ValueError(f"{self._kind} {name!r} is already registered")
        self._items[name] = item

    def get(self, name: str) -> T | None:
        """Return the item registered under *name*, or ``None`` if absent."""
        return self._items.get(name)

    def require(self, name: str) -> T:
        """Return the item registered under *name*.

        Raises :class:`KeyError` (listing available names) if absent.
        """
        try:
            return self._items[name]
        except KeyError:
            available = ", ".join(sorted(self._items)) or "<none>"
            raise KeyError(
                f"no {self._kind} registered as {name!r} (available: {available})"
            ) from None

    def unregister(self, name: str) -> None:
        """Remove *name* from the registry, if present. No-op if absent."""
        self._items.pop(name, None)

    def names(self) -> list[str]:
        """Return every registered name, sorted."""
        return sorted(self._items)

    def items(self) -> Iterator[tuple[str, T]]:
        """Iterate over (name, item) pairs."""
        yield from self._items.items()

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())
