#!/usr/bin/env python3
"""Post-tool hook: warns when context window is getting heavy.

Tracks tool invocations per session via a JSON temp file. Injects warnings
at configurable thresholds to prevent context rot — the silent quality
degradation that happens as the context window fills.

Input (stdin): {"tool_name": "...", "tool_input": {...}}
Output (stdout): JSON with warning message when threshold hit
Exit: always 0 (never blocks)

Cross-platform — uses only Python stdlib (no external deps).
"""

import json
import os
import sys
import tempfile

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WARN_THRESHOLD = 60  # tools — "context getting heavy"
CRITICAL_THRESHOLD = 80  # tools — "context critically full"
DEBOUNCE_GAP = 8  # tools between repeated warnings at same level

# ---------------------------------------------------------------------------
# State file management
# ---------------------------------------------------------------------------


def _state_path() -> str:
    """Return path to the session state file, keyed by parent process ID."""
    ppid = os.getppid()
    return os.path.join(tempfile.gettempdir(), f"claude-context-monitor-{ppid}.json")


def _load_state(path: str) -> dict:
    """Load state from disk, returning defaults if missing/corrupt."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return {"tool_count": 0, "last_warning_level": "none", "last_warning_at": 0}


def _save_state(path: str, state: dict) -> None:
    """Persist state to disk. Best-effort — failure is silent."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Warning logic
# ---------------------------------------------------------------------------

_WARNINGS = {
    "warn": (
        "Context getting heavy ({count} tool calls). "
        "Consider wrapping up current work and committing before starting new tasks."
    ),
    "critical": (
        "Context critically full ({count} tool calls). "
        "Commit current work now. Start a fresh session for new tasks."
    ),
}


def _determine_level(count: int) -> str:
    """Return the current severity level based on tool count."""
    if count >= CRITICAL_THRESHOLD:
        return "critical"
    if count >= WARN_THRESHOLD:
        return "warn"
    return "none"


def _should_warn(level: str, state: dict) -> bool:
    """Check if we should emit a warning, respecting debounce rules."""
    if level == "none":
        return False

    last_level = state.get("last_warning_level", "none")
    last_at = state.get("last_warning_at", 0)
    count = state["tool_count"]

    # Severity escalation bypasses debounce
    severity = {"none": 0, "warn": 1, "critical": 2}
    if severity.get(level, 0) > severity.get(last_level, 0):
        return True

    # Same level — respect debounce gap
    if count - last_at >= DEBOUNCE_GAP:
        return True

    return False


def _emit_warning(level: str, count: int) -> None:
    """Write warning to stdout (Claude sees it) and stderr (user sees it)."""
    template = _WARNINGS[level]
    message = template.format(count=count)

    # stdout: JSON for Claude context
    result = {"warning": message, "level": level, "tool_count": count}
    print(json.dumps(result))

    # stderr: plain text for user terminal
    prefix = "WARNING" if level == "warn" else "CRITICAL"
    print(f"[context-monitor] {prefix}: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Parse stdin (hook protocol)
    raw = sys.stdin.read()
    try:
        json.loads(raw)  # validate it's JSON, we don't need the content
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    # Load and increment
    path = _state_path()
    state = _load_state(path)
    state["tool_count"] = state.get("tool_count", 0) + 1

    # Determine warning level
    level = _determine_level(state["tool_count"])

    if _should_warn(level, state):
        _emit_warning(level, state["tool_count"])
        state["last_warning_level"] = level
        state["last_warning_at"] = state["tool_count"]

    _save_state(path, state)
    sys.exit(0)


if __name__ == "__main__":
    main()
