#!/usr/bin/env python3
"""Pre-tool hook: blocks dangerous shell commands.

Reads JSON from stdin (Claude Code PreToolUse hook protocol).
Blocks destructive SQL, dangerous rm commands, and force-pushes to main/master.

Cross-platform — uses only Python stdlib (no external deps).
"""

import json
import re
import sys

# Patterns that should be blocked
_SQL_DESTRUCTIVE = re.compile(r"\b(DROP\s+TABLE|DELETE\s+FROM|TRUNCATE)\b", re.IGNORECASE)
_RM_RF_CRITICAL = re.compile(
    r"\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+.*\b(src|data)[/\\]?"
    r"|\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+.*\b(src|data)[/\\]?",
    re.IGNORECASE,
)
_FORCE_PUSH_MAIN = re.compile(
    r"\bgit\s+push\s+.*--force.*\b(main|master)\b"
    r"|\bgit\s+push\s+.*\b(main|master)\b.*--force",
    re.IGNORECASE,
)


def is_dangerous(command: str) -> str | None:
    """Return a reason string if the command is dangerous, else None."""
    if _SQL_DESTRUCTIVE.search(command):
        return "Destructive SQL detected (DROP TABLE / DELETE FROM / TRUNCATE)"

    if _RM_RF_CRITICAL.search(command):
        return "Recursive forced deletion of critical directory (src/ or data/)"

    if _FORCE_PUSH_MAIN.search(command):
        return "Force push to main/master branch"

    return None


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Can't parse, allow

    tool_name: str = data.get("tool_name", "")

    # Only intercept Bash tool
    if tool_name != "Bash":
        sys.exit(0)

    tool_input: dict = data.get("tool_input", {})  # type: ignore[assignment]
    command: str = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    reason = is_dangerous(command)
    if reason is None:
        sys.exit(0)

    # Dangerous command detected — deny
    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked by dangerous-command-guard: {reason}. "
                f"Command: {command!r}. "
                f"If this is intentional, run the command manually outside Claude Code."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
