"""Folder monitoring: turn filesystem changes into event-bus events.

A :class:`FolderWatcher` runs a ``watchdog`` observer over one or more
directories and republishes each change as a ``fs.<event>`` event on the app
event bus (``fs.created``, ``fs.modified``, ``fs.deleted``, ``fs.moved``).
Rules can then trigger on those events -- e.g. "when a PDF lands in ~/Inbox,
index it and move it to ~/Documents".

The translation from a watchdog event to a bus event lives in
:class:`_BusEventHandler`, which is a plain object with no threads, so it can
be unit-tested by handing it fake events directly -- no real filesystem
waiting, no flaky sleeps. The watchdog ``Observer`` thread is only started
when :meth:`FolderWatcher.start` is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.core.events import EventBus
from nexus.core.logging import get_logger

__all__ = ["FolderWatcher"]

_logger = get_logger("automation.watcher")


class _BusEventHandler:
    """Translates watchdog filesystem events into event-bus publishes.

    Implemented as a duck-typed handler (the methods watchdog calls) rather
    than subclassing ``FileSystemEventHandler`` at import time, so this module
    imports cleanly and is testable even in an environment where watchdog is
    absent; the real base class is only needed when an observer is started.
    """

    def __init__(self, events: EventBus) -> None:
        self._events = events

    def dispatch(self, event: Any) -> None:
        """Publish a bus event for a watchdog filesystem *event*."""
        if getattr(event, "is_directory", False):
            return
        topic = f"fs.{event.event_type}"
        payload: dict[str, Any] = {"path": str(getattr(event, "src_path", ""))}
        dest = getattr(event, "dest_path", None)
        if dest:
            payload["dest_path"] = str(dest)
        self._events.publish(topic, **payload)


class FolderWatcher:
    """Watches directories and republishes changes onto the event bus."""

    def __init__(self, events: EventBus) -> None:
        self._events = events
        self._handler = _BusEventHandler(events)
        # watchdog's Observer is a runtime factory, not a class usable as a
        # type, so this is typed as Any -- the object is only ever driven
        # through start()/stop() here.
        self._observer: Any = None
        self._paths: list[tuple[Path, bool]] = []

    def watch(self, path: Path | str, *, recursive: bool = True) -> None:
        """Register *path* to be watched once :meth:`start` is called."""
        self._paths.append((Path(path), recursive))

    def start(self) -> None:
        """Start observing every registered path on a background thread.

        Imports watchdog lazily so the rest of the automation module works
        without it installed; only starting an observer requires it.
        """
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        handler = self._handler

        class _Adapter(FileSystemEventHandler):  # pragma: no cover - thin glue
            def on_any_event(self, event: Any) -> None:
                handler.dispatch(event)

        observer = Observer()
        adapter = _Adapter()
        for path, recursive in self._paths:
            if path.is_dir():
                observer.schedule(adapter, str(path), recursive=recursive)
            else:
                _logger.warning("skipping watch on non-directory %s", path)
        observer.start()
        self._observer = observer
        _logger.info("watching %d path(s)", len(self._paths))

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the observer thread, if running."""
        observer = self._observer
        if observer is not None:
            observer.stop()
            observer.join(timeout=timeout)
            self._observer = None
