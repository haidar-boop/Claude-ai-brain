"""Provider discovery and registration.

Providers register either via the ``aiforge.providers`` entry-point group
(installable packages, including AIForge's own built-in providers) or via a
direct :meth:`ProviderRegistry.register_factory` call -- no core file needs
to change to add a new provider.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points

from aiforge.core.errors import ProviderNotFoundError
from aiforge.core.registry import Registry
from aiforge.providers.base import Provider

__all__ = ["ProviderRegistry"]

_ENTRY_POINT_GROUP = "aiforge.providers"


class ProviderRegistry:
    """Lazily-instantiating registry of :class:`~aiforge.providers.base.Provider` factories."""

    def __init__(self) -> None:
        self._factories: Registry[Callable[..., Provider]] = Registry(kind="provider")
        self._instances: dict[str, Provider] = {}

    def register_factory(
        self, name: str, factory: Callable[..., Provider], *, replace: bool = False
    ) -> None:
        """Register a keyword-args-only *factory* under *name*."""
        self._factories.register(name, factory, replace=replace)
        self._instances.pop(name, None)

    def discover_entry_points(self) -> None:
        """Register every provider factory advertised via the entry-point group.

        Safe to call multiple times; an already-registered name is left
        alone (call :meth:`register_factory` with ``replace=True`` to
        override explicitly).
        """
        for entry_point in entry_points(group=_ENTRY_POINT_GROUP):
            if entry_point.name in self._factories:
                continue
            self._factories.register(entry_point.name, entry_point.load())

    def get_or_create(self, name: str, **kwargs: object) -> Provider:
        """Return the cached instance for *name*, constructing it on first use.

        Passing *kwargs* always builds a fresh, uncached instance -- the
        instance cache only applies to zero-argument default construction.
        """
        if kwargs:
            return self._build(name, kwargs)
        cached = self._instances.get(name)
        if cached is not None:
            return cached
        instance = self._build(name, {})
        self._instances[name] = instance
        return instance

    def require(self, name: str) -> Provider:
        """Return the cached, zero-argument instance for *name*."""
        return self.get_or_create(name)

    def _build(self, name: str, kwargs: dict[str, object]) -> Provider:
        try:
            factory = self._factories.require(name)
        except KeyError:
            raise ProviderNotFoundError(name, available=tuple(self.names())) from None
        return factory(**kwargs)

    def names(self) -> list[str]:
        """Return every registered provider name, sorted."""
        return self._factories.names()

    def __contains__(self, name: str) -> bool:
        return name in self._factories
