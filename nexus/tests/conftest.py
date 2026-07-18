"""Shared test configuration.

Force Qt to use the ``offscreen`` platform plugin before PySide6 is imported
anywhere, so the GUI widget tests run in a headless container (CI, this
build environment) without a real display server. Setting it here -- at
collection time, before pytest-qt or any test imports QtGui -- is what makes
``import PySide6`` succeed without an X server or Wayland session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def app_ctx() -> Iterator[object]:
    """An in-memory :class:`AppContext` with every service wired, per test.

    Imported lazily inside the fixture so non-UI test modules that never
    request it don't pay the import cost.
    """
    from nexus.app_context import AppContext

    ctx = AppContext.in_memory()
    try:
        yield ctx
    finally:
        ctx.close()
