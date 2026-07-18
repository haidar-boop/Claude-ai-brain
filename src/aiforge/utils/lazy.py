"""PEP 562 lazy-attribute helpers.

Used by :mod:`aiforge` (and any subpackage that wants the same trick) to
expose a wide public API without paying the import cost of every submodule
just because the package itself was imported. Each name is imported at most
once and then cached directly on the defining module.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterable, Mapping

__all__ = ["lazy_dir", "lazy_getattr"]


def lazy_getattr(package: str, mapping: Mapping[str, tuple[str, str]]) -> Callable[[str], object]:
    """Build a module-level ``__getattr__`` for lazy re-exports.

    Args:
        package: ``__name__`` of the module defining ``__getattr__`` (that
            module's namespace is where resolved attributes get cached).
        mapping: public attribute name -> ``(module_name, attr_name)``.

    Returns:
        A function suitable for assignment to ``__getattr__`` in the caller.
    """

    def _getattr(name: str) -> object:
        try:
            module_name, attr_name = mapping[name]
        except KeyError:
            raise AttributeError(f"module {package!r} has no attribute {name!r}") from None
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
        sys.modules[package].__dict__[name] = value
        return value

    return _getattr


def lazy_dir(names: Iterable[str]) -> Callable[[], list[str]]:
    """Build a module-level ``__dir__`` that reports the lazily-exported names."""
    sorted_names = sorted(names)

    def _dir() -> list[str]:
        return list(sorted_names)

    return _dir
