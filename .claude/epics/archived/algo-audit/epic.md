---
name: algo-audit
status: backlog
created: 2026-03-08T00:32:08Z
progress: 0%
prd: .claude/prds/algo-audit.md
github: https://github.com/jobu711/options_arena/issues/354
---

# Epic: algo-audit

## Overview

Fix 13 algorithmic correctness findings from a comprehensive codebase audit. Core
financial math (BSM/BAW, Greeks, IV solvers, annualization) is verified correct — all
findings are edge-case guards, cross-system inconsistencies, and one significant P&L
accuracy bug in the outcome collector. Changes span indicators, scoring, agents, services,
and the API layer. No new dependencies required.

## Architecture Decisions

- **Historical close via existing OHLCV model**: Reuse `fetch_ohlcv()` already in
  `market_data.py` — no new service methods needed. Filter bars by date, fallback to
  `fetch_quote()` with warning.
- **Domain-bound normalization over percentile ranking**: Single-ticker debates lack a
  cross-universe distribution. Use static domain bounds with linear scaling and clamping
  to [0, 100]. Not equivalent to scan percentile ranks, but produces meaningful 0-100 scores.
- **Limiter-aware retry as new helper**: Rather than modifying `fetch_with_retry()` internals,
  add `fetch_with_limiter_retry()` alongside it. Migrate call sites incrementally.
- **NEUTRAL exclusion simplification**: Denominator change in `compute_agreement_score()`
  is a 2-line fix. All-NEUTRAL → 0.0 agreement (no directional consensus).

## Technical Approach

### Indicators (FR-6)
- Add `math.isfinite()` guards to `iv_rank()` and `iv_percentile()` in
  `indicators/options_specific.py`. Return neutral (50.0) or raise `InsufficientDataError`.

### Scoring (FR-2, FR-5)
- `scoring/composite.py`: Change `_FLOOR_VALUE` from 1.0 to 0.5.
- `scoring/normalization.py`: Add `normalize_single_ticker()` with domain bounds dict
  for all 19 indicator fields. Apply `invert_indicators()` after scaling.

### Agents (FR-3, FR-8, FR-9)
- `agents/orchestrator.py`: Fix agreement denominator (exclude NEUTRAL); add explicit
  `"risk": 0.0` weight.
- `agents/_parsing.py`: Word-boundary regex for citation matching.

### Services (FR-1, FR-4, FR-7, FR-10)
- `services/helpers.py`: Add jitter to `fetch_with_retry()`; add `fetch_with_limiter_retry()`.
- `services/outcome_collector.py`: Use historical OHLCV close for expired contracts;
  add `max(0, ...)` DTE clamp for active contracts.
- `services/market_data.py` + `options_data.py`: Migrate 8 call sites to new helper.

### API (FR-2)
- `api/routes/debate.py`: Call `normalize_single_ticker()` before `calc_composite()`
  in ad-hoc debate paths.

### Documentation (FR-11)
- `scoring/direction.py`: Comment explaining strict `>` boundary is intentional.
- `services/cache.py`: Comment documenting accepted TOCTOU window.

## Implementation Strategy

All fixes are localized — no cross-cutting architectural changes. The 4-wave structure
from the PRD maps naturally to 8 tasks that can be parallelized within waves.

Testing: ~25 new tests + ~11 updated expectations. Each task includes its own test changes.

## Task Breakdown Preview

- [ ] Task 1: isfinite guards on iv_rank/iv_percentile + documentation comments (FR-6, FR-11)
- [ ] Task 2: Backoff jitter in fetch_with_retry (FR-7)
- [ ] Task 3: Historical close for expired contracts + DTE clamping (FR-1, FR-10)
- [ ] Task 4: Composite floor value + explicit risk weight (FR-5, FR-9)
- [ ] Task 5: Word-boundary citation matching (FR-8)
- [ ] Task 6: NEUTRAL exclusion from agreement denominator (FR-3)
- [ ] Task 7: Single-ticker normalization for ad-hoc debate (FR-2)
- [ ] Task 8: Retry-outside-limiter helper + call site migration (FR-4)

## Dependencies

### Between Tasks
- Tasks 1-5 are independent (Wave 0 + Wave 1, fully parallel)
- Task 6 (agreement) independent of others
- Task 7 (normalization) independent but benefits from Task 4 (floor) being done first
- Task 8 (retry restructure) depends on Task 2 (jitter) being done first

### Internal Module Dependencies
| Dependency | Module | Required By |
|-----------|--------|-------------|
| `IndicatorSignals` model | `models/scan.py` | Task 7 |
| `INVERTED_INDICATORS` | `scoring/normalization.py` | Task 7 |
| `RateLimiter` | `services/rate_limiter.py` | Task 8 |
| `OHLCV` model | `models/market_data.py` | Task 3 |

### External
- No new external dependencies required.

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Test suite green | All 3,921+ tests pass |
| New test coverage | 25+ new tests |
| isfinite() defense | iv_rank/iv_percentile guarded |
| Expired P&L accuracy | Historical OHLCV close used |
| Semaphore hold time | Max = single request duration |
| Lint + typecheck | ruff + mypy --strict clean |

## Estimated Effort

- **8 tasks**, most are S-sized (1-2 file changes + tests)
- Task 7 (normalization) and Task 8 (retry migration) are M-sized
- All tasks parallelizable in 2-3 waves
- Critical path: Task 2 → Task 8 (jitter before retry restructure)

## Tasks Created

- [ ] #356 - isfinite guards on IV functions + documentation comments (parallel: true)
- [ ] #357 - Backoff jitter in fetch_with_retry (parallel: true)
- [ ] #358 - Historical close for expired contracts + DTE clamping (parallel: true)
- [ ] #359 - Composite floor value + explicit risk weight (parallel: true)
- [ ] #360 - Word-boundary citation matching (parallel: true)
- [ ] #361 - NEUTRAL exclusion from agreement denominator (parallel: true)
- [ ] #362 - Single-ticker normalization for ad-hoc debate (parallel: true)
- [ ] #363 - Retry-outside-limiter helper + call site migration (parallel: false, depends: #357)

Total tasks: 8
Parallel tasks: 7
Sequential tasks: 1 (#363 depends on #357)
Estimated total effort: 14-19 hours

## Test Coverage Plan

Total test files planned: 7
Total test cases planned: ~28 (22 new + ~6 updated)
