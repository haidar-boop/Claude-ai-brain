"""Tests for aiforge.utils.serialization."""

from __future__ import annotations

import pytest

from aiforge.utils import serialization


def test_dumps_and_loads_roundtrip() -> None:
    obj = {"b": 2, "a": 1, "list": [1, 2, 3], "nested": {"x": True, "y": None}}
    text = serialization.dumps(obj)
    assert serialization.loads(text) == obj


def test_dumps_bytes_and_loads_roundtrip() -> None:
    obj = {"a": 1}
    data = serialization.dumps_bytes(obj)
    assert isinstance(data, bytes)
    assert serialization.loads(data) == obj


def test_dumps_sort_keys() -> None:
    obj = {"b": 1, "a": 2}
    text = serialization.dumps(obj, sort_keys=True)
    assert text.index('"a"') < text.index('"b"')


def test_has_orjson_flag_matches_import() -> None:
    try:
        import orjson  # noqa: F401

        expected = True
    except ImportError:
        expected = False
    assert serialization.HAS_ORJSON is expected


def test_dumps_serializes_dates_on_current_path() -> None:
    # Regression: TOML parsing produces real date/datetime objects (e.g. in
    # provider `extra` config); the orjson path serialized them natively
    # while the stdlib fallback raised TypeError, so `aiforge config show`
    # crashed only for installs without the `fast` extra. Both paths must
    # produce isoformat strings.
    import datetime

    obj = {
        "released": datetime.date(2024, 1, 1),
        "at": datetime.datetime(2024, 1, 1, 12, 30, 0),
        "t": datetime.time(12, 30, 0),
    }
    parsed = serialization.loads(serialization.dumps(obj))
    assert parsed["released"] == "2024-01-01"
    assert parsed["at"].startswith("2024-01-01T12:30:00")
    assert parsed["t"].startswith("12:30:00")


def test_stdlib_fallback_serializes_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the stdlib branch even when orjson is installed (as in CI) --
    # without this, the fallback's default=_json_default wiring is never
    # executed and removing it would leave the suite green.
    import datetime

    monkeypatch.setattr(serialization, "_orjson_mod", None)
    obj = {"released": datetime.date(2024, 1, 1)}
    assert serialization.loads(serialization.dumps(obj)) == {"released": "2024-01-01"}
    assert serialization.loads(serialization.dumps_bytes(obj)) == {"released": "2024-01-01"}


def test_stdlib_fallback_rejects_nan_instead_of_emitting_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # allow_nan=False: the fallback must never emit the spec-invalid NaN /
    # Infinity tokens that a strict parser (including orjson) rejects.
    monkeypatch.setattr(serialization, "_orjson_mod", None)
    with pytest.raises(ValueError, match=r"[Oo]ut of range"):
        serialization.dumps({"temperature": float("nan")})


def test_stdlib_fallback_json_default_rejects_unknown_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(serialization, "_orjson_mod", None)
    with pytest.raises(TypeError, match="not JSON serializable"):
        serialization.dumps({"x": object()})
