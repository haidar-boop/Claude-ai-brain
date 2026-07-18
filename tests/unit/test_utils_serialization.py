"""Tests for aiforge.utils.serialization."""

from __future__ import annotations

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
