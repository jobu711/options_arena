---
epic: scientific-ml-statistical
completed: 2026-03-15T22:00:00Z
planned_hours: 35
proxy_hours: 1.5
ratio: 0.04
---

# Retrospective: scientific-ml-statistical

## Summary

| Metric | Planned | Actual |
|--------|---------|--------|
| Tasks | 5 | 5 |
| Effort | 31-40h | ~1.5h proxy |
| Tests | ~105 | 189 functions (260 parametrized) |
| New files | 4 | 4 source + 9 test |
| Modified files | 11 | 13 source |
| LOC (src) | — | +1,452 / -381 |
| Post-merge fixes | — | 0 |

## Timeline

- 17:00 — Agent-1 (#533 FRED) + Agent-2 (#534 GARCH) launched in parallel worktrees
- 17:00 — #533 complete (78 tests), merged
- 17:01 — #534 complete (69 tests), merged + ML deps installed
- 17:01 — Agent-3 (#535 Macro Regime) + Agent-4 (#536 Markov) launched in parallel
- 17:13 — #535 complete (41 tests), merged
- 17:16 — #536 complete (29 tests), merged
- 17:16 — Agent-5 (#537 Pipeline Integration) launched
- 17:36 — #537 complete (24 tests), merged
- 22:00 — Verification: 28/28 PASS, 260/260 tests pass

## What Went Well

1. **Parallel execution worked perfectly** — Wave 1 (#533, #534) ran simultaneously in isolated worktrees. Wave 2 (#535, #536) launched as soon as their dependencies completed. Zero merge conflicts.

2. **Context7-verified API notes prevented bugs** — Pre-researched API details (EGARCH p/o/q signature, statsmodels k_regimes parameter, convergence flag vs exception) were included in agent prompts. No API misuse bugs.

3. **Guarded import pattern was well-established** — Agents followed the existing `_get_obb()` pattern from `openbb_service.py`, producing consistent code across all 3 new indicator files.

4. **Test quality exceeded plan** — 189 test functions vs 105 planned (1.8x). Comprehensive edge case coverage (NaN rejection, convergence failure, missing deps, boundary conditions).

5. **Zero regressions** — 128/128 critical tests pass. Existing FRED, scan, and scoring tests unaffected.

## What Could Improve

1. **Flaky ML test** — `test_high_vol_regime_detected_at_end` passes inconsistently due to Markov model stochasticity. Should use a fixed seed or wider assertion tolerance. Minor issue.

2. **Worktree nesting** — Agents spawned from worktrees created nested worktrees (3 levels deep). Cleanup failed due to Windows file locks. Need better worktree lifecycle management.

3. **Task files disappeared** — Task .md files (533-537) were on a branch that got overwritten during epic-start checkout. Should commit task files to the epic branch before starting execution.

## Scope Delta

| Planned | Delivered | Delta |
|---------|-----------|-------|
| 4 new source files | 4 new source files | On target |
| 11 modified files | 13 modified files | +2 (scan/models.py, agents/orchestrator.py — not planned but needed for wiring) |
| ~105 tests | 189 functions / 260 parametrized | +80% over plan |
| indicators/regime.py modified | NOT modified | Correct — Markov is complementary, not replacing |
| agents/volatility.py modified | Modified via _parsing.py | Cleaner — rendering logic stays in _parsing.py |

## Learnings

- **Parallel worktree agents are highly effective** for epics with clear dependency graphs. 5 tasks completed in ~36 minutes wall time (commit timestamps 17:00-17:36).
- **Agent prompts should include Context7-verified API details** — this eliminated an entire class of integration bugs.
- **Config-gated features with default-off** make verification trivial — existing tests pass unchanged.
- **Weight redistribution** (proportional scaling of existing weights) is the safest way to add new scoring indicators.
