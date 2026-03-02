#!/usr/bin/env python
"""One-time setup: configure git to use .githooks/ as the hooks directory.

Usage:
    python .githooks/install.py

Sets core.hooksPath so that .githooks/pre-commit and .githooks/commit-msg
run automatically on every git commit — regardless of client (CLI, IDE, etc.).
"""

import os
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    result = subprocess.run(
        ["git", "config", "--local", "core.hooksPath", ".githooks"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )

    if result.returncode != 0:
        print(f"Failed to set core.hooksPath: {result.stderr.strip()}", file=sys.stderr)
        return 1

    # Verify
    check = subprocess.run(
        ["git", "config", "core.hooksPath"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    print(f"core.hooksPath set to: {check.stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
