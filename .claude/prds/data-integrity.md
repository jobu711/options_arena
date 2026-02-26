---
name: data-integrity
description: End-to-end data integrity audit and hardening across all pipeline layers
status: backlog
created: 2026-02-26T08:56:43Z
---

# PRD: data-integrity

## Executive Summary

Options Arena processes market data through a multi-layer pipeline (services → indicators → scoring → scan → debate → persistence). A code audit has identified **concrete data integrity gaps** where malformed, missing, or zero-value data can silently propagate through the system, producing incorrect scores, misleading AI debate inputs, and corrupted persistence records.

This PRD defines a comprehensive data integrity hardening initiative that adds validation at model boundaries, service ingestion points, indicator-to-scoring handoffs, and debate context construction. The goal is **fail-fast on bad data** rather than silent degradation.

## Problem Statement

### What problem are we solving?

Three categories of data integrity gaps exist today:

1. **Model boundary validators are missing or incomplete.** The `OHLCV` model has zero validators — malformed candles (high < low, zero prices, negative volume) pass through to indicators and pricing unchallenged. `OptionGreeks.theta` and `.rho` lack `math.isfinite()` defense, allowing NaN/Inf to leak from pricing edge cases into debate agents.

2. **Service layer accepts invalid data via zero-fallback patterns.** `market_data.py` converts `None` prices to `Decimal("0")` instead of raising `TickerNotFoundError`. A zero-price Quote flows into IV solvers, scoring denominators, and `MarketContext` — corrupting everything downstream.

3. **Silent data loss at pipeline handoffs.** Missing indicator values become `0.0` (not NaN or an error) in `MarketContext`, so debate agents receive `"IV_RANK: 0.0"` when the actual value was unavailable. Cache entries lack negative-TTL rejection. No completeness check validates that debate inputs meet minimum data requirements before LLM invocation.

### Why is this important now?

- The system is feature-complete (v1.5.0) and about to see real usage. Data integrity bugs under real market conditions are harder to diagnose than during development.
- Every downstream feature (additional LLM providers, web UI, real-time streaming) amplifies the blast radius of upstream data corruption.
- Several gaps (zero-price fallback, missing OHLCV validators) are **HIGH severity** — they can produce financially misleading output.

## User Stories

### US-1: Operator encounters bad market data
**As** an operator running `options-arena scan`,
**I want** the system to reject invalid market data at ingestion (zero prices, malformed candles),
**so that** I get a clear error message instead of silently incorrect scan results.

**Acceptance Criteria:**
- Fetching a ticker with zero or negative price raises `TickerNotFoundError` with a descriptive message
- OHLCV candles with high < low, or prices ≤ 0, are rejected at model construction
- The scan pipeline logs the rejection and continues to the next ticker (batch isolation preserved)

### US-2: Debate receives incomplete context
**As** an operator running `options-arena debate AAPL`,
**I want** the system to validate that MarketContext has sufficient data before invoking AI agents,
**so that** agents don't reason from placeholder zeros or missing indicators.

**Acceptance Criteria:**
- MarketContext construction logs a warning when critical fields (iv_rank, rsi_14, atm_iv_30d) are unavailable
- Missing indicators are represented as `None` or NaN (not silently converted to 0.0)
- A minimum completeness threshold is enforced: debate proceeds only when ≥ 60% of context fields are populated; otherwise falls back to data-driven verdict with a logged explanation

### US-3: Greeks propagate NaN from pricing edge case
**As** a developer debugging a bad debate result,
**I want** OptionGreeks to reject NaN/Inf values at construction,
**so that** pricing edge cases are caught immediately rather than propagating silently to agents.

**Acceptance Criteria:**
- `theta` and `rho` fields have `math.isfinite()` validators matching the existing pattern for `gamma` and `vega`
- If a pricing function produces NaN theta/rho, the error is caught at OptionGreeks construction and logged

### US-4: Cache serves stale or corrupt data
**As** an operator,
**I want** cache entries to be validated for freshness and TTL sanity,
**so that** I never get stale market data during an active scan.

**Acceptance Criteria:**
- Cache `set()` rejects negative TTL values with a clear error
- Cache `get()` never returns data older than the configured TTL (existing behavior, verified by tests)

## Requirements

### Functional Requirements

#### FR-1: OHLCV Candle Integrity Validators (HIGH)
**File:** `src/options_arena/models/market_data.py`

Add to the `OHLCV` model (Context7-verified: `field_validator` mode="after" and `model_validator` mode="after" both work on `ConfigDict(frozen=True)` models — they validate without mutation):
- `field_validator` on `open`, `high`, `low`, `close`, `adjusted_close`: prices must be `> Decimal("0")` and finite (reject `Decimal("Inf")`, `Decimal("NaN")`)
- `field_validator` on `volume`: must be `>= 0`
- `model_validator(mode="after")` returning `Self`: `high >= low`, `low <= open <= high`, `low <= close <= high`

#### FR-2: OptionGreeks NaN/Inf Defense on Theta and Rho (MEDIUM)
**File:** `src/options_arena/models/options.py`

Add `field_validator` on `theta` and `rho` with `math.isfinite()` check, matching the existing validator pattern used for `gamma` and `vega`.

#### FR-3: Reject Zero Prices at Service Ingestion (HIGH)
**File:** `src/options_arena/services/market_data.py`

Context7-verified: yfinance `Ticker.info` returns `float` for price fields (`lastPrice`, `previousClose`, `open`, `dayHigh`, `dayLow`) and `int` for `volume`. Fields return `None` when data is unavailable (delisted, pre-market). `Ticker.fast_info` has the same shape.

- In `fetch_quote()`: replace `safe_decimal(price_raw) or Decimal("0")` with a check that raises `TickerNotFoundError` when price is None or ≤ 0. Bid/ask may legitimately be zero (illiquid contracts).
- In `fetch_ticker_info()`: same treatment for `current_price` — reject None/zero, raise `TickerNotFoundError`.

#### FR-4: MarketContext Completeness Validation (MEDIUM)
**File:** `src/options_arena/models/analysis.py` and `src/options_arena/agents/orchestrator.py`

- In `build_market_context()`: replace `... if x is not None else 0.0` with `... if x is not None else None` for indicator fields. Change field types to `float | None` where appropriate.
- Add a `completeness_ratio()` method or utility that counts populated vs total context fields.
- Log a warning when completeness < 80%. Abort debate (use data-driven fallback) when completeness < 60%.

#### FR-5: Indicator NaN Propagation Guard (LOW)
**File:** `src/options_arena/scoring/normalization.py` (already correct — verify with tests)

- Verify existing `math.isfinite()` guards in normalization catch all NaN from indicators.
- Add explicit test cases for fully-NaN indicator series to confirm graceful handling.

#### FR-6: Cache TTL Validation (LOW)
**File:** `src/options_arena/services/cache.py`

- In `set()`: reject `ttl < 0` with `ValueError`.

#### FR-7: Debate Input Quality Gate (MEDIUM)
**File:** `src/options_arena/agents/orchestrator.py`

- Before invoking bull agent, validate that `MarketContext` meets minimum data requirements.
- If validation fails, skip LLM debate and return data-driven fallback with `is_fallback=True` and a reason string.

### Non-Functional Requirements

#### NFR-1: Performance
- All new validators are Pydantic field/model validators — they execute during model construction with negligible overhead (microseconds per object).
- No additional API calls or I/O introduced.

#### NFR-2: Backwards Compatibility
- Existing tests must continue to pass with valid data. Only tests that were constructing models with invalid data (e.g., zero prices in test fixtures) need updating.
- The `MarketContext` field type changes (`float` → `float | None`) may require updates in agent prompt formatting and CLI rendering.

#### NFR-3: Error Observability
- Every validation rejection must produce a log message at WARNING or ERROR level.
- Log messages include: field name, invalid value, expected constraint, and ticker symbol where available.

#### NFR-4: Test Coverage
- Each new validator requires:
  - Positive test (valid data passes)
  - Negative test (invalid data raises `ValidationError`)
  - Edge case test (boundary values: exactly zero, exactly at limit)
- Estimated: ~40-60 new tests across models, services, and agents.

## Success Criteria

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Zero-price propagation | 0 instances | `Decimal("0")` never appears in Quote.price or TickerInfo.current_price after ingestion |
| OHLCV integrity | 100% candle validity | model_validator rejects all impossible candles |
| Greeks NaN leaks | 0 instances | All 5 Greeks fields have `math.isfinite()` validators |
| MarketContext silent zeros | 0 instances | No indicator field silently defaults to 0.0 |
| Test coverage | ≥40 new tests | `pytest --co -q` count before/after |
| Existing tests | 0 regressions | All 1402 existing tests pass |

## Constraints & Assumptions

### Constraints
- **Pydantic v2 only** — all validators use `field_validator` / `model_validator` syntax (not v1 `@validator`)
- **No new dependencies** — all validation uses stdlib (`math`, `decimal`) and Pydantic
- **Frozen models** — OHLCV and OptionGreeks are `frozen=True`; model_validators must use `mode="after"` (not mutate)
- **Test fixtures** — some existing tests may construct models with intentionally minimal/zero data; these need audit and update

### Assumptions
- `safe_decimal()` returns `Decimal | None` (never raises) — this is verified in existing code
- yfinance occasionally returns None for prices on delisted or pre-market tickers — this is expected and should raise, not fallback
- Debate agents can handle `None` indicator fields in context formatting (requires formatting update)

## Out of Scope

- **Schema migrations** — no SQLite schema changes; this is validation-only
- **New indicator functions** — not adding indicators, only validating existing outputs
- **Rate limiting changes** — token bucket and semaphore logic is out of scope
- **Service retry logic** — `fetch_with_retry()` behavior unchanged
- **API response format changes** — external API shapes (yfinance, FRED) are not modified
- **Web UI validation** — no web UI exists yet; CLI-only scope
- **Options chain validation** — option contract bid/ask/strike validation is deferred (separate PRD)

## Dependencies

### Internal
- **Models module** (`models/`) — primary target for validator additions
- **Services module** (`services/market_data.py`) — ingestion guard changes
- **Agents module** (`agents/orchestrator.py`) — MarketContext construction and quality gate
- **Test suite** (`tests/`) — fixture updates and new test cases

### External
- None — all changes are internal validation logic using existing dependencies

## Implementation Notes

### Suggested Epic Decomposition

| Issue | Title | Priority | Estimated Tests |
|-------|-------|----------|-----------------|
| 1 | OHLCV candle integrity validators | HIGH | ~15 |
| 2 | OptionGreeks theta/rho NaN defense | HIGH | ~5 |
| 3 | Reject zero prices in market_data.py | HIGH | ~8 |
| 4 | MarketContext completeness validation | MEDIUM | ~10 |
| 5 | Debate input quality gate | MEDIUM | ~6 |
| 6 | Cache TTL negative check | LOW | ~3 |
| 7 | Test fixture audit and cleanup | MEDIUM | ~0 (updates only) |

### Risk: Test Fixture Breakage
Many existing tests may construct models with zero or placeholder values. The test fixture audit (issue 7) should run early to identify which tests need updating before validators are added. Suggested approach: add validators behind a feature flag first, run full test suite, identify failures, fix fixtures, then enable validators permanently.

Alternatively: audit test fixtures first (issue 7), then add validators — no feature flag needed.
