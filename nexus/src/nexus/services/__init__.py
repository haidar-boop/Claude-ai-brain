"""Domain services: the UI-free business logic of each Nexus module.

Every service takes its collaborators by constructor injection (a
:class:`~nexus.db.database.Database` and usually the
:class:`~nexus.core.events.EventBus`) and exposes plain methods that return
frozen data-transfer objects, never live ORM instances. That boundary keeps
three things true at once: the UI can't accidentally depend on an open
session (no ``DetachedInstanceError`` surprises), the REST API can serialize
returns directly, and each service is trivially unit-testable against an
in-memory database with no Qt involved.
"""
