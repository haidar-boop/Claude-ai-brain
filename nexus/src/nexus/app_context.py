"""The application composition root: build every service from configuration.

:class:`AppContext` is the single place that wires the whole application
together -- it opens the database, constructs each domain service with its
dependencies injected, and exposes them as attributes. The UI, the CLI, and
the REST API all build an :class:`AppContext` and read services off it,
rather than each constructing databases and services themselves. This keeps
construction in one auditable place and makes it trivial to stand up the
entire backend (against a temp directory, or in memory) in a test.

Nothing here imports Qt: the context is the UI-free backend, so the API and
CLI use it without dragging in a GUI toolkit.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from nexus.automation.actions import default_action_registry
from nexus.automation.rules import RuleEngine
from nexus.core.config import AppConfig, load_config
from nexus.core.events import EventBus
from nexus.core.logging import configure, get_logger
from nexus.core.paths import AppPaths
from nexus.db.database import Database
from nexus.services.ai import AIService
from nexus.services.automation import AutomationService
from nexus.services.dashboard import DashboardService
from nexus.services.files import FilesService
from nexus.services.notes import NotesService
from nexus.services.tasks import TasksService

__all__ = ["AppContext"]

_logger = get_logger("app")


class AppContext:
    """Owns the database and every domain service for one running app."""

    def __init__(self, config: AppConfig, paths: AppPaths, database: Database) -> None:
        self.config = config
        self.paths = paths
        self.database = database
        self.events = EventBus()

        self.notes = NotesService(database, self.events)
        self.tasks = TasksService(database, self.events)
        self.files = FilesService(database, self.events)
        self.ai = AIService(database, config.ai, self.events)
        self.automation = AutomationService(database, self.events)
        self.dashboard = DashboardService(database, self.events)

        # The rule engine makes stored workflow rules live: it subscribes to
        # the event bus and runs each enabled rule's actions when its trigger
        # fires. Loading here means automation is on as soon as the app starts.
        # The action registry is exposed so plugins can register new actions.
        self.automation_actions = default_action_registry(self.events)
        self.automation_engine = RuleEngine(self.events, self.automation_actions)
        loaded = self.automation.load_into(self.automation_engine)
        _logger.info("application context ready (%d automation rule(s) loaded)", loaded)

    def reload_automation(self) -> int:
        """Re-load stored rules into the running engine; return the count.

        Call after creating, toggling, or deleting rules so the live engine
        matches what is persisted.
        """
        self.automation_engine.clear()
        return self.automation.load_into(self.automation_engine)

    @classmethod
    def create(
        cls,
        *,
        data_dir: Path | str | None = None,
        config_path: Path | str | None = None,
    ) -> AppContext:
        """Build a fully-wired context: config, paths, logging, database, services.

        This is the normal entry point. *data_dir* overrides where Nexus
        stores its database, backups, and logs (defaulting to the platform
        data directory); *config_path* points at a ``config.yaml``. When
        *config_path* is omitted, a ``config.yaml`` sitting in the data
        directory is picked up automatically, so dropping a config file next
        to the database is all it takes to configure an install.
        """
        paths = AppPaths.create(data_dir)
        if config_path is None and paths.config.is_file():
            config_path = paths.config
        config = load_config(config_path)
        configure(config.logging, log_dir=paths.logs)
        database = Database.open(
            paths.database,
            config=config.database,
            key_path=paths.encryption_key,
            backup_dir=paths.backups,
        )
        return cls(config, paths, database)

    @classmethod
    def in_memory(cls, config: AppConfig | None = None) -> AppContext:
        """Build a context backed by an in-memory database (for tests/demos)."""
        cfg = config or AppConfig()
        paths = AppPaths(base=Path("."))
        database = Database.in_memory()
        return cls(cfg, paths, database)

    def close(self) -> None:
        """Dispose of the database connection pool."""
        self.database.dispose()

    def __enter__(self) -> AppContext:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
