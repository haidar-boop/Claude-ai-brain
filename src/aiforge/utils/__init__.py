"""Internal utilities: caching, serialization, async helpers, indexing, lazy imports.

Kept import-light on purpose: submodules are imported individually by the
code that needs them, not re-exported here, so ``import aiforge.utils`` never
pulls in orjson, asyncio helpers, etc. that a given caller doesn't need.
"""
