---
allowed-tools: Bash, Read, Glob, Grep, Agent
---

# Epic Recap

Generate an inline visual recap of what was built in an epic, rendered directly in the
conversation as formatted markdown with ASCII diagrams.

## Usage
```
/pm:epic-recap <epic_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Do not narrate preflight steps. Just do them.

1. **Validate arguments:**
   - Extract `<epic_name>` from `$ARGUMENTS` (first word)
   - If no epic name: "Usage: `/pm:epic-recap <epic_name>`"

2. **Locate epic directory:**
   - Check `.claude/epics/$EPIC_NAME/` first (active/completed)
   - Then check `.claude/epics/archived/$EPIC_NAME/` (archived)
   - If not found: "Epic not found: `$EPIC_NAME`. Run `/pm:epic-list` to see available epics."
   - Set `$EPIC_DIR` to the found path

3. **Verify epic.md exists:**
   - Read `$EPIC_DIR/epic.md`
   - If missing: "Epic directory exists but `epic.md` is missing."

## Instructions

### 1. Gather Epic Data

Read these files (skip any that don't exist):

**Epic metadata:**
- `$EPIC_DIR/epic.md` — overview, architecture decisions, technical approach, status
- All `$EPIC_DIR/[0-9]*.md` — task files (use Glob pattern `$EPIC_DIR/[0-9]*.md`)
- `$EPIC_DIR/checkpoint.json` — phase tracking
- `$EPIC_DIR/retro.md` — retrospective metrics (if exists)
- PRD file path from `epic.md` frontmatter `prd:` field — read if it exists

**Git history:**

Run these commands to gather facts:

```bash
# Total commits on epic branch (if branch exists)
git log --oneline master..$EPIC_NAME 2>/dev/null | wc -l

# Files changed summary
git diff --stat master...$EPIC_NAME 2>/dev/null

# Per-task commits (for each issue number found in task files)
git log --all --oneline --grep="#<issue_number>" 2>/dev/null
```

If the epic branch doesn't exist (already merged), try:
```bash
# Search by epic name in commit messages
git log --all --oneline --grep="$EPIC_NAME" 2>/dev/null | head -30

# Search by issue numbers from task files
git log --all --oneline --grep="#<issue_number>" 2>/dev/null
```

### 2. Generate & Output Inline Recap

Synthesize the gathered data and **output directly as formatted markdown** in the
conversation. Be token-efficient — every sentence should carry information. No filler.

**Required sections** (output all of these inline):

---

# Epic Recap: {epic_name}

## Executive Summary

{2-3 sentences: what was built and why. Pull from epic.md overview.}

## Problem / Solution

**Problem**: {1-2 sentences from PRD problem statement}

**Solution**: {1-2 sentences describing what was delivered}

## What Changed

{Group files by module. Show file count and line delta per module.}

| Module | Files Changed | Lines (+/-) |
|--------|--------------|-------------|
| models/ | 3 | +245 / -12 |
| pricing/ | 1 | +89 / -0 |
| ... | ... | ... |

**New files**: {list new files, one per line}

## Architecture Decisions

{Pull from epic.md "Architecture Decisions" section. For each decision, add a one-line
annotation: "Held up well", "Required adjustment", or "Not yet validated".}

## Wave Execution

{Show the wave/phase execution strategy with an ASCII diagram:}

```
Wave 1 (parallel)     Wave 2 (sequential)     Wave 3 (sequential)
┌─────────────┐       ┌──────────────────┐     ┌──────────────────┐
│ Task A      │──┐    │ Task D           │──┐  │ Task F           │
│ Task B      │──┼──▶ │ Task E           │──┼─▶│ Task G           │
│ Task C      │──┘    └──────────────────┘  │  └──────────────────┘
└─────────────┘                             │
                                            ▼
                              {dependency arrows as needed}
```

{Adapt the diagram to the actual wave structure of the epic. Use box-drawing
characters (┌ ┐ └ ┘ │ ─ ┼ ▶ ▼) for clean ASCII art.}

## Module Dependencies

{Show an ASCII dependency graph of modules touched by this epic:}

```
indicators/hurst.py ──▶ models/indicators.py ──▶ scoring/weights.py
                                                        │
analysis/performance.py ──▶ models/analytics.py         ▼
analysis/position_sizing.py ──────────────────▶ agents/orchestrator.py
analysis/valuation.py ──▶ models/valuation.py ──┘
analysis/correlation.py ──▶ models/correlation.py
```

{Adapt to actual modules. Show data flow direction with arrows.}

## Task Breakdown

| # | Task | Issue | Status | Commits |
|---|------|-------|--------|---------|
| 1 | {name} | #{num} | {status} | {count} |

## Metrics

{Only if retro.md exists. Otherwise omit this section entirely.}

- **Duration**: {wall_clock_time}
- **Effort**: {proxy_hours}h (estimation ratio: {ratio}x)
- **Quality**: {post_merge_fixes} post-merge fixes
- **Tests**: {planned} planned / {actual} delivered
- **Scope accuracy**: {percentage}

---

### 3. Output Summary

After the full recap, add a one-line summary:

```
Recap complete: {task_count} tasks, {commit_count} commits, {files_changed} files changed, {lines_added} lines added
```

## Error Recovery

- If epic branch not found in git: use issue-number grep to find commits. If no commits found,
  show "No git history available" in the What Changed section and skip Metrics.
- If PRD file not found: omit the "Problem" half of "Problem / Solution", show only "Solution".
- If retro.md not found: omit Metrics section entirely.
