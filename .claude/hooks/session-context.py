#!/usr/bin/env python3
"""SessionStart hook: auto-injects git state, active epics, and latest handoff.

Fires once at session start to provide immediate orientation context.

Cross-platform — uses only Python stdlib (no external deps).
"""

import glob
import json
import os
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MAX_TOTAL_CHARS = 2000
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


def _git_section() -> str:
    """Build git state section."""
    lines: list[str] = []

    branch = _run_git(["branch", "--show-current"])
    if branch:
        lines.append(f"Branch: {branch}")

    log = _run_git(["log", "--oneline", "-5"])
    if log:
        lines.append("Recent commits:")
        for commit_line in log.splitlines()[:5]:
            lines.append(f"  {commit_line}")

    status = _run_git(["status", "--porcelain", "--short"])
    if status:
        status_lines = status.splitlines()
        lines.append(f"Uncommitted changes ({len(status_lines)} files):")
        for s_line in status_lines[:10]:
            lines.append(f"  {s_line}")
        if len(status_lines) > 10:
            lines.append(f"  ... and {len(status_lines) - 10} more")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Epic helpers
# ---------------------------------------------------------------------------


def _epic_section() -> str:
    """Scan for active (non-complete) epics from checkpoint.json files."""
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

        lines.append(f"  {epic_name}: phase={phase}, {done}/{total} done, {in_progress} in-progress")

    if not lines:
        return ""

    return "Active epics:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Handoff helpers
# ---------------------------------------------------------------------------


def _handoff_section() -> str:
    """Load the most recent handoff file if it exists."""
    handoff_dir = os.path.join(_PROJECT_ROOT, ".claude", "handoffs")
    if not os.path.isdir(handoff_dir):
        return ""

    handoff_files = sorted(glob.glob(os.path.join(handoff_dir, "handoff-*.md")), reverse=True)
    if not handoff_files:
        return ""

    latest = handoff_files[0]
    try:
        with open(latest, encoding="utf-8") as f:
            content = f.read(800)
    except OSError:
        return ""

    if not content.strip():
        return ""

    basename = os.path.basename(latest)
    return f"Last handoff ({basename}):\n{content.strip()}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # SessionStart hooks receive empty or minimal stdin
    raw = sys.stdin.read()
    # Parse but don't require valid JSON — SessionStart may send empty input
    try:
        json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    sections: list[str] = []

    git = _git_section()
    if git:
        sections.append(git)

    epics = _epic_section()
    if epics:
        sections.append(epics)

    handoff = _handoff_section()
    if handoff:
        sections.append(handoff)

    if not sections:
        sys.exit(0)

    context = "\n\n".join(sections)
    # Cap total output
    if len(context) > _MAX_TOTAL_CHARS:
        context = context[:_MAX_TOTAL_CHARS - 3] + "..."

    result = {"message": f"[Session Context]\n{context}"}
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
