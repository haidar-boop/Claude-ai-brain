"""The PySide6 desktop UI: main window, dockable panels, themes, dialogs.

Everything here is presentation: panels read from and call the services on
an :class:`~nexus.app_context.AppContext`, and never touch the database or
business logic directly. Importing this package pulls in PySide6, so the
CLI and API (which don't need a GUI) import the specific services they use
instead of importing :mod:`nexus.ui`.
"""
