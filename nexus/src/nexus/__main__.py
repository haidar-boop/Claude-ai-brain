"""Allow ``python -m nexus`` as an alias for the ``nexus`` console script."""

import sys

from nexus.cli import main

if __name__ == "__main__":
    sys.exit(main())
