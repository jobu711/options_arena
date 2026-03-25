---
epic: pipeline-wiring-fix
completed: 2026-03-25T04:30:00Z
---

# Retrospective: pipeline-wiring-fix

## Scope Summary

| Metric | Planned | Delivered | Delta |
|--------|---------|-----------|-------|
| Tasks | 10 | 10 | 0 (100%) |
| Waves | 3 | 3 | 0 |
| Planned hours | 29h | ~2.5h actual wall time | 0.09x (agent parallelism) |
| New tests | ~48 | 97 | +102% |
| Files changed | ~20 est. | 39 | +95% (tests drove count up) |
| Lines added | — | 2,836 | — |
| Lines removed | — | 85 | — |
| Commits | 10 | 9 (two tasks merged into one commit) | -1 |

## Execution Timeline

| Phase | Tasks | Parallelism | Notes |
|-------|-------|-------------|-------|
| Wave 1a | #805, #810 | 2 parallel + #813, #814 | Foundation + independent Wave 3 |
| Wave 1b | #806 | Sequential (blocked on #805) | Critical path |
| Wave 2 | #808, #812, #809, #811 | 4 parallel | All unblocked by #806 |
| Wave 2b | #807 | Sequential (blocked on #812) | Final task |

Peak parallelism: **4 agents** running simultaneously (Wave 1a launched 4; Wave 2 launched 4).

## Quality Assessment

- **Test coverage**: 97 new tests across 11 files (2x planned estimate of ~48)
- **Regressions**: 0
- **Pre-existing failures**: 1 (test_volatility_toolset — unrelated)
- **Lint delta**: -1 error (improved)
- **Post-merge fixes needed**: 0

## Scope Delta

- **Added**: Risk desk prompt injection (#807 expanded from synthesis-only to include risk desk)
- **Added**: `_load_tuned_weight_overrides()` in scan pipeline (#814 expanded to full DB integration)
- **Added**: CLI spread rendering integration in `commands.py` (#809 expanded from rendering function to command wiring)
- **Removed**: Nothing — all 10 planned tasks delivered

## What Went Well

1. **Envelope pattern worked perfectly** — `ScanEnrichment` model cleanly replaced flat params. Future enrichment is a single field addition.
2. **Agent parallelism** — 10 tasks completed with effective 4-way parallelism. Wave 3 independence let us start #813/#814 with Wave 1.
3. **Zero regressions** — all 1081 existing unit tests still pass.
4. **Test quality** — agents wrote 97 tests (2x estimate), with good edge case coverage (NaN defense, boundary values, None handling).

## What Could Improve

1. **Commit consolidation** — #810 got folded into #805's commit due to concurrent agent execution. Each task should have its own commit.
2. **Task status tracking** — task frontmatter stayed `open` until manual bulk update. Agents should update status on completion.
3. **Pre-existing test failure** — `test_volatility_toolset_has_four_tools` should be fixed separately (count hardcoded, actual tools = 5).

## Learnings

1. **Envelope models prevent wiring bugs** — the `ScanEnrichment` pattern is now the canonical way to pass scan→recommendation data. Document for future epics.
2. **Agent concurrency works well for non-conflicting file sets** — Wave 2 tasks touched different modules (CLI, frontend, agents, prompts) with no merge conflicts.
3. **Wave 3 independence is free parallelism** — always look for tasks with no dependencies that can piggyback on Wave 1.
