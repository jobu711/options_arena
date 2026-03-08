---
name: next-command-redesign
status: backlog
created: 2026-03-08T18:06:26Z
progress: 0%
prd: .claude/prds/next-command-redesign.md
github: https://github.com/jobu711/options_arena/issues/385
---

# Epic: next-command-redesign

## Overview

Rewrite `.claude/commands/pm/next.md` to fix the AskUserQuestion rendering bug, add
multi-source backlog cross-referencing, introduce strategic vision suggestions, and
delegate heavy context gathering to a subagent. This is a single-file rewrite — no
Python source, models, or tests are modified.

## Architecture Decisions

1. **Prose-based tool invocation over JSON code fences.** Research confirmed that no other
   command in the PM system uses JSON code fences for tool parameters. All working commands
   use prose directives. The AskUserQuestion call will follow this established pattern.

2. **Agent delegation for context sweep.** Phase 2 will delegate git history, PRD scanning,
   and cross-referencing to an Explore subagent. Only a compact summary (~20 lines) returns
   to the main context, cutting context burn from ~25-30% to <15%.

3. **Multi-source shipped-feature detection.** Cannot rely on PRD `status` field alone
   (shipped PRDs like `liquidity-weighting` still say `status: planned`). Must cross-reference:
   archived epics dir, progress.md "Recently Completed", and codebase presence via glob/grep.

4. **Separate strategic suggestions from backlog.** Phase 3 output will have two distinct
   sections: "Backlog Items" (from PRDs/Future Work) and "Strategic Opportunities" (from
   capability/gap analysis). This ensures at least 1 novel suggestion even when backlog is empty.

5. **Keep ranking multiplier tables unchanged.** The Mode/Scope multiplier tables are correct
   and well-designed. Only the input (Phase 1) and data gathering (Phase 2) change.

## Technical Approach

This epic modifies a single markdown command file. There are no frontend components,
backend services, or infrastructure changes.

### File: `.claude/commands/pm/next.md` (154 lines → ~180 lines)

**Phase 1 rewrite (~20 lines):**
- Remove JSON code fence (lines 21-57)
- Remove text-before-tool instruction (line 14)
- Remove negative constraints (lines 15-16, 60)
- Add single positive directive leading with AskUserQuestion call
- Describe 3 questions as prose bullets with field names inline
- Gate Phase 2 with "AFTER the user answers"

**Phase 2 rewrite (~60 lines):**
- Wrap context sweep in Agent tool (Explore subagent) prose directive
- Subagent instructions: 2 git commands, PRD frontmatter reads, progress.md check,
  archived epics glob, codebase existence check per candidate
- Add explicit cross-referencing algorithm (3-source check before including a candidate)
- Ranking logic stays in main context (receives compact subagent summary)

**Phase 3 enhancement (~30 lines):**
- Split output into "Backlog Items" and "Strategic Opportunities"
- Add "Filtered out (already shipped)" section
- Add strategic suggestion guidance (capability analysis, gap analysis, industry patterns)
- Keep existing per-recommendation format (alignment, why now, effort, unblocks, reference)

## Implementation Strategy

### Single wave — 4 tasks, sequential

The file is small (154 lines) and the changes are interdependent (Phase 2 references
Phase 1 answers, Phase 3 references Phase 2 output). Tasks are ordered to build on each
other but can be done in a single session.

1. **Rewrite Phase 1** — Fix the critical AskUserQuestion bug
2. **Rewrite Phase 2** — Add Agent delegation + cross-referencing
3. **Enhance Phase 3** — Add strategic suggestions + shipped filter
4. **Manual verification** — Run `/pm:next` end-to-end, verify all success criteria

### Risk mitigation
- **Risk: Prose directives still don't trigger AskUserQuestion** — Mitigate by testing
  Phase 1 in isolation before proceeding. If prose doesn't work, escalate to investigate
  AskUserQuestion tool availability in command context.
- **Risk: Subagent returns too much data** — Mitigate by capping subagent output in the
  prompt ("Return a summary under 30 lines").

## Task Breakdown Preview

- [ ] Task 1: Rewrite Phase 1 — fix AskUserQuestion with prose-based directives
- [ ] Task 2: Rewrite Phase 2 — Agent-delegated context sweep with cross-referencing
- [ ] Task 3: Enhance Phase 3 — strategic suggestions section + shipped filter + output format
- [ ] Task 4: Manual verification — run `/pm:next` end-to-end, verify success criteria

## Dependencies

- **No external dependencies.** This is a markdown command file edit.
- **No internal dependencies.** No other PM commands reference or import `next.md`.
- **Prerequisite knowledge:** Research phase (complete) identified all patterns and conflicts.

## Success Criteria (Technical)

| Criterion | Verification |
|-----------|-------------|
| AskUserQuestion renders as interactive form | Manual: run `/pm:next`, observe form |
| Phase 2 runs only AFTER interview answers | Manual: observe execution order |
| No shipped features in recommendations | Manual: cross-check against progress.md |
| At least 1 strategic suggestion appears | Manual: inspect output |
| Context usage <15% for Phase 2 | Manual: observe remaining context after Phase 2 |
| Command completes in <60 seconds | Manual: time the execution |
| Output scannable in <30 seconds | Manual: read the output |

## Tasks Created

- [ ] #386 - Rewrite Phase 1 — fix AskUserQuestion with prose-based directives (parallel: false)
- [ ] #387 - Rewrite Phase 2 — Agent-delegated context sweep with cross-referencing (parallel: false)
- [ ] #388 - Enhance Phase 3 — strategic suggestions + shipped filter + output format (parallel: false)
- [ ] #389 - Manual verification — end-to-end success criteria (parallel: false)

Total tasks: 4
Parallel tasks: 0
Sequential tasks: 4 (linear dependency chain: #386 → #387 → #388 → #389)
Estimated total effort: 4.5 hours

## Test Coverage Plan

Total test files planned: 0 (markdown command file — no automated tests)
Total manual test cases planned: 17 across all tasks
Verification method: Manual `/pm:next` invocation

## Estimated Effort

- **Size: S (Small)** — 1-2 focused sessions
- **Files modified: 1** (`.claude/commands/pm/next.md`)
- **Lines changed: ~154** (full rewrite of existing 154-line file)
- **Critical path: Task 1** (if AskUserQuestion still doesn't render with prose, all other
  tasks are blocked until the root cause is resolved)
