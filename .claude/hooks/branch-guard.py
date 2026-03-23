#!/usr/bin/env python3
"""Pre-tool hook: prevents epic-to-epic branch switching.

When on `epic/X`, blocks `git checkout epic/Y` or `git switch epic/Y` to prevent
cross-contamination when multiple Claude Code sessions share the same working directory.

Allowed transitions:
  - epic/X -> epic/X (same branch, no-op)
  - epic/X -> master/main (returning to trunk)
  - master -> epic/X (entering an epic)
  - epic/X -> -b epic/Y (creating a new branch)
  - epic/X -> -- file (file checkout, not branch switch)
  - Any transition inside a git worktree (isolated by design)

Cross-platform — uses only Python stdlib (no external deps).
"""

import json
import os
import re
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SUBPROCESS_TIMEOUT = 5

# Matches: git checkout epic/... or git switch epic/...
# Captures the target epic branch name after epic/
_CHECKOUT_EPIC = re.compile(
    r"\bgit\s+(?:checkout|switch)\s+(?!.*(?:-[bBcC]\b|--create\b|--orphan\b|--\s)).*\bepic/(\S+)"
)

# Detects branch creation flags — if present, this is a new branch, not a switch
_BRANCH_CREATE = re.compile(r"\s(?:-[bBcC]\b|--create\b|--orphan\b)")

# Detects file checkout (-- before paths)
_FILE_CHECKOUT = re.compile(r"\s--\s")


def _run_git(args: list[str]) -> str:
    """Run a git command, return stdout or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            cwd=_PROJECT_ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _is_worktree() -> bool:
    """Check if we're in a git worktree (not the main working tree)."""
    git_dir = _run_git(["rev-parse", "--git-dir"])
    common_dir = _run_git(["rev-parse", "--git-common-dir"])
    if not git_dir or not common_dir:
        return False
    # Normalize paths for comparison
    return os.path.normpath(git_dir) != os.path.normpath(common_dir)


def _get_current_branch() -> str:
    """Get the current branch name."""
    return _run_git(["branch", "--show-current"])


def check_epic_switch(command: str) -> str | None:
    """Return a deny reason if the command switches between epic branches, else None."""
    # Skip file checkouts (git checkout -- path/to/file)
    if _FILE_CHECKOUT.search(command):
        return None

    # Skip branch creation (git checkout -b, git switch -c, etc.)
    if _BRANCH_CREATE.search(command):
        return None

    # Check if command targets an epic branch
    match = _CHECKOUT_EPIC.search(command)
    if not match:
        return None

    target_epic = match.group(1)

    # Worktrees are always allowed — they're isolated by design
    if _is_worktree():
        return None

    # Get current branch
    current_branch = _get_current_branch()
    if not current_branch.startswith("epic/"):
        return None  # Not on an epic branch — allow

    current_epic = current_branch.removeprefix("epic/")

    # Same epic — allow (no-op or re-checkout)
    if current_epic == target_epic:
        return None

    # Different epic — DENY
    return (
        f"Cannot switch from epic/{current_epic} to epic/{target_epic}. "
        f"Multiple sessions share this directory — switching would contaminate both epics.\n"
        f"Use worktree mode instead:\n"
        f"  /pm:epic-start {target_epic} --worktree\n"
        f"Or manually:\n"
        f"  git worktree add ../epic-{target_epic} -b epic/{target_epic}"
    )


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Can't parse, allow

    tool_name: str = data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input: dict = data.get("tool_input", {})  # type: ignore[assignment]
    command: str = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    reason = check_epic_switch(command)
    if reason is None:
        sys.exit(0)

    # Epic-to-epic switch detected — deny
    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Blocked by branch-guard: {reason}",
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
