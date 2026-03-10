---
epic: service-layer-unification
completed: 2026-03-10T17:00:00Z
---

# Retrospective: service-layer-unification

## Effort Summary

| Metric | Planned | Actual |
|--------|---------|--------|
| Total hours | 18-24h | ~0.6h (36 min wall clock) |
| Tasks | 7 | 7 |
| Waves | 4 sequential | 2 (foundation + parallel migrations + verification) |
| Parallelization | Up to 5 agents | 5 agents in parallel worktrees |

### Per-Task Breakdown (from agent durations)

| Task | Planned | Agent Duration | Commit |
|------|---------|---------------|--------|
| #439 ServiceBase ABC | 3-4h | ~8 min | `a5d32db` |
| #440 UniverseService | 2-3h | ~9 min | `c46071e` |
| #441 Fred + OpenBB | 2-3h | ~11 min | `0f7364e` |
| #443 MarketDataService | 3-4h | ~12 min | `f576b4c` |
| #444 Intel + FinDatasets | 3-4h | ~14 min | `0487d0d` |
| #438 OptionsDataService | 2-3h | ~15 min | `241b1d0` |
| #442 Integration + verify | 2-3h | ~18 min | `614e053` |

## Scope Delta

### Planned vs Delivered

| Feature | Planned | Delivered | Delta |
|---------|---------|-----------|-------|
| ServiceBase ABC | Full | Full | On target |
| 7/7 service migrations | All inherit | All inherit | On target |
| `_cached_fetch` adoption | ~25 of 29 blocks | 3 of 29 blocks (OpenBB only) | -22 blocks |
| `_yf_call` dedup | 2→1 | 2→1 (MarketData deleted) | On target |
| `_retried_fetch` adoption | ~18 sites | 8 sites (MarketData) | -10 sites |
| Boilerplate reduction | -300+ lines | -33 lines (services), +180 (base) | Shortfall |
| New tests | 30+ | 38 (30 unit + 8 integration) | +8 over target |
| Consumer code changes | 0 | 0 | On target |

### Root Cause of Shortfall

`_cached_fetch` was designed for `T: BaseModel` single-model serde. Most services cache:
- Lists of strings/dicts (UniverseService)
- Custom serde patterns (MarketDataService OHLCV, earnings dates)
- Scalar floats (FredService — excluded by design)
- Complex multi-tier patterns that don't fit the factory model

Agents correctly prioritized "all tests pass unchanged" over forcing patterns. The infrastructure exists and works (proven by OpenBB's 3 methods), but broader adoption would need either:
1. A `_cached_fetch_raw(key, factory, serializer, deserializer, ttl)` variant for non-model data
2. Individual service refactoring to use wrapper models

## Quality Assessment

| Metric | Value |
|--------|-------|
| Tests added | 38 |
| Existing tests broken | 0 |
| Post-merge fixes needed | 0 |
| mypy --strict | Clean (15 files) |
| ruff check | Clean |
| Consumer code changes | 0 |

## Learnings

### What Went Well
1. **Parallel worktree execution**: 5 agents running simultaneously cut wall-clock from ~87 min serial to ~36 min
2. **Zero test breakage**: Conservative approach (keep inline patterns that don't fit cleanly) preserved all 626 service tests
3. **Foundation-first pattern**: Building ServiceBase + full tests first gave all agents a stable base to inherit from
4. **Clear task decomposition**: Each agent had well-defined file scope — no merge conflicts

### What Could Improve
1. **Overestimated `_cached_fetch` coverage**: PRD projected 25/29 blocks but actual service cache patterns are more diverse than assumed. Recommendation: analyze actual serde patterns before estimating adoption numbers.
2. **Boilerplate reduction overestimated**: -300+ target assumed `_cached_fetch` would eliminate 8-15 lines per method × 25 methods. Actual reduction was mostly constructor/logger dedup (-2-5 lines × 7 services).
3. **Agent variability in approach**: Some agents used `self._log` (Intelligence, FinancialDatasets), others kept module-level `logger` (UniverseService). Could standardize with explicit instructions.

### Patterns to Reuse
- **Worktree isolation for parallel work**: Each agent in its own worktree, merge sequentially. Works cleanly when files don't overlap.
- **Foundation → parallel → verification wave structure**: Good pattern for "shared base + N independent consumers" refactors.
- **Conservative migration principle**: When target is "zero test changes", keep inline patterns rather than force-fitting shared abstractions.
