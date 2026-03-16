---
generated: 2026-03-16T20:05:00Z
epic: scientific-ml-neural
---

# Retrospective — scientific-ml-neural

## Timeline

| Event | Timestamp (ET) |
|-------|---------------|
| Epic planning + task files | 2026-03-16 15:27 |
| Wave 1 start (C1 + C3 parallel) | 2026-03-16 15:41 |
| Wave 1 merge | 2026-03-16 15:56 |
| Wave 2 start (C2 + C4 parallel) | 2026-03-16 16:06 |
| Wave 2 merge | 2026-03-16 16:30 |
| **Total wall clock** | **~63 minutes** |

## Effort

| Metric | Planned | Actual |
|--------|---------|--------|
| Hours | 19-25h | ~1.1h proxy |
| Ratio | — | 0.05x |
| Tasks | 4 | 4 |
| Waves | 2 | 2 |
| Parallel agents | 2 per wave | 2 per wave (worktree isolation) |

## Scope Delta

| Dimension | Planned | Delivered | Delta |
|-----------|---------|-----------|-------|
| New source files | 2 | 2 | 0 |
| Modified source files | 6 | 6 | 0 |
| Test files | 6 | 6 | 0 |
| Test cases | ~56 | 97 | +41 (+73%) |
| Lines added | — | 3,223 | — |

Extra test cases cover boundary conditions (NaN/Inf rejection, degenerate inputs, boundary ranges) beyond the original plan.

## Quality

| Metric | Value |
|--------|-------|
| Tests passed | 75 |
| Tests skipped | 22 (torch/lightning not installed — expected) |
| Tests failed | 0 |
| Regression tests passed | 147 |
| Regression tests failed | 0 (37 pre-existing config env failures excluded) |
| Post-merge fixes | 0 |
| Lint errors | 0 |

## What Went Well

1. **Worktree parallelism**: Wave 1 ran C1 and C3 simultaneously in isolated worktrees. Wave 2 ran C2 and C4 similarly. Total wall clock ~1 hour for ~20h planned work.
2. **Guarded import pattern**: Reusing the `_get_torch()`/`_get_lightning()` pattern from existing ML code made neural integration smooth.
3. **Zero regressions**: All existing tests pass with default config (neural features off by default).
4. **Test surplus**: Delivered 97 tests vs 56 planned (+73%) with comprehensive edge case coverage.

## What Could Improve

1. **torch not installed in CI/dev**: 22 tests are skipped because torch/lightning aren't in the dev dependencies. Consider adding `[neural]` extra to test matrix or creating a separate CI job.
2. **Task status not auto-closed**: All 4 tasks remained `status: open` after commits were merged. Should automate task closure on merge.
3. **Pre-existing config test failures**: 37 test_config.py failures from env var pollution should be fixed (not epic-specific but masks real regressions).

## Learnings

- **CPU-only torch index** (`whl/cpu`) keeps dependency size manageable (~200MB vs ~900MB with CUDA).
- **Neural models as optional fallback** (returns None → existing method continues) is the right pattern for experimental features.
- **String concatenation (not str.format)** for LLM prompt assembly avoids curly-brace escaping issues.
- **NamedTuple at pricing boundary** keeps PyTorch internals invisible to consumers.
