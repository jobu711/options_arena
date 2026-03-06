#!/usr/bin/env python3
"""Pre-tool hook: blocks commits when version strings are out of sync.

Checks pyproject.toml, web/package.json, and .claude/context/progress.md
all declare the same version. Fires on Bash tool calls that look like
git commit operations.

Cross-platform — uses only Python stdlib.
"""

import json
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def extract_pyproject_version(root: str) -> str | None:
    """Read version from pyproject.toml."""
    path = os.path.join(root, "pyproject.toml")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^version\s*=\s*"([^"]+)"', line.strip())
            if m:
                return m.group(1)
    return None


def extract_package_json_version(root: str) -> str | None:
    """Read version from web/package.json."""
    path = os.path.join(root, "web", "package.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def extract_progress_version(root: str) -> str | None:
    """Read version from .claude/context/progress.md."""
    path = os.path.join(root, ".claude", "context", "progress.md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.search(r"\*\*Version\*\*:\s*(\d+\.\d+\.\d+)", line)
            if m:
                return m.group(1)
    return None


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name: str = data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input_value = data.get("tool_input", {})
    if not isinstance(tool_input_value, dict):
        sys.exit(0)
    command_value = tool_input_value.get("command", "")
    command = command_value if isinstance(command_value, str) else ""

    # Only check on git commit commands
    if "git commit" not in command:
        sys.exit(0)

    cwd: str = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or _PROJECT_ROOT

    pyproject = extract_pyproject_version(cwd)
    package_json = extract_package_json_version(cwd)
    progress = extract_progress_version(cwd)

    sources = {
        "pyproject.toml": pyproject,
        "web/package.json": package_json,
        ".claude/context/progress.md": progress,
    }

    found = {k: v for k, v in sources.items() if v is not None}
    unique = set(found.values())

    if len(unique) <= 1:
        # All match (or only one source found) — allow
        sys.exit(0)

    # Mismatch detected — deny the commit
    detail = ", ".join(f"{k}={v}" for k, v in found.items())
    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Version mismatch detected: {detail}. "
                f"All three files must declare the same version. "
                f"Self-heal: Update the out-of-sync file(s) to match "
                f"pyproject.toml ({pyproject}), then retry the commit."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
