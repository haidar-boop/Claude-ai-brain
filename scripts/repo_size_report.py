"""Report tracked repository size by directory and extension.

Uses ``git ls-files`` as the source of truth for "what's tracked" -- the
same criterion GitHub storage actually bills against -- rather than walking
the filesystem, which would also count .gitignore'd build artifacts.

Run with: python scripts/repo_size_report.py
"""

from __future__ import annotations

import subprocess  # nosec B404 -- fixed argv below, no untrusted input
import sys
from collections import defaultdict
from pathlib import Path

_LARGE_FILE_THRESHOLD_BYTES = 50_000


def _tracked_files() -> list[Path]:
    # Fixed argv ("git ls-files"), no untrusted input.
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"], check=True, capture_output=True, text=True, timeout=30
    )
    return [Path(line) for line in result.stdout.splitlines() if line]


def main() -> int:
    files = _tracked_files()
    by_dir: dict[str, int] = defaultdict(int)
    by_ext: dict[str, int] = defaultdict(int)
    total = 0
    large_files: list[tuple[int, Path]] = []

    for path in files:
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        top = path.parts[0] if len(path.parts) > 1 else "."
        by_dir[top] += size
        by_ext[path.suffix or "(no extension)"] += size
        if size > _LARGE_FILE_THRESHOLD_BYTES:
            large_files.append((size, path))

    print(f"Tracked files: {len(files)}")
    print(f"Total tracked size: {total / 1024:.1f} KiB\n")

    print("By top-level directory:")
    for name, size in sorted(by_dir.items(), key=lambda kv: -kv[1]):
        print(f"  {name:20s} {size / 1024:8.1f} KiB")

    print("\nBy extension:")
    for ext, size in sorted(by_ext.items(), key=lambda kv: -kv[1]):
        print(f"  {ext:20s} {size / 1024:8.1f} KiB")

    if large_files:
        threshold_kb = _LARGE_FILE_THRESHOLD_BYTES / 1000
        print(f"\nFiles over {threshold_kb:.0f} KB (review for necessity):")
        for size, path in sorted(large_files, reverse=True):
            print(f"  {size / 1024:8.1f} KiB  {path}")
    else:
        print(f"\nNo tracked file exceeds {_LARGE_FILE_THRESHOLD_BYTES / 1000:.0f} KB.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
