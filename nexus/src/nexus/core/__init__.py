"""Application kernel: configuration, logging, events, errors, and paths.

Everything in this package is UI-free and framework-free so every other
layer (services, database, automation, API, and the Qt shell itself) can
depend on it without dragging in heavyweight imports.
"""
