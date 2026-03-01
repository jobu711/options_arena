#!/bin/bash
# Code analysis hook for epic/* branches (large commits only).
# Size gate: skips fix:/chore:/docs:/test: prefixes and diffs under 100 lines.
# Defers to context7 hook if context7 stamp is missing/stale.
# Reads JSON from stdin (Claude Code PreToolUse hook protocol).

# Require jq — silently pass if not available
if ! command -v jq &>/dev/null; then
  exit 0
fi

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd')

# Only intercept git commit commands
if [[ "$COMMAND" != git\ commit* ]]; then
  exit 0
fi

cd "$CWD" 2>/dev/null || exit 0
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

# Only enforce on epic/* branches
if [[ "$BRANCH" != epic/* ]]; then
  exit 0
fi

# --- SIZE GATE ---
# Extract commit message from -m flag (handles -m "msg" and -m 'msg')
COMMIT_MSG=$(echo "$COMMAND" | sed -n 's/.*-m[[:space:]]*["'"'"']\([^"'"'"']*\)["'"'"'].*/\1/p')
if [ -z "$COMMIT_MSG" ]; then
  COMMIT_MSG=$(echo "$COMMAND" | sed -n "s/.*-m[[:space:]]*\([^[:space:]]*\).*/\1/p")
fi

# Skip trivial commit prefixes
if [[ "$COMMIT_MSG" =~ ^(fix|chore|docs|test): ]]; then
  exit 0
fi

# Skip small diffs (under 100 lines changed)
LINES_CHANGED=$(git diff --staged --stat | tail -1 | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+')
LINES_DELETED=$(git diff --staged --stat | tail -1 | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+')
TOTAL_LINES=$(( ${LINES_CHANGED:-0} + ${LINES_DELETED:-0} ))
if [ "$TOTAL_LINES" -lt 100 ]; then
  exit 0
fi
# --- END SIZE GATE ---

# Compute staged hash
STAGED_HASH=$(git diff --staged | git hash-object --stdin)

# Defer if context7 hasn't passed yet (let context7 hook handle denial)
C7_STAMP="$CWD/.claude/.context7-stamp"
if [ ! -f "$C7_STAMP" ]; then
  exit 0
fi
C7_HASH=$(cat "$C7_STAMP" 2>/dev/null | tr -d '[:space:]')
if [ "$C7_HASH" != "$STAGED_HASH" ]; then
  exit 0
fi

# Context7 passed — check analyzer stamp
STAMP_FILE="$CWD/.claude/.analyze-stamp"
if [ -f "$STAMP_FILE" ]; then
  STAMP_HASH=$(cat "$STAMP_FILE" 2>/dev/null | tr -d '[:space:]')
  if [ "$STAMP_HASH" = "$STAGED_HASH" ]; then
    exit 0
  fi
fi

# Block — analyzer stamp missing or stale
cat <<HOOK_JSON
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Code analysis required for this large commit ($TOTAL_LINES lines) to epic branch '$BRANCH'. Context7 passed. Self-heal: 1) Run /analyze to review staged changes for bugs and regressions. 2) Fix critical/high findings. 3) Re-stage fixes with git add. 4) Re-attempt commit. Stamp written automatically after /analyze."
  }
}
HOOK_JSON
