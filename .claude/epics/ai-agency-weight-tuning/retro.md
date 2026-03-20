# Retrospective — ai-agency-weight-tuning

**Epic**: Self-Improvement P1 — Weight Tuning (#606)
**Date**: 2026-03-20
**Branch**: `epic/ai-agency-weight-tuning`

## Effort

| Task | Planned | Actual (proxy) |
|------|---------|---------------|
| #608 learning/ module + relocate | 3-4h | ~15min |
| #610 indicator tuning algorithm | 3-4h | ~15min |
| #611 migration + data layer | 3-4h | ~10min |
| #607 orchestration + CLI | 4-6h | ~10min |
| #609 API endpoints | 5-7h | ~10min |
| **Total** | **18-25h** | **~1h** |

**Ratio**: ~0.05x (20x faster than planned). Estimates were for human-paced implementation sessions; AI agent completed sequentially in a single conversation.

## Scope Delta

| Planned | Delivered | Delta |
|---------|-----------|-------|
| 5 tasks | 5 tasks | On target |
| 20+ tests | 52 new tests | +160% |
| LearningDashboard.vue | Deferred | -1 frontend component |
| Outcome trigger wiring | Deferred | API trigger exists instead |

## Code Stats

- **29 files changed**, +2,357 / -125 lines
- **7 new source files** (learning module, API routes, migration)
- **6 new test files** with 52 test functions
- **1 post-verify bug fix** (missing SQL column in get_outcome_signal_pairs)

## Quality

- **110/110 tests pass** (52 new + 58 pre-existing)
- **0 lint errors** (ruff)
- **0 type errors** (mypy --strict on learning/)
- **1 bug caught** during verification (R12: missing SQL column)
- **0 post-merge fixes** (not yet merged)

## Learnings

1. **Relocating functions safely**: Re-export from the old location ensures backward compat. Identity-check tests (`assert agents_weights is learning_weights`) catch broken chains.

2. **Verification catches real bugs**: The `get_outcome_signal_pairs()` SELECT clause was missing a column the Python code referenced. Unit tests passed because they used mocked repos, but real-data execution would KeyError. The verification step caught this — validates the verify-loop workflow.

3. **`__all__` tests are fragile across tasks**: The module init `__all__` test broke twice as new exports were added in subsequent tasks. Consider making this test self-updating or checking `__all__` is a superset rather than exact match.

4. **ruff E402 on mid-file imports**: Moving re-exports inline (mid-file) triggers E402. The fix is to move imports to the top of the file and keep a comment at the original location. This is cleaner than `# noqa: E402`.

5. **asyncio.Lock mock differences**: `asyncio.Lock.acquire_nowait()` doesn't exist — the mock conftest provides `threading.Lock` semantics. Use `await lock.acquire()` instead. Check mock fixture types when writing route code.

## Deferred Work

- **LearningDashboard.vue**: Chart.js line chart showing weight evolution over time. API endpoints are ready — frontend is a standalone follow-up.
- **Outcome collection trigger**: The planned inline trigger after `collect_outcomes()` was replaced by the `POST /api/learning/weights/tune` endpoint. The trigger can be wired in a follow-up by calling `auto_tune_indicator_weights()` at the end of the CLI `outcomes collect` command.
