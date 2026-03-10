---
epic: pipeline-phase-extraction
completed: 2026-03-09T21:00:00Z
---

# Retro: pipeline-phase-extraction

## Timeline

| Commit | Time | Issue | Description |
|--------|------|-------|-------------|
| `5c46ebc` | 19:34 | #424 | Extract phase_universe.py + phase_scoring.py |
| `9aee9e3` | 19:36 | #426 | Extract phase_persist.py |
| `9ce1e16` | 19:39 | #425 | Extract phase_options.py |
| `2ad193f` | 20:02 | #427 | Slim pipeline.py to orchestrator |
| `dca90c5` | 20:22 | #428 | Final verification + CLAUDE.md update |

**Wall clock**: ~48 minutes (19:34 → 20:22)
**Proxy hours**: ~1.0h

## Effort: Planned vs Actual

| Task | Planned | Actual | Ratio |
|------|---------|--------|-------|
| #424 (phase_universe + phase_scoring) | 2-3h | ~5min | 0.04x |
| #425 (phase_options) | 3-4h | ~5min | 0.02x |
| #426 (phase_persist) | 1-2h | ~2min | 0.02x |
| #427 (slim pipeline) | 3-4h | ~22min | 0.10x |
| #428 (verification) | 1h | ~20min | 0.33x |
| **Total** | **10-14h** | **~1.0h** | **0.08x** |

## Scope Delta

- **Planned**: 5 tasks, 4 new files, 1 modified file, ~1,200 LOC relocated
- **Delivered**: 5 tasks, 4 new files, 1 slimmed file, 1 test import fix, 1,483 insertions / 1,093 deletions
- **Scope creep**: Callable override pattern in phase modules (~100 LOC) to preserve 30+ monkey-patching tests without modifying test files. Not in PRD but necessary for zero-test-change goal.

## Quality

- **Tests**: 312 scan tests pass, 23,815 full suite pass
- **Test modifications**: 1 file (import path change only)
- **Post-merge fixes**: 0
- **Lint**: ruff clean
- **Types**: mypy --strict clean (9 scan files, 118 project-wide)

## Deviations

1. **pipeline.py 352 LOC vs target <200**: Callable overrides for test patching added ~150 LOC. Acceptable trade-off vs modifying 30+ test files.
2. **Logger names**: Phase modules use `"options_arena.scan.pipeline"` instead of `__name__` to preserve test log capture. Minor deviation, justified.
3. **Regime constants renamed**: `_REGIME_BULL/BEAR/NEUTRAL` became `_REGIME_CRISIS_THRESHOLD/VOLATILE_THRESHOLD/MEAN_REVERTING_THRESHOLD` matching actual usage.

## Learnings

1. **Monkey-patching is the dominant constraint**: 30+ tests patch `pipeline` module namespace. This forced callable overrides in phase functions — a pattern worth documenting for future extractions.
2. **Parallel wave execution works well**: Wave 2 (#425 + #426) ran in parallel saving ~5 minutes. The dependency graph was clean enough for this.
3. **Pure mechanical refactoring is fast**: No design decisions needed — just copy, replace `self._*`, verify. Total agent time dominated by mypy/test verification, not coding.
4. **Logger name matters for tests**: Using `__name__` in extracted modules would change logger names, breaking tests that assert on log output. Using the original module's logger name preserves compatibility.

## Recommendations

- Consider adding direct unit tests for standalone phase functions (PRD mentions this as future work)
- The callable override pattern should be documented in `system-patterns.md` if reused
- pipeline.py could be further slimmed by removing callable overrides IF tests are updated to patch phase modules directly (future cleanup)
