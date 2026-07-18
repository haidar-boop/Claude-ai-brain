"""Automation: a scheduler, a rule engine, and folder monitoring.

These three pieces let Nexus do things on its own:
- :mod:`nexus.automation.scheduler` runs callbacks on interval or daily-time
  schedules on a background thread.
- :mod:`nexus.automation.rules` reacts to events on the app's event bus,
  running configured actions when a rule's trigger fires and its conditions
  hold -- this is the "workflow builder" runtime.
- :mod:`nexus.automation.watcher` turns filesystem changes into events, so a
  rule can act when a file lands in a watched folder.

The scheduling and rule-evaluation *logic* is written as pure, injectable
functions so it can be unit-tested deterministically without waiting on real
threads or wall-clock time; the threads are thin drivers over that logic.
"""
