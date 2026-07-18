"""Tests for aiforge.utils.lazy."""

from __future__ import annotations

import sys
import types

import pytest

from aiforge.utils.lazy import lazy_dir, lazy_getattr


def test_lazy_getattr_resolves_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pkg = types.ModuleType("fake_lazy_pkg")
    fake_target = types.ModuleType("fake_lazy_pkg._impl")
    fake_target.Widget = object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_lazy_pkg", fake_pkg)
    monkeypatch.setitem(sys.modules, "fake_lazy_pkg._impl", fake_target)
    fake_pkg.__getattr__ = lazy_getattr(  # type: ignore[attr-defined]
        "fake_lazy_pkg", {"Widget": ("fake_lazy_pkg._impl", "Widget")}
    )

    resolved = fake_pkg.Widget  # triggers module-level __getattr__ per PEP 562
    assert resolved is fake_target.Widget
    # Second access should hit the now-cached plain attribute, not __getattr__.
    assert fake_pkg.__dict__["Widget"] is fake_target.Widget


def test_lazy_getattr_raises_attribute_error_for_unknown_name() -> None:
    getattr_fn = lazy_getattr("some.pkg", {})
    with pytest.raises(AttributeError, match=r"some\.pkg"):
        getattr_fn("missing")


def test_lazy_dir_returns_sorted_names() -> None:
    dir_fn = lazy_dir(["b", "a", "c"])
    assert dir_fn() == ["a", "b", "c"]
