"""Dockable module panels for the Nexus main window.

Each panel is a ``QWidget`` that takes an
:class:`~nexus.app_context.AppContext` and drives exactly one module's
service. Panels never touch the database directly -- they call service
methods and render the returned DTOs -- so all the business logic stays
tested and UI-free, and a panel is a thin, replaceable view.
"""
