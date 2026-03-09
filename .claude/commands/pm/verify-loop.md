---
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion, Skill
---

# Verify Loop

Orchestrator: runs epic-verify and epic-retro in sequence.

## Usage
```
/pm:verify-loop <epic_name>
```

## Preflight Checklist

Do not bother the user with preflight checks progress. Just do them and move on.

1. **Verify epic name was provided:**
   - If not: "Epic name required. Usage: /pm:verify-loop <epic_name>"

2. **Verify epic exists:**
   - Check `.claude/epics/$ARGUMENTS/` exists
   - If not found: "Epic not found: $ARGUMENTS"

3. **Verify all tasks closed:**
   - Read all `[0-9]*.md` task files in `.claude/epics/$ARGUMENTS/`
   - Check each has `status: closed` or `status: completed` in frontmatter
   - If any open: "Cannot run verify loop. Open tasks: {list}. Close them first."

## Instructions

### Step 1: Verify

Execute the full `/pm:epic-verify` flow:

1. Locate epic dir and PRD
2. Extract all requirements from PRD + task acceptance criteria
3. Grep `src/options_arena/` for code evidence per requirement
4. Verify test files exist and count test functions
5. Run tests: `uv run pytest {test_files} -v --tb=short`
6. Check git commit traces per task issue
7. Build traceability matrix (PASS/WARN/FAIL/SKIP)
8. Write `verification-report.md`
9. Handle interactive overrides if FAIL/WARN items exist
10. Update checkpoint with `"verified"` phase

Display summary:
```
Step 1/2 — Verification: {pass}/{total} PASS, {warn} WARN, {fail} FAIL
```

### Step 2: Gate Decision

If any FAIL items remain after overrides:

Ask the user:
- **"Review & override"**: Go back to interactive override for remaining FAILs
- **"Abort"**: Stop here. Print: "Verify loop aborted. Fix issues and re-run."
- **"Continue anyway"**: Proceed to retro despite failures

If no FAIL items (only PASS/WARN/SKIP), proceed automatically.

### Step 3: Retro

Execute the full `/pm:epic-retro` flow:

1. Gather all epic data
2. Compute proxy hours per task from git history
3. Analyze scope delta (planned vs delivered)
4. Assess quality (test coverage, post-merge fixes)
5. Extract learnings
6. Write `retro.md`
7. Append to `velocity.jsonl`
8. Update `estimation-bias.md`

Display summary:
```
Step 2/2 — Retro: {proxy_hours}h actual vs {planned_hours}h planned ({ratio}x)
```

### Step 4: Final Output

```
Verify loop complete: $ARGUMENTS

  Verification: {pass}/{total} PASS ({coverage}%)
  Effort: {proxy_hours}h actual vs {planned_hours}h planned
  Quality: {post_merge_fixes} post-merge fixes

Reports:
  - .claude/epics/$ARGUMENTS/verification-report.md
  - .claude/epics/$ARGUMENTS/retro.md
  - .claude/metrics/velocity.jsonl

Next: /pm:epic-merge $ARGUMENTS
```

## Recovery

Each step is independently recoverable:

- **Verification fails to complete**: report is still written (partial). User can fix and re-run `/pm:epic-verify`.
- **Retro fails**: verification is already done. User can run `/pm:epic-retro` independently.

The verify loop never leaves the repository in an inconsistent state — each step either completes fully or aborts cleanly.
