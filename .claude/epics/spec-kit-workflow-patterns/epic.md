---
name: spec-kit-workflow-patterns
status: completed
created: 2026-03-24T13:01:32Z
progress: 100%
prd: .claude/prds/spec-kit-workflow-patterns.md
github: https://github.com/jobu711/options_arena/issues/786
---

# Epic: spec-kit-workflow-patterns

## Overview

Integrate three cherry-picked workflow patterns from GitHub's spec-kit (MIT) into Options
Arena's `.claude/` development infrastructure. All changes are markdown prompt/convention
edits — zero Python code, zero tests, zero migrations.

1. **Ambiguity taxonomy** — replace spec-analyzer Phase 3's 10-point checklist with 11-category
   taxonomy (10 from spec-kit + 1 OA-specific) with Impact x Uncertainty scoring, top 5 questions
2. **`[P]` parallel task markers** — machine-readable parallelism annotation derived from
   `depends_on` dependency graph, consumed by parallel-worker agent and humans
3. **`NEEDS CLARIFICATION` placeholders** — greppable structured markers with soft gates at
   both prd-parse (scans PRD) and epic-decompose (scans epic.md)

## Architecture Decisions

- **`depends_on` is the single source of truth** for task parallelism. Both `parallel: true`
  frontmatter and `[P]` markdown markers are derived views computed from the same dependency
  graph by epic-decompose. No authority conflict possible.
- **NEEDS CLARIFICATION gates at two boundaries**: prd-parse scans the PRD for requirement
  ambiguity; epic-decompose scans epic.md for architecture ambiguity. Same soft-gate mechanism
  (warn + user override) at both.
- **No Python code changes** — all modifications are `.claude/` markdown files (agent prompts,
  PM command templates, guides).
- **Backward compatible** — spec-analyzer Phases 1, 2, 4 are unchanged; only Phase 3 is
  enhanced. Existing epics/tasks are not retroactively modified.
- **Soft gates, not hard gates** — NEEDS CLARIFICATION warnings are user-overridable. `[P]`
  markers are advisory (agent can still serialize if unsure).

## Technical Approach

### Files Modified

| File | Change |
|------|--------|
| `.claude/agents/spec-analyzer.md` | Replace Phase 3 checklist with 11-category taxonomy + scoring |
| `.claude/agents/parallel-worker.md` | Add `[P]` marker parsing instructions |
| `.claude/commands/pm/epic-decompose.md` | Emit `[P]` markers; add NEEDS CLARIFICATION scan |
| `.claude/commands/pm/prd-parse.md` | Add NEEDS CLARIFICATION scan on PRD |
| `.claude/commands/pm/epic-status.md` | Report parallel vs sequential task counts |
| `.claude/commands/pm/epic-start.md` | Consume `[P]` markers for fan-out decisions |

### Files Created

| File | Purpose |
|------|---------|
| `.claude/guides/spec-kit-conventions.md` | Reference guide for all three conventions |

## Task Breakdown Preview

- [ ] [P] T1: Enhance spec-analyzer with 11-category ambiguity taxonomy + scoring
- [ ] [P] T2: Add `[P]` parallel marker convention to parallel-worker + PM commands
- [ ] [P] T3: Add NEEDS CLARIFICATION convention to prd-parse + epic-decompose
- [ ] T4: Create spec-kit-conventions.md reference guide (depends on T1, T2, T3)
- [ ] T5: Verify — run spec-analyzer on existing PRD, validate taxonomy output (depends on T1)

## Dependencies

- **None** — all changes are self-contained within `.claude/` markdown files
- No external library dependencies
- No prerequisite epics

## Success Criteria (Technical)

1. `spec-analyzer` output includes 11-category taxonomy coverage table with scored gaps
2. `spec-analyzer` questions use enhanced format (Category, Impact x Uncertainty, Recommended
   option, Alternatives)
3. `/pm:epic-decompose` emits `[P]` markers derived from `depends_on` analysis
4. `parallel-worker` agent can parse `[P]` markers to determine fan-out
5. `prd-parse` warns on `[NEEDS CLARIFICATION: ...]` markers in PRD (soft gate)
6. `epic-decompose` warns on `[NEEDS CLARIFICATION: ...]` markers in epic.md (soft gate)
7. `grep -r "NEEDS CLARIFICATION" .claude/` finds all open questions
8. `.claude/guides/spec-kit-conventions.md` documents all three conventions

## Tasks Created

- [ ] [P] #787 - Enhance spec-analyzer with 11-category ambiguity taxonomy and scoring
- [ ] [P] #788 - Add [P] parallel marker convention to parallel-worker and PM commands
- [ ] [P] #789 - Add NEEDS CLARIFICATION convention to prd-parse and epic-decompose
- [ ] #790 - Create spec-kit-conventions.md reference guide (depends on #787, #788, #789)
- [ ] #791 - Verify spec-analyzer taxonomy output on existing PRD (depends on #787)

Total tasks: 5
Parallel tasks: 3
Sequential tasks: 2
Estimated total effort: 8-12 hours

## Test Coverage Plan

Total test files planned: 0 (markdown-only epic — no Python code)
Total manual verification scenarios: 15

## Estimated Effort

- **5 tasks, all S/XS** — markdown edits only
- **Tasks 1-3 are fully parallel** (`[P]`)
- **Critical path**: T1 → T5 (taxonomy must exist before verification)
- **Total**: 1-2 days
