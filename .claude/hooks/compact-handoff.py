#!/usr/bin/env python3
"""PreCompact hook: captures working state to .claude/handoffs/ before compaction.

Writes a markdown handoff file with git state, active epics, and session info.
The next SessionStart hook auto-loads the latest handoff for continuity.

Cross-platform — uses only Python stdlib (no external deps).
"""

import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HANDOFF_DIR = os.path.join(_PROJECT_ROOT, ".claude", "handoffs")
_MAX_HANDOFFS = 5
_SUBPROCESS_TIMEOUT = 5


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


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


def _git_state() -> str:
    """Collect git state for the handoff."""
    lines: list[str] = []

    branch = _run_git(["branch", "--show-current"])
    if branch:
        lines.append(f"**Branch**: `{branch}`")

    status = _run_git(["status", "--porcelain", "--short"])
    if status:
        status_lines = status.splitlines()
        lines.append(f"**Uncommitted changes** ({len(status_lines)} files):")
        for s_line in status_lines[:15]:
            lines.append(f"- `{s_line.strip()}`")
        if len(status_lines) > 15:
            lines.append(f"- ... and {len(status_lines) - 15} more")
    else:
        lines.append("**Working tree**: Clean")

    # Staged diff stats
    staged = _run_git(["diff", "--cached", "--stat"])
    if staged:
        lines.append(f"**Staged changes**:\n```\n{staged}\n```")

    # Recent commits
    log = _run_git(["log", "--oneline", "-10"])
    if log:
        lines.append("**Recent commits**:")
        for commit_line in log.splitlines()[:10]:
            lines.append(f"- `{commit_line}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Epic helpers
# ---------------------------------------------------------------------------


def _epic_state() -> str:
    """Collect active epic state."""
    pattern = os.path.join(_PROJECT_ROOT, ".claude", "epics", "*", "checkpoint.json")
    checkpoint_files = glob.glob(pattern)

    if not checkpoint_files:
        return ""

    lines: list[str] = []
    for cp_path in sorted(checkpoint_files):
        try:
            with open(cp_path, encoding="utf-8") as f:
                cp = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            continue

        status = cp.get("status", "")
        if status == "complete":
            continue

        epic_name = os.path.basename(os.path.dirname(cp_path))
        phase = cp.get("current_phase", "unknown")
        issues = cp.get("issues", {})
        done = sum(1 for v in issues.values() if v.get("status") == "done")
        in_progress = sum(1 for v in issues.values() if v.get("status") == "in_progress")
        total = len(issues)

        lines.append(f"- **{epic_name}**: phase=`{phase}`, {done}/{total} done, {in_progress} in-progress")

    if not lines:
        return ""

    return "**Active epics**:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Session info
# ---------------------------------------------------------------------------


def _session_info() -> str:
    """Collect context-monitor session info if available."""
    ppid = os.getppid()
    import tempfile
    state_path = os.path.join(tempfile.gettempdir(), f"claude-context-monitor-{ppid}.json")

    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        tool_count = state.get("tool_count", 0)
        return f"**Session tool count at compaction**: {tool_count}"
    except (OSError, json.JSONDecodeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# Handoff management
# ---------------------------------------------------------------------------


def _prune_handoffs() -> None:
    """Keep only the latest N handoff files."""
    handoff_files = sorted(glob.glob(os.path.join(_HANDOFF_DIR, "handoff-*.md")), reverse=True)
    for old_file in handoff_files[_MAX_HANDOFFS:]:
        try:
            os.remove(old_file)
        except OSError:
            pass


def _write_handoff() -> str:
    """Write a handoff file and return its path."""
    os.makedirs(_HANDOFF_DIR, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    filename = f"handoff-{timestamp}.md"
    filepath = os.path.join(_HANDOFF_DIR, filename)

    sections: list[str] = []
    sections.append(f"# Handoff — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    sections.append("")

    git = _git_state()
    if git:
        sections.append("## Git State")
        sections.append(git)
        sections.append("")

    epics = _epic_state()
    if epics:
        sections.append("## Epics")
        sections.append(epics)
        sections.append("")

    session = _session_info()
    if session:
        sections.append("## Session")
        sections.append(session)
        sections.append("")

    content = "\n".join(sections)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        return ""

    _prune_handoffs()
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # PreCompact hooks receive JSON on stdin
    raw = sys.stdin.read()
    try:
        json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    filepath = _write_handoff()

    if filepath:
        basename = os.path.basename(filepath)
        result = {"message": f"State preserved to .claude/handoffs/{basename}"}
        print(json.dumps(result))

    sys.exit(0)


if __name__ == "__main__":
    main()
