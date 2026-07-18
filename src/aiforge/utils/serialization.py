"""JSON serialization with automatic orjson acceleration when available.

Falls back to the standard library's ``json`` module, so everything here
works with zero third-party dependencies -- just slower. Install the ``fast``
extra (``pip install aiforge[fast]``) to pull in orjson.
"""

from __future__ import annotations

import json
from typing import Any

try:
    import orjson as _orjson_mod
except ImportError:
    _orjson_mod = None  # type: ignore[assignment]

__all__ = ["HAS_ORJSON", "dumps", "dumps_bytes", "loads"]

HAS_ORJSON = _orjson_mod is not None


def dumps(obj: Any, *, sort_keys: bool = False) -> str:
    """Serialize *obj* to a compact JSON string."""
    if _orjson_mod is not None:
        option = _orjson_mod.OPT_SORT_KEYS if sort_keys else 0
        return _orjson_mod.dumps(obj, option=option).decode("utf-8")
    return json.dumps(obj, sort_keys=sort_keys, separators=(",", ":"))


def dumps_bytes(obj: Any, *, sort_keys: bool = False) -> bytes:
    """Serialize *obj* to compact JSON bytes, skipping an encode round trip."""
    if _orjson_mod is not None:
        option = _orjson_mod.OPT_SORT_KEYS if sort_keys else 0
        return _orjson_mod.dumps(obj, option=option)
    return json.dumps(obj, sort_keys=sort_keys, separators=(",", ":")).encode("utf-8")


def loads(data: str | bytes) -> Any:
    """Deserialize JSON *data*."""
    if _orjson_mod is not None:
        return _orjson_mod.loads(data)
    return json.loads(data)
