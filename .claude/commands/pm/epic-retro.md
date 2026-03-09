---
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
---

# Epic Retro

Post-merge retrospective: effort accuracy, quality analysis, learnings, velocity tracking.

## Usage
```
/pm:epic-retro <epic_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Do not bother the user with preflight checks progress. Just do them and move on.

1. **Verify epic name was provided:**
   - If not: "Epic name required. Usage: /pm:epic-retro <epic_name>"

2. **Locate archived epic:**
   - Check `.claude/epics/archived/$ARGUMENTS/` first (expected location post-merge)
   - Then check `.claude/epics/$ARGUMENTS/` (may not be archived yet)
   - If not found: "Epic not found: $ARGUMENTS"
   - Set `$EPIC_DIR` to the found path

3. **Verify epic has completion indicators:**
   - Read `epic.md` — check for `status: completed` or presence of merge commits
   - If not completed, warn: "Epic not marked complete. Retro may be incomplete."

## Instructions

### 1. Gather Epic Data

Read all available epic files:
- `$EPIC_DIR/epic.md` — overview, architecture decisions, created/completed dates
- `$EPIC_DIR/[0-9]*.md` — all task files (frontmatter: name, status, github, test_files)
- `$EPIC_DIR/checkpoint.json` — phase tracking (if exists)
- `$EPIC_DIR/execution-status.md` — execution notes (if exists)
- `$EPIC_DIR/verification-report.md` — verification results (if exists)
- PRD file (from epic.md `prd:` field)

Extract from PRD:
- Original scope (requirement count, task count planned)

### 2. Effort Analysis

For each task with a `github:` issue number, compute proxy development hours from git history.

```bash
# Get commit timestamps and count for this issue
git log --all --format="%aI" --grep="#{issue_number}" 2>/dev/null
```

For each task:
- `commit_count`: number of commits referencing the issue
- `first_commit` / `last_commit`: earliest and latest commit timestamps
- `raw_elapsed_hours`: time between first and last commit (in hours)
- `proxy_hours`: `min(raw_elapsed_hours, commit_count * 2.0)` — caps elapsed time to avoid counting overnight gaps
- Floor: `max(proxy_hours, commit_count * 0.5)` — minimum half hour per commit
- Single-commit default: `1.0` hour

Extract planned effort from task frontmatter or body:
- Look for "Effort Estimate", "Size:", or "Hours:" fields
- Map sizes: S=2h, M=4h, L=8h, XL=16h (if only size given)

Compute per-task `estimation_ratio = proxy_hours / planned_hours`.

### 3. Scope Analysis

Compare planned vs delivered:
- **Planned tasks**: count of task files in epic directory
- **Delivered tasks**: count with `status: closed` or `status: completed`
- **Scope creep**: tasks added after initial decomposition (if detectable from created dates vs epic created date)
- **Scope cuts**: tasks with `status: descoped` or `status: wontfix`

### 4. Quality Analysis

Find all files changed by this epic's commits:
```bash
# Get all files changed by epic commits
for issue_num in {issue_numbers}; do
  git log --all --name-only --format="" --grep="#${issue_num}" 2>/dev/null
done | sort -u
```

For each changed production file (`src/options_arena/**`):
- Check if a corresponding test file exists
- Count test functions in the test file

Check for post-merge fixes (commits within 7 days after last epic commit touching same files):
```bash
git log --all --oneline --after="{last_epic_commit_date}" --until="{last_epic_commit_date + 7 days}" -- {epic_files} 2>/dev/null | grep -i "fix:"
```

### 5. Extract Learnings

Analyze the data to identify:
- **Estimation accuracy**: which task sizes were most accurately estimated?
- **Velocity**: tasks per day, commits per task
- **Architecture decisions**: read epic.md "Architecture Decisions" — note which held up
- **Reusable patterns**: any patterns from this epic that should be documented?
- **What went well**: tasks completed faster than estimated
- **What was hard**: tasks that took much longer, or had post-merge fixes

### 6. Write Retro Report

Get REAL current datetime by running the appropriate command for the platform.

Write `$EPIC_DIR/retro.md`:

```markdown
---
epic: {epic_name}
retro_date: {current ISO datetime}
duration_days: {days from epic created to completed}
task_count: {total tasks}
planned_hours_total: {sum of planned hours}
proxy_hours_total: {sum of proxy hours}
estimation_ratio: {proxy_total / planned_total}
---

# Retrospective: {epic_name}

## Effort Analysis

| Task | Issue | Planned | Proxy Hours | Commits | Ratio | Assessment |
|------|-------|---------|-------------|---------|-------|------------|
| {name} | #{num} | {S/M/L + hours} | {proxy_hours} | {count} | {ratio} | Over/Under/Accurate |

**Totals**: {planned}h planned, {proxy}h actual (proxy), {ratio}x estimation ratio

## Scope Delta

- **Planned**: {N} tasks
- **Delivered**: {N} tasks
- **Added** (scope creep): {N} tasks — {names}
- **Cut** (descoped): {N} tasks — {names}

## Quality Assessment

- **Files changed**: {count} production files, {count} test files
- **Test coverage**: {files_with_tests}/{total_prod_files} production files have tests
- **Post-merge fixes**: {count} fix commits within 7 days
- **Verification**: {from verification-report if exists: pass/total coverage}

## Learnings

### What Went Well
{bullet points}

### What Was Hard
{bullet points}

### Estimation Insights
{bullet points about accuracy by task size}

### Recommendations for Future Epics
{bullet points}
```

### 7. Append Velocity Log

Create `.claude/metrics/` directory if it doesn't exist:
```bash
mkdir -p .claude/metrics
```

Append one JSON line to `.claude/metrics/velocity.jsonl`:
```json
{"epic":"{name}","completed":"{ISO}","duration_days":{N},"task_count":{N},"planned_hours_total":{N},"proxy_hours_total":{N},"estimation_ratio":{N},"commits":{N},"files_changed":{N},"tests_added":{N},"post_merge_fixes":{N},"requirements_verified":{N},"requirements_total":{N},"tasks":[{"id":{N},"name":"...","planned_size":"S","planned_hours":{N},"proxy_hours":{N}}],"learnings":["..."]}
```

Use a single line — this is JSONL format (one JSON object per line).

### 8. Update Estimation Bias

Read all entries from `.claude/metrics/velocity.jsonl` (if it exists with >1 entry).

Compute running averages:
- Average estimation ratio by task size (S/M/L/XL)
- Average estimation ratio overall
- Tasks per day trend

Write `.claude/metrics/estimation-bias.md`:

```markdown
# Estimation Bias Report

Generated: {datetime}
Based on: {N} epics, {N} tasks

## By Task Size

| Size | Planned Hours | Avg Proxy Hours | Avg Ratio | Sample Count |
|------|--------------|-----------------|-----------|--------------|
| S | 2h | {avg}h | {ratio}x | {N} |
| M | 4h | {avg}h | {ratio}x | {N} |
| L | 8h | {avg}h | {ratio}x | {N} |

## Overall

- **Average estimation ratio**: {ratio}x (>1.0 = under-estimating, <1.0 = over-estimating)
- **Median epic duration**: {days} days
- **Average tasks per epic**: {count}

## Recommendation

{If ratio > 1.3}: "Consistently under-estimating. Multiply estimates by {ratio}."
{If ratio < 0.7}: "Consistently over-estimating. Reduce estimates by {1/ratio}."
{If 0.7-1.3}: "Estimation accuracy is reasonable."
```

If only 1 entry exists, write the report with a note: "Insufficient data for trends. Need 3+ epics."

### 9. Output

```
Retro complete: $ARGUMENTS

  Duration: {days} days
  Tasks: {delivered}/{planned} delivered
  Effort: {proxy_hours}h actual vs {planned_hours}h planned ({ratio}x)
  Quality: {post_merge_fixes} post-merge fixes
  Report: $EPIC_DIR/retro.md
  Velocity: .claude/metrics/velocity.jsonl

Next: /pm:next
```

## Error Recovery

- If git log returns no commits for a task, record proxy_hours as 0 and note "no commits found"
- If planned hours cannot be determined, use task size mapping (S=2, M=4, L=8)
- If no task sizes found either, default to M=4h per task
- velocity.jsonl append failures are warned but don't stop the command
- Estimation bias update failures are warned but don't stop the command
