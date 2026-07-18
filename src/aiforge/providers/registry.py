"""Provider discovery and registration.

Providers register either via the ``aiforge.providers`` entry-point group
(installable packages, including AIForge's own built-in providers) or via a
direct :meth:`ProviderRegistry.register_factory` call -- no core file needs
to change to add a new provider.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from importlib.metadata import entry_points

from aiforge.core.errors import ProviderNotFoundError
from aiforge.core.registry import Registry
from aiforge.providers.base import Provider

__all__ = ["ProviderRegistry"]

_ENTRY_POINT_GROUP = "aiforge.providers"


class ProviderRegistry:
    """Lazily-instantiating registry of :class:`~aiforge.providers.base.Provider` factories.

    Thread-safe: the zero-argument instance cache is guarded by a lock, so
    concurrent first-use callers (e.g. requests racing in via
    ``ThreadingHTTPServer`` or ``Engine.arun``'s thread offload) share one
    constructed instance instead of each building their own.
    """

    def __init__(self) -> None:
        self._factories: Registry[Callable[..., Provider]] = Registry(kind="provider")
        self._instances: dict[str, Provider] = {}
        self._lock = threading.Lock()

    def register_factory(
        self, name: str, factory: Callable[..., Provider], *, replace: bool = False
    ) -> None:
        """Register a keyword-args-only *factory* under *name*."""
        with self._lock:
            self._factories.register(name, factory, replace=replace)
            self._instances.pop(name, None)

    def discover_entry_points(self) -> None:
        """Register every provider factory advertised via the entry-point group.

        Safe to call multiple times; an already-registered name is left
        alone (call :meth:`register_factory` with ``replace=True`` to
        override explicitly).
        """
        with self._lock:
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
        # Construction happens under the lock deliberately: the singleton
        # guarantee ("one shared instance per name") matters more than
        # first-call construction parallelism, and providers build quickly.
        with self._lock:
            cached = self._instances.get(name)
            if cached is not None:
                return cached
            instance = self._build(name, {})
            self._instances[name] = instance
            return instance

    def require(self, name: str) -> Provider:
        """Return the cached, zero-argument instance for *name*."""
        return self.get_or_create(name)

    def configure(self, name: str, **candidate_kwargs: object) -> Provider | None:
        """Build and cache an instance for *name* from *candidate_kwargs*.

        Only the keyword arguments *name*'s factory signature actually
        declares are passed (via introspection), or all of them if the
        factory accepts ``**kwargs`` -- callers can safely pass a superset
        of possible config fields across differently-shaped provider
        factories (e.g. a fake or third-party provider that doesn't accept
        ``max_retries``/``timeout``). Subsequent zero-argument
        :meth:`require`/:meth:`get_or_create` calls for *name* return the
        resulting instance.

        Returns ``None`` (and registers nothing, leaving the provider's own
        defaults in effect) if none of *candidate_kwargs* apply. Raises
        :class:`~aiforge.core.errors.ProviderNotFoundError` if *name* isn't
        a registered factory.
        """
        with self._lock:
            try:
                factory = self._factories.require(name)
            except KeyError:
                raise ProviderNotFoundError(name, available=tuple(self.names())) from None
            params = inspect.signature(factory).parameters
            accepts_var_keyword = any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
            kwargs = (
                dict(candidate_kwargs)
                if accepts_var_keyword
                else {k: v for k, v in candidate_kwargs.items() if k in params}
            )
            if not kwargs:
                return None
            instance = factory(**kwargs)
            self._instances[name] = instance
            return instance

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
