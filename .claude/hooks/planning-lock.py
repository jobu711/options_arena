#!/usr/bin/env python3
"""Pre-tool hook: blocks Write/Edit to src/tests/web/data during planning phase.

Reads JSON from stdin (Claude Code PreToolUse hook protocol).
Scans .claude/epics/*/.planning-lock for active planning locks.
If lock found AND target file_path is in a blocked prefix, denies with self-heal message.

Cross-platform — uses only Python stdlib (no jq, no external deps).
"""

import json
import os
import sys
from pathlib import Path


# Prefixes where code writes are blocked during planning
BLOCKED_PREFIXES = ("src/", "tests/", "web/", "data/migrations/")

# Prefixes that are always allowed (planning artifacts)
ALLOWED_PREFIXES = (".claude/",)


def normalize_path(p: str) -> str:
    """Normalize Windows backslashes to forward slashes for consistent matching."""
    return p.replace("\\", "/")


def find_planning_locks(cwd: str) -> list[tuple[str, str]]:
    """Find all active .planning-lock files under .claude/epics/.

    Returns list of (epic_name, lock_file_path) tuples.
    """
    epics_dir = os.path.join(cwd, ".claude", "epics")
    locks: list[tuple[str, str]] = []
    if not os.path.isdir(epics_dir):
        return locks
    try:
        for entry in os.listdir(epics_dir):
            lock_path = os.path.join(epics_dir, entry, ".planning-lock")
            if os.path.isfile(lock_path):
                locks.append((entry, lock_path))
    except OSError:
        pass
    return locks


def is_blocked(file_path: str) -> bool:
    """Check if the file path falls under a blocked prefix."""
    normalized = normalize_path(file_path)

    # Always allow .claude/ paths
    for prefix in ALLOWED_PREFIXES:
        if normalized.startswith(prefix):
            return False

    # Check blocked prefixes
    for prefix in BLOCKED_PREFIXES:
        if normalized.startswith(prefix):
            return True

    return False


def get_relative_path(file_path: str, cwd: str) -> str:
    """Convert absolute path to relative path from cwd."""
    try:
        return str(Path(file_path).relative_to(Path(cwd)))
    except ValueError:
        return file_path


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Can't parse, allow

    tool_name: str = data.get("tool_name", "")

    # Only intercept Write and Edit tools
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    cwd: str = data.get("cwd", ".")
    tool_input: dict = data.get("tool_input", {})  # type: ignore[assignment]
    file_path: str = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    # Make path relative for prefix matching
    relative = normalize_path(get_relative_path(file_path, cwd))

    # Check if path is blocked
    if not is_blocked(relative):
        sys.exit(0)

    # Check for active planning locks
    locks = find_planning_locks(cwd)
    if not locks:
        sys.exit(0)

    # Found lock(s) AND target is in a blocked prefix — deny
    epic_names = [name for name, _ in locks]
    epics_str = ", ".join(f"'{n}'" for n in epic_names)

    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Planning phase active for epic {epics_str}. "
                f"Code writes to {relative} are blocked during planning. "
                f"Allowed during planning: .claude/ files only. "
                f"Self-heal: Complete planning with /pm:epic-decompose "
                f"{epic_names[0]} to remove the planning lock and enable code writes."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
