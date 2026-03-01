#!/usr/bin/env python3
"""Code analysis hook for epic/* branches (large commits only).

Size gate: skips fix:/chore:/docs:/test: prefixes and diffs under 100 lines.
Defers to context7 hook if context7 stamp is missing/stale.
Reads JSON from stdin (Claude Code PreToolUse hook protocol).

Cross-platform replacement for analyze-epic-commit.sh -- uses only Python stdlib,
no jq dependency.
"""

import json
import os
import re
import subprocess
import sys


def _extract_commit_message(command: str) -> str:
    """Extract commit message from a git commit command string.

    Handles:
      - git commit -m "message"
      - git commit -m 'message'
      - git commit -m "$(cat <<'EOF'\nmessage\nEOF\n)"
      - git commit -m message  (unquoted single word)
    """
    # Try quoted message first: -m "..." or -m '...'
    match = re.search(r'-m\s+"([^"]*)"', command)
    if match:
        return match.group(1)
    match = re.search(r"-m\s+'([^']*)'", command)
    if match:
        return match.group(1)

    # Heredoc pattern: -m "$(cat <<'EOF'\n...\nEOF\n)"
    # Extract just the first meaningful line after the heredoc opener
    match = re.search(r"-m\s+\"\$\(cat <<'?EOF'?\s*\n(.*?)(?:\n|$)", command)
    if match:
        return match.group(1).strip()

    # Unquoted single-word message: -m message
    match = re.search(r"-m\s+(\S+)", command)
    if match:
        return match.group(1)

    return ""


def _parse_lines_changed(cwd: str) -> int:
    """Parse total lines changed from git diff --staged --stat summary line.

    The summary line looks like:
      3 files changed, 120 insertions(+), 45 deletions(-)
    or with only insertions/deletions:
      1 file changed, 5 insertions(+)
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--staged", "--stat"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        output = result.stdout.strip()
    except Exception:
        return 0

    if not output:
        return 0

    # The summary is the last line
    summary = output.split("\n")[-1]

    insertions = 0
    deletions = 0

    ins_match = re.search(r"(\d+)\s+insertion", summary)
    if ins_match:
        insertions = int(ins_match.group(1))

    del_match = re.search(r"(\d+)\s+deletion", summary)
    if del_match:
        deletions = int(del_match.group(1))

    return insertions + deletions


def main() -> None:
    # Read JSON from stdin
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Can't parse, allow

    command: str = data.get("tool_input", {}).get("command", "")
    cwd: str = data.get("cwd", ".")

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

    # --- SIZE GATE ---

    # Extract commit message and skip trivial commit prefixes
    commit_msg = _extract_commit_message(command)
    trivial_prefixes = ("fix:", "chore:", "docs:", "test:")
    if commit_msg.startswith(trivial_prefixes):
        sys.exit(0)

    # Skip small diffs (under 100 lines changed)
    total_lines = _parse_lines_changed(cwd)
    if total_lines < 100:
        sys.exit(0)

    # --- END SIZE GATE ---

    # Compute staged hash
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

    # Defer if context7 hasn't passed yet (let context7 hook handle denial)
    c7_stamp_file = os.path.join(cwd, ".claude", ".context7-stamp")
    if not os.path.isfile(c7_stamp_file):
        sys.exit(0)

    try:
        with open(c7_stamp_file) as f:
            c7_hash = f.read().strip()
    except OSError:
        sys.exit(0)

    if c7_hash != staged_hash:
        sys.exit(0)  # Context7 stamp stale, let that hook handle it

    # Context7 passed -- check analyzer stamp
    stamp_file = os.path.join(cwd, ".claude", ".analyze-stamp")
    if os.path.isfile(stamp_file):
        try:
            with open(stamp_file) as f:
                stamp_hash = f.read().strip()
            if stamp_hash == staged_hash:
                sys.exit(0)  # Verified -- allow commit
        except OSError:
            pass  # Can't read stamp, fall through to block

    # Block -- analyzer stamp missing or stale
    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Code analysis required for this large commit ({total_lines} lines) "
                f"to epic branch '{branch}'. Context7 passed. Self-heal: 1) Run "
                f"/analyze to review staged changes for bugs and regressions. 2) Fix "
                f"critical/high findings. 3) Re-stage fixes with git add. 4) "
                f"Re-attempt commit. Stamp written automatically after /analyze."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
