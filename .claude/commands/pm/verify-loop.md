---
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion, Skill
---

# Verify Loop

Orchestrator: runs epic-verify, epic-merge, and epic-retro in sequence.

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
Step 1/3 — Verification: {pass}/{total} PASS, {warn} WARN, {fail} FAIL
```

### Step 2: Gate Decision

If any FAIL items remain after overrides:

Ask the user:
- **"Review & override"**: Go back to interactive override for remaining FAILs
- **"Abort"**: Stop here. Print: "Verify loop aborted. Fix issues and re-run."
- **"Continue anyway"**: Proceed to merge despite failures

If no FAIL items (only PASS/WARN/SKIP), proceed automatically.

### Step 3: Merge

Execute the full `/pm:epic-merge` flow:

1. Pre-merge validation (includes soft verification gate — will see the report we just wrote)
2. Run tests if recommended
3. Update epic documentation (status: completed)
4. Merge branch to main with `--no-ff`
5. Handle conflicts if any (abort loop if unresolvable)
6. Post-merge cleanup (worktree, branch, archive)
7. Close GitHub issues

Display summary:
```
Step 2/3 — Merge: epic/$ARGUMENTS merged to main
```

**If merge fails**: preserve verification report, display conflict details, and stop.
User can resolve conflicts manually and re-run `/pm:epic-merge` + `/pm:epic-retro` separately.

### Step 4: Retro

Execute the full `/pm:epic-retro` flow:

1. Gather all epic data (now in archived location)
2. Compute proxy hours per task from git history
3. Analyze scope delta (planned vs delivered)
4. Assess quality (test coverage, post-merge fixes)
5. Extract learnings
6. Write `retro.md`
7. Append to `velocity.jsonl`
8. Update `estimation-bias.md`

Display summary:
```
Step 3/3 — Retro: {proxy_hours}h actual vs {planned_hours}h planned ({ratio}x)
```

### Step 5: Final Output

```
Verify loop complete: $ARGUMENTS

  Verification: {pass}/{total} PASS ({coverage}%)
  Merge: epic/$ARGUMENTS -> main ({commits} commits, {files} files)
  Effort: {proxy_hours}h actual vs {planned_hours}h planned
  Quality: {post_merge_fixes} post-merge fixes

Reports:
  - .claude/epics/archived/$ARGUMENTS/verification-report.md
  - .claude/epics/archived/$ARGUMENTS/retro.md
  - .claude/metrics/velocity.jsonl

Next: /pm:next
```

## Recovery

Each step is independently recoverable:

- **Verification fails to complete**: report is still written (partial). User can fix and re-run `/pm:epic-verify`.
- **Merge fails (conflicts)**: verification report is preserved. User resolves conflicts, then runs `/pm:epic-merge` + `/pm:epic-retro` separately.
- **Retro fails**: merge is already done. User can run `/pm:epic-retro` independently.

The verify loop never leaves the repository in an inconsistent state — each step either completes fully or aborts cleanly.
