#!/usr/bin/env python3
"""Pre-tool hook: blocks write operations on the SQLite MCP server.

Audit agents get read-only DB access. Write and create-table tools are denied.

Cross-platform — uses only Python stdlib (no external deps).
"""

import json
import sys

# MCP tool names that modify the database
_WRITE_TOOLS = frozenset(
    {
        "mcp__sqlite__write_query",
        "mcp__sqlite__create_table",
    }
)


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name: str = data.get("tool_name", "")

    if tool_name not in _WRITE_TOOLS:
        sys.exit(0)

    # Block write operations
    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked by sqlite-readonly-guard: {tool_name}. "
                "Production database is read-only for audit agents. "
                "Use static code analysis or read_query for inspection."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
