---
name: algo-audit
description: Fix 13 algorithmic correctness findings from comprehensive codebase audit
status: planned
created: 2026-03-08T00:22:14Z
updated: 2026-03-08T00:22:14Z
---

# PRD: Algorithmic Correctness Audit Fixes

## Executive Summary

A comprehensive algorithmic correctness audit across 14 systems (composite scoring,
normalization, direction classification, contract ranking, verdict synthesis, pricing,
indicators, outcome tracking, rate limiting, caching, and pipeline orchestration)
identified 13 findings. Core financial math is sound — BSM/BAW pricing, Greeks, IV
solvers, and annualization factors all match canonical references. The findings fall
into three categories: (1) incorrect data used for P&L calculation on expired contracts,
(2) scale-incoherent composite scoring in ad-hoc debate paths, and (3) cross-system
inconsistencies in NEUTRAL vote handling, floor values, and defensive guards.

## Problem Statement

### What problem are we solving?

1. **Expired contract P&L uses wrong stock price** — the outcome collector fetches the
   current stock price instead of the historical close on expiration day, causing
   incorrect ITM/OTM classification when collection runs days after expiry.

2. **Ad-hoc debate composite score is meaningless** — raw indicator signals (OBV ~50M,
   ATR% ~0.05) are passed to `composite_score()` which expects 0-100 percentile-ranked
   inputs, producing scores dominated by large-scale indicators.

3. **NEUTRAL vote dilution asymmetry** — `compute_agreement_score()` includes NEUTRAL
   agents in its denominator while bull/bear scores exclude them, creating paradoxical
   results (low agreement but perfect directional score).

4. **Missing NaN/Inf guards** — `iv_rank()` and `iv_percentile()` lack `isfinite()`
   checks, violating the project's NaN defense pattern.

5. **Retry starvation** — `fetch_with_retry()` holds semaphore slots during backoff
   sleep (up to 31s), blocking other requests unnecessarily.

### Why is this important now?

The outcome tracking system (`outcomes collect`) launched recently. The expired contract
bug (H1) silently produces incorrect P&L data that will accumulate over time, making
any future backtesting or strategy evaluation unreliable. The ad-hoc debate path (H2)
is the primary web UI flow — every user-initiated debate computes a misleading score.

## User Stories

### US-1: Accurate Expired Contract P&L

**As** an options analyst reviewing historical outcomes,
**I want** expired contract P&L to use the stock price on expiration day,
**so that** ITM/OTM classification and return percentages reflect reality.

**Acceptance Criteria:**
- AC-1.1: Expired contracts use historical OHLCV close on expiration date.
- AC-1.2: Falls back to current quote with warning if historical data unavailable.
- AC-1.3: Weekend/holiday expirations use the last trading day before expiration.

### US-2: Meaningful Ad-Hoc Composite Score

**As** a user running a single-ticker debate from the web UI,
**I want** the composite score to be on the same 0-100 scale as scan results,
**so that** score-based thresholds and comparisons are meaningful.

**Acceptance Criteria:**
- AC-2.1: Raw signals are normalized to 0-100 via domain-bound scaling before scoring.
- AC-2.2: Inverted indicators (bb_width, atr_pct, keltner_width) are flipped.
- AC-2.3: The score is logged as "single-ticker normalization" to distinguish from scan scores.

### US-3: Consistent Agreement Scoring

**As** a system producing debate verdicts,
**I want** agreement and bull/bear scores to use the same denominator logic,
**so that** confidence capping and score reporting are internally consistent.

**Acceptance Criteria:**
- AC-3.1: NEUTRAL agents are excluded from the agreement denominator.
- AC-3.2: All-NEUTRAL agents produce agreement = 0.0 (no directional consensus).
- AC-3.3: Existing tests updated to reflect new denominator.

### US-4: NaN-Safe Indicator Functions

**As** the scoring pipeline processing market data,
**I want** `iv_rank()` and `iv_percentile()` to handle NaN/Inf inputs safely,
**so that** non-finite values don't silently produce misleading results.

**Acceptance Criteria:**
- AC-4.1: `iv_rank()` returns 50.0 (neutral) for non-finite inputs.
- AC-4.2: `iv_percentile()` raises `InsufficientDataError` for non-finite `current_iv`.
- AC-4.3: `isfinite()` checks precede all arithmetic.

### US-5: Non-Blocking Retry

**As** the scan pipeline processing 500 tickers,
**I want** retry backoff to release the rate limiter semaphore during sleep,
**so that** transient failures on a few tickers don't block the entire pipeline.

**Acceptance Criteria:**
- AC-5.1: Semaphore is released before backoff sleep, re-acquired per attempt.
- AC-5.2: Random jitter (0.5x-1.0x) prevents synchronized retry storms.
- AC-5.3: All 8 call sites in market_data.py and options_data.py are migrated.

## Requirements

### Functional Requirements

**FR-1: Historical price for expired contracts (H1)**
- In `outcome_collector.py:_process_expired_contract()`, replace `fetch_quote()` with
  `fetch_ohlcv(ticker, period="5d")`, filter for bar on or before `contract.expiration`.
- Fallback to `fetch_quote()` with WARNING log if OHLCV unavailable.
- Use `OHLCV.close` (Decimal) as `exit_stock_price`.

**FR-2: Single-ticker normalization (H2)**
- Add `normalize_single_ticker(signals: IndicatorSignals) -> IndicatorSignals` to
  `scoring/normalization.py` using domain-bound linear scaling per indicator.
- Domain bounds dict maps each of 19 indicators to `(min, max)` expected range.
- Formula: `clamp((value - min) / (max - min) * 100, 0, 100)`.
- Apply `invert_indicators()` after normalization.
- Call in `api/routes/debate.py` at lines 112 and 356 before `calc_composite()`.

**FR-3: Consistent NEUTRAL exclusion (M1)**
- In `compute_agreement_score()`, change denominator from `len(agent_directions)` to
  `bullish_count + bearish_count`. Return 0.0 when all agents are NEUTRAL.

**FR-4: Retry-outside-limiter helper (M2)**
- Add `fetch_with_limiter_retry()` to `services/helpers.py` that acquires limiter
  per attempt, sleeps outside the limiter context.
- Migrate all 8 call sites in `market_data.py` (6) and `options_data.py` (2).

**FR-5: Composite floor attenuation (M3)**
- Change `_FLOOR_VALUE` from `1.0` to `0.5` in `scoring/composite.py:66`.
- Effect: `ln(0.5) = -0.693` — bottom-ranked tickers contribute negative signal
  rather than zero, creating a smooth boundary.

**FR-6: isfinite guards on IV functions (L1+L2)**
- `iv_rank()`: Guard all 3 inputs with `isfinite()`, return 50.0 if non-finite.
- `iv_percentile()`: Guard `current_iv` with `isfinite()`, raise `InsufficientDataError`.

**FR-7: Backoff jitter (L3)**
- Add `* (0.5 + random.random() * 0.5)` to delay in `fetch_with_retry()`.
- Also include jitter in the new `fetch_with_limiter_retry()`.

**FR-8: Word-boundary citation matching (L4)**
- Replace `label in combined` with `re.search(r'\b' + re.escape(label) + r'\b', combined)`
  in `compute_citation_density()`.

**FR-9: Explicit risk weight (L5)**
- Add `"risk": 0.0` to `AGENT_VOTE_WEIGHTS` with explanatory comment.

**FR-10: Consistent DTE clamping (L6)**
- Add `max(0, ...)` to active contract DTE at `outcome_collector.py:257`.

**FR-11: Documentation-only fixes (L7, L8)**
- L7: Add comment at `direction.py:85` explaining strict `>` is intentional.
- L8: Add comment at `cache.py:162` documenting accepted TOCTOU window.

### Non-Functional Requirements

- All fixes pass `uv run ruff check . --fix && uv run ruff format .`
- All fixes pass `uv run mypy src/ --strict`
- All existing tests pass (with updates for changed expectations)
- New tests added for each functional fix

## Success Criteria

| Metric | Target |
|--------|--------|
| Test suite green | All 3,921+ tests pass |
| New test coverage | 25+ new tests for audit fixes |
| isfinite() defense | iv_rank/iv_percentile guarded |
| Expired P&L accuracy | Historical close used, not current quote |
| Semaphore hold time | Max = single request duration (not 31s) |

## Constraints & Assumptions

### Constraints
- Module boundaries from CLAUDE.md must be respected.
- `services/` is the only layer touching external APIs.
- `scoring/` imports from `pricing/dispatch` only.
- Single-ticker normalization bounds are approximate — not equivalent to cross-universe percentile ranking.

### Assumptions
- `fetch_ohlcv(ticker, period="5d")` reliably returns data including the expiration date.
- Domain bounds for single-ticker normalization cover >95% of real market data.
- The sub-ms cache TOCTOU window is acceptable (no fix, document only).
- RSI strict `>` boundary is acceptable (no fix, document only).

## Out of Scope

- **Pricing model changes** — BSM/BAW formulas verified correct, no changes needed.
- **Greeks computation** — All Greek formulas verified against canonical references.
- **Annualization factor changes** — 252/365 usage verified correct across all sites.
- **Weight optimization** — Covered by signal-weights.md, not this audit.
- **Confidence calibration** — Covered by debate-calibration-audit.md.

## Dependencies

### Internal

| Dependency | Module | Required By |
|-----------|--------|-------------|
| `IndicatorSignals` model | `models/scan.py` | FR-2 (domain bounds per field) |
| `INVERTED_INDICATORS` | `scoring/normalization.py` | FR-2 (inversion after normalization) |
| `RateLimiter` | `services/rate_limiter.py` | FR-4 (limiter-aware retry) |
| `OHLCV` model | `models/market_data.py` | FR-1 (historical close) |

### External
- No new external dependencies required.

## Implementation Order

### Wave 0: Foundation Guards (4 issues, all S, parallel)
1. FR-6: isfinite guards on iv_rank/iv_percentile
2. FR-7: Backoff jitter
3. FR-11: Documentation (RSI boundary + cache TOCTOU comments)

### Wave 1: Core Logic Fixes (4 issues, parallel with Wave 0)
4. FR-1: Historical price for expired contracts (H1)
5. FR-5: Composite floor value change (M3)
6. FR-9: Explicit risk weight (L5)
7. FR-8: Word-boundary citation matching (L4)

### Wave 2: Agreement & Ad-Hoc (3 issues, depends on Wave 1/M3)
8. FR-3: NEUTRAL exclusion from agreement (M1)
9. FR-2: Single-ticker normalization for ad-hoc debate (H2)
10. FR-10: Consistent DTE clamping (L6)

### Wave 3: Retry Restructure (1 issue, depends on Wave 0/L3)
11. FR-4: Retry-outside-limiter helper (M2)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Domain bounds for single-ticker normalization miss edge cases | Medium | Low | Clamp to [0, 100]; log warning; values outside bounds still produce valid scores |
| Agreement score change affects downstream confidence capping | Medium | Medium | The agreement < 0.4 cap still applies; NEUTRAL-excluded scores are generally higher, reducing false caps |
| Composite floor change shifts score distribution | Low | Medium | Floor 0.5 vs 1.0 only affects bottom-ranked tickers; relative ordering preserved |
| Retry restructure introduces timing-sensitive bugs | Low | High | Comprehensive tests; semaphore acquire/release symmetry verified per attempt |

## Files to Modify

| File | Changes | Issues |
|------|---------|--------|
| `indicators/options_specific.py` | Add isfinite guards to iv_rank/iv_percentile | FR-6 |
| `services/helpers.py` | Add jitter; add fetch_with_limiter_retry() | FR-7, FR-4 |
| `scoring/direction.py` | Add design-decision comment | FR-11 |
| `services/cache.py` | Add TOCTOU acceptance comment | FR-11 |
| `services/outcome_collector.py` | Use historical close; consistent DTE clamp | FR-1, FR-10 |
| `scoring/composite.py` | Change _FLOOR_VALUE to 0.5 | FR-5 |
| `agents/orchestrator.py` | Fix agreement denominator; add risk weight | FR-3, FR-9 |
| `agents/_parsing.py` | Word-boundary citation matching | FR-8 |
| `scoring/normalization.py` | Add normalize_single_ticker() | FR-2 |
| `api/routes/debate.py` | Use normalized signals for ad-hoc composite | FR-2 |
| `services/market_data.py` | Migrate 6 call sites to fetch_with_limiter_retry | FR-4 |
| `services/options_data.py` | Migrate 2 call sites to fetch_with_limiter_retry | FR-4 |

## Test Changes

| Test File | Changes |
|-----------|---------|
| `tests/unit/indicators/test_options_specific.py` | +5 tests (NaN/Inf guards) |
| `tests/unit/services/test_helpers.py` | +3 tests (jitter, limiter retry) |
| `tests/unit/scoring/test_composite.py` | ~4 updated (floor value expectations) |
| `tests/unit/scoring/test_direction.py` | 0 (boundary tests already pass) |
| `tests/unit/agents/test_debate_protocol.py` | ~3 updated (NEUTRAL exclusion) |
| `tests/unit/agents/test_zero_enrichment.py` | ~2 updated (NEUTRAL exclusion) |
| `tests/unit/agents/test_parsing.py` | +3 tests (word-boundary citation) |
| `tests/unit/services/test_outcome_collector.py` | ~2 updated, +2 new (historical close) |
| `tests/unit/scoring/test_normalization.py` | +5 tests (single-ticker normalization) |
| `tests/unit/api/test_debate_routes.py` | +1 test (normalized ad-hoc composite) |
