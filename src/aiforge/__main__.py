"""Enables ``python -m aiforge`` as an alias for the ``aiforge`` console script."""

from __future__ import annotations

import sys

from aiforge.api.cli import main

if __name__ == "__main__":
    sys.exit(main())
