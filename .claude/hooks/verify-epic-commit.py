#!/usr/bin/env python3
"""Pre-commit hook for epic/* branches: requires Context7 verification stamp.

Reads JSON from stdin (Claude Code PreToolUse hook protocol).
Blocks git commit if .claude/.context7-stamp doesn't match staged diff hash.

Cross-platform replacement for verify-epic-commit.sh — uses only Python stdlib,
no jq dependency.
"""

import datetime
import json
import os
import subprocess
import sys

# Resolve project root from script location: .claude/hooks/script.py → project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_cwd(data: dict) -> str:  # type: ignore[type-arg]
    """Resolve working directory with robust fallback chain."""
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or _PROJECT_ROOT
    return cwd


def _log_debug(label: str, raw_stdin: str) -> None:
    """Append diagnostic info to hook debug log (temporary)."""
    log_path = os.path.join(
        os.environ.get("CLAUDE_PROJECT_DIR", _PROJECT_ROOT),
        ".claude",
        ".hook-debug.log",
    )
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {label} @ {datetime.datetime.now(datetime.UTC).isoformat()} ---\n")
            f.write(f"CWD: {os.getcwd()}\n")
            f.write(f"CLAUDE_PROJECT_DIR: {os.environ.get('CLAUDE_PROJECT_DIR', 'NOT SET')}\n")
            f.write(f"_PROJECT_ROOT: {_PROJECT_ROOT}\n")
            f.write(f"Script __file__: {os.path.abspath(__file__)}\n")
            f.write(f"stdin length: {len(raw_stdin)}\n")
            f.write(f"stdin: {raw_stdin[:500]}\n")
    except Exception:
        pass


def main() -> None:
    # Read JSON from stdin
    raw = sys.stdin.read()

    _log_debug("verify-epic-commit", raw)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Can't parse, allow

    command: str = data.get("tool_input", {}).get("command", "")
    cwd: str = _resolve_cwd(data)

    # Only intercept git commit commands
    if not command.startswith("git commit"):
        sys.exit(0)

    # Check branch -- only enforce on epic/* branches
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        branch = result.stdout.strip()
    except Exception:
        sys.exit(0)

    if not branch.startswith("epic/"):
        sys.exit(0)

    # Compute hash of currently staged changes using git's own hashing (portable)
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            cwd=cwd,
        )
        hash_result = subprocess.run(
            ["git", "hash-object", "--stdin"],
            input=diff_result.stdout,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        staged_hash = hash_result.stdout.strip()
    except Exception:
        sys.exit(0)

    # Check stamp file
    stamp_file = os.path.join(cwd, ".claude", ".context7-stamp")
    if os.path.isfile(stamp_file):
        try:
            with open(stamp_file) as f:
                stamp_hash = f.read().strip()
            if stamp_hash == staged_hash:
                sys.exit(0)  # Verified -- allow commit
        except OSError:
            pass  # Can't read stamp, fall through to block

    # Stamp missing or stale -- block and instruct Claude to self-heal
    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Context7 verification required before committing to epic branch "
                f"'{branch}'. Self-heal: 1) Run /context7 to verify data structures "
                f"against library docs. 2) Fix any mismatches found. 3) Re-stage "
                f"fixed files with git add. 4) Re-attempt the commit. The "
                f"verification stamp will be written automatically after /context7 "
                f"passes."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
