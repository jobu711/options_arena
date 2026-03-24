---
title: "epic-sync fails: --json flag, grep locale, missing labels"
date: 2026-03-24
module: .claude.commands.pm.epic_sync
problem_type: integration_issues
severity: high
symptoms:
  - "gh issue create fails with 'unknown flag: --json'"
  - "grep -P supports only unibyte and UTF-8 locales"
  - "could not add label: 'epic:X' not found"
tags:
  - gh-cli
  - epic-sync
  - windows
  - grep
  - labels
root_cause: "epic-sync.md used gh issue create --json (unsupported), BRE grep syntax (Windows-fragile), and labels without pre-creation"
---

## Problem

`/pm:epic-sync` failed with three cascading errors on Windows:
1. `gh issue create --json number -q .number` -> `unknown flag: --json`
2. `grep -P` (invoked in gh's bash wrapper) -> locale error on MSYS2/Git Bash
3. `--label "epic:hedge-fund-frontend"` -> label doesn't exist in repo

## Root Cause

**`--json` flag**: `gh issue create` does NOT support `--json`. That flag is only available on `gh issue list` and `gh issue view`. The `create` subcommand outputs the issue URL to stdout instead.

**`grep` locale**: `grep -qi "bug\|fix\|..."` uses BRE backslash-alternation which behaves inconsistently across platforms. On Windows Git Bash, locale settings can cause `grep -P` failures when invoked internally.

**Missing labels**: GitHub rejects `--label` values that don't exist in the repository. Dynamic labels like `epic:$ARGUMENTS` are never pre-created by the script.

## Solution

1. **Replace `--json`** with URL extraction:
   ```bash
   epic_url=$(gh issue create --repo "$REPO" --title "..." --body-file /tmp/epic-body.md --label "...")
   epic_number=$(echo "$epic_url" | grep -o '[0-9]*$')
   ```

2. **Use ERE instead of BRE**:
   ```bash
   # Before: grep -qi "bug\|fix\|issue"
   grep -q -i -E "bug|fix|issue"
   ```

3. **Pre-create labels before use**:
   ```bash
   gh label create "epic:$ARGUMENTS" --repo "$REPO" --color "0075ca" --description "Epic: $ARGUMENTS" 2>/dev/null || true
   gh label create "epic" --repo "$REPO" --color "0075ca" --description "Epic tracking" 2>/dev/null || true
   gh label create "task" --repo "$REPO" --color "c5def5" --description "Task within epic" 2>/dev/null || true
   ```

## Prevention Rule

- `gh issue create` and `gh sub-issue create` return a URL, not JSON. Parse the issue number from the URL with `grep -o '[0-9]*$'`.
- Never use `grep -P` or BRE `\|` in cross-platform scripts. Always use `grep -E` for alternation.
- Always `gh label create ... 2>/dev/null || true` before referencing dynamic labels in `--label`.

## Related

- Commit `82d5513` — fix applied to `.claude/commands/pm/epic-sync.md`
- `gh issue create` docs: only supports `--title`, `--body`, `--body-file`, `--label`, `--assignee`, `--project`, `--milestone`
