"""A minimal dependency-injection container with optional singleton caching.

Not a full DI framework -- just enough to assemble the engine's
collaborators (provider registry, skill resolver, event bus, ...) from
factories rather than hardcoded concrete classes, so each collaborator stays
independently constructible and swappable in tests. Registrations are keyed
by a typed :class:`Key` so :meth:`Container.resolve` returns the correct
static type instead of ``object``.

The container stores every registration in ``dict[Key[object], ...]``
fields (type-erased at storage time) while the public methods stay generic
over ``Key[T]``. That erasure is why several lines below need a narrow
``# type: ignore`` -- it's the standard, expected cost of a heterogeneous
typed registry in Python's invariant-generics type system, not a sign of a
real type-safety hole: every erasure is re-established by the ``Key[T]``
type on the calling method's signature.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")

__all__ = ["Container", "Key"]


class Key(Generic[T]):
    """A typed, hashable token identifying a registration.

    Two distinct :class:`Key` instances never compare equal, even with the
    same *label* -- the label is for debugging/repr only, not identity.
    """

    __slots__ = ("label",)

    def __init__(self, label: str) -> None:
        self.label = label

    def __repr__(self) -> str:
        return f"Key({self.label!r})"


class Container:
    """Registers factories keyed by :class:`Key` and resolves them, caching singletons.

    Thread-safe: singleton resolution is guarded by a lock so concurrent
    first-use :meth:`resolve` calls for the same key share one built
    instance, as ``singleton=True`` promises.
    """

    def __init__(self) -> None:
        self._factories: dict[Key[object], Callable[[], object]] = {}
        self._singleton: dict[Key[object], bool] = {}
        self._instances: dict[Key[object], object] = {}
        self._lock = threading.Lock()

    def register(self, key: Key[T], factory: Callable[[], T], *, singleton: bool = True) -> None:
        """Register *factory* under *key*, replacing any prior registration."""
        with self._lock:
            self._factories[key] = factory  # type: ignore[index]
            self._singleton[key] = singleton  # type: ignore[index]
            self._instances.pop(key, None)  # type: ignore[arg-type]

    def register_instance(self, key: Key[T], instance: T) -> None:
        """Register a pre-built *instance* directly under *key* (always a singleton)."""
        with self._lock:
            self._factories[key] = lambda: instance  # type: ignore[index]
            self._singleton[key] = True  # type: ignore[index]
            self._instances[key] = instance  # type: ignore[index]

    def resolve(self, key: Key[T]) -> T:
        """Return the instance registered under *key*, building it on first use."""
        with self._lock:
            if key in self._instances:
                return self._instances[key]  # type: ignore[index, return-value]
            try:
                factory = self._factories[key]  # type: ignore[index]
            except KeyError:
                raise KeyError(f"no factory registered for {key!r}") from None
            instance = factory()
            if self._singleton.get(key, True):  # type: ignore[arg-type]
                self._instances[key] = instance  # type: ignore[index]
            return instance  # type: ignore[return-value]

    def has(self, key: Key[object]) -> bool:
        """Return whether *key* has a registered factory."""
        return key in self._factories

    def reset(self, key: Key[object] | None = None) -> None:
        """Drop cached singleton instance(s) so the next resolve() rebuilds them.

        With no argument, clears every cached instance.
        """
        with self._lock:
            if key is None:
                self._instances.clear()
            else:
                self._instances.pop(key, None)
