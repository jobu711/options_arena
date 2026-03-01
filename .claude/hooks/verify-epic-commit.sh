#!/bin/bash
# Pre-commit hook for epic/* branches: requires Context7 verification stamp.
# Reads JSON from stdin (Claude Code PreToolUse hook protocol).
# Blocks git commit if .claude/.context7-stamp doesn't match staged diff hash.

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

# Resolve working directory
cd "$CWD" 2>/dev/null || exit 0
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

# Only enforce on epic/* branches
if [[ "$BRANCH" != epic/* ]]; then
  exit 0
fi

# Compute hash of currently staged changes using git's own hashing (portable)
STAGED_HASH=$(git diff --staged | git hash-object --stdin)
STAMP_FILE="$CWD/.claude/.context7-stamp"

# Check if stamp matches current staged changes
if [ -f "$STAMP_FILE" ]; then
  STAMP_HASH=$(cat "$STAMP_FILE" 2>/dev/null | tr -d '[:space:]')
  if [ "$STAMP_HASH" = "$STAGED_HASH" ]; then
    exit 0  # Verified — allow commit
  fi
fi

# Stamp missing or stale — block and instruct Claude to self-heal
cat <<HOOK_JSON
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Context7 verification required before committing to epic branch '$BRANCH'. Self-heal: 1) Run /context7 to verify data structures against library docs. 2) Fix any mismatches found. 3) Re-stage fixed files with git add. 4) Re-attempt the commit. The verification stamp will be written automatically after /context7 passes."
  }
}
HOOK_JSON
