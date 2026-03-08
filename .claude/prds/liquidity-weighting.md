---
name: liquidity-weighting
description: Add gradient liquidity scoring to composite and contract selection, replacing binary pass/fail filters with continuous signals
status: planned
created: 2026-03-08T14:20:16Z
---

# PRD: liquidity-weighting

## Executive Summary

Options Arena currently uses binary gates (min OI, min volume, max spread %) to filter
option contracts but assigns no gradient quality score based on liquidity. A contract with
OI=101 and 29% spread ranks identically to one with OI=50,000 and 0.3% spread. This PRD
adds two liquidity indicators — **spread percentage of mid** and **open interest depth** —
to the composite scoring system, plus a **liquidity score multiplier** for contract-level
tiebreaking in `select_by_delta()`. The result: tickers with highly liquid option chains
rank higher, and within a ticker, the most liquid delta-appropriate contract wins.

## Problem Statement

### What problem are we solving?

The scan pipeline's Phase 3 applies hard filters (OI >= 100, volume >= 1, spread <= 30%)
that either pass or reject contracts with no middle ground. Two tickers scoring identically
on technicals can produce vastly different trade execution experiences — one with tight
spreads and deep books, the other barely clearing thresholds. Users who act on
recommendations may face significant slippage on illiquid contracts.

### Why is this important now?

- **Half-built infrastructure exists**: `spread_quality` field is declared on
  `IndicatorSignals` (line 104, `scan.py`) and `compute_spread_quality()` exists in
  `indicators/options_specific.py` — but neither is wired into the pipeline. This is
  unfinished work ready to be completed.
- **The composite score drives top-N selection**: Without liquidity in the composite, the
  top 50 tickers may include illiquid names that would rank lower with proper weighting.
- **Outcome tracking is live**: With `OutcomeCollector` tracking P&L at T+1/5/10/20, we
  can measure whether liquidity-weighted recommendations produce better realized outcomes.

## User Stories

### US-1: Scanner user gets better-ranked results
**As** a scan user, **I want** tickers with liquid option chains to rank higher in scan
results **so that** the top-N recommendations are more tradeable.

**Acceptance criteria:**
- Two tickers with identical technical scores but different option chain liquidity produce
  different composite scores
- The ticker with tighter spreads and deeper OI ranks higher
- Existing scans without liquidity data still load and score correctly (backward compat)

### US-2: Contract selection favors liquidity
**As** a user reviewing a recommended contract, **I want** the system to prefer the most
liquid contract near the delta target **so that** I face less slippage when entering the
trade.

**Acceptance criteria:**
- When two contracts are equally close to the delta target, the one with better liquidity
  (tighter spread, higher OI) is selected
- The liquidity multiplier does not override delta proximity — a contract much closer to
  target delta still wins even if less liquid
- Single-contract scenarios are unaffected

### US-3: Single-ticker debate uses liquidity scoring
**As** a user running a single-ticker debate (no universe scan), **I want** liquidity
indicators to be computed and normalized using domain bounds **so that** the debate context
includes liquidity quality information.

**Acceptance criteria:**
- `normalize_single_ticker()` handles the two new indicators with appropriate domain bounds
- Inversion is applied to spread % (lower = better)
- Missing liquidity data produces `None`, not a crash

## Requirements

### Functional Requirements

#### FR-1: Two new liquidity indicators on IndicatorSignals

| Field | Type | Direction | Formula | Domain Bounds |
|-------|------|-----------|---------|---------------|
| `chain_spread_pct` | `float \| None` | Lower = better (INVERTED) | OI-weighted average of `(ask - bid) / mid * 100` across all contracts in the recommended expiration's chain | (0.0, 30.0) |
| `chain_oi_depth` | `float \| None` | Higher = better | `log10(total_oi + 1)` across all contracts in the recommended expiration's chain | (0.0, 6.0) |

**Why these signals:**
- `chain_spread_pct`: Directly measures cost-to-trade. Transforms the existing 30% hard
  gate into a gradient. OI-weighting prevents illiquid far-OTM strikes from dominating.
- `chain_oi_depth`: Measures market depth. `log10` compresses the wide OI range
  (100 → 2.0, 10,000 → 4.0, 1,000,000 → 6.0) into a scoreable scale. Complements
  spread % by capturing depth vs. cost.

**Rejected signals:**
- *Volume/OI ratio*: Noisy intraday — early-morning scans show artificially low turnover.
- *Dollar volume*: Penalizes low-priced options that may still be highly liquid (high OI,
  tight spread). Price bias is undesirable.
- *Historical option volume trend*: Requires 30 days of historical option data not
  available in the current pipeline (violates constraint: no new API calls).

#### FR-2: New "Liquidity" composite weight category

Add a `liquidity` category to `INDICATOR_WEIGHTS` with total weight **0.06** (moderate
influence). Redistribute by scaling down existing categories proportionally:

| Category | Current | New | Change |
|----------|---------|-----|--------|
| Oscillators | 0.17 | 0.16 | -0.01 |
| Trend | 0.20 | 0.19 | -0.01 |
| Volatility | 0.14 | 0.13 | -0.01 |
| Volume | 0.15 | 0.14 | -0.01 |
| Moving Averages | 0.12 | 0.12 | — |
| Options | 0.22 | 0.20 | -0.02 |
| **Liquidity** | — | **0.06** | **+0.06** |
| **Total** | **1.00** | **1.00** | |

Individual weight allocation within the new category:
- `chain_spread_pct`: **0.04** (cost-to-trade is the primary liquidity signal)
- `chain_oi_depth`: **0.02** (depth is complementary but secondary)

Weight redistribution within existing categories (specific indicator adjustments):
- `rsi`: 0.07 → 0.065
- `adx`: 0.07 → 0.065
- `atr_pct`: 0.05 → 0.045
- `obv`: 0.05 → 0.045
- `iv_rank`: 0.06 → 0.05
- `iv_percentile`: 0.06 → 0.05
- All others: unchanged

#### FR-3: Contract-level liquidity score multiplier

In `select_by_delta()`, after sorting by delta proximity, apply a liquidity quality
multiplier as a tiebreaker:

```
liquidity_score = (1 - spread_pct / max_spread_pct) * 0.7 + min(log10(oi + 1) / 4, 1.0) * 0.3
effective_distance = delta_distance / max(liquidity_score, 0.01)
```

Where:
- `spread_pct = float(contract.spread / contract.mid)` (0 when mid=0, handled by zero-bid exemption)
- `oi = contract.open_interest`
- `max_spread_pct` from `PricingConfig` (default 0.30)
- `liquidity_score` range: ~[0.0, 1.0] — higher = more liquid
- Division by `liquidity_score` amplifies the delta distance for illiquid contracts,
  making them rank lower — but only as a tiebreaker when delta distances are similar

**Key behavior:** A contract at delta distance 0.01 with poor liquidity (score 0.3) gets
effective distance 0.033 — still beats a contract at delta distance 0.10 with perfect
liquidity (effective distance 0.10). Delta proximity remains dominant.

#### FR-4: Pipeline wiring in scan/indicators.py

Compute `chain_spread_pct` and `chain_oi_depth` during Phase 3
(`_process_ticker_options()`) after chain fetch and before contract recommendation.
Attach to `IndicatorSignals` so they participate in composite re-scoring if/when Phase 3
re-scoring is implemented.

The chain data is already available as `list[OptionContract]` at the point where
`filter_contracts()` is called — no new API calls needed.

#### FR-5: Existing `spread_quality` field cleanup

The existing `spread_quality` field on `IndicatorSignals` and `compute_spread_quality()`
in `indicators/options_specific.py` compute absolute dollar spread (not percentage).
Options:
- **Repurpose**: Rename/redefine `spread_quality` → `chain_spread_pct` with the new
  percentage-based formula, or
- **Replace**: Keep `spread_quality` as-is (dead field), add `chain_spread_pct` as new

**Decision: Replace.** `spread_quality` remains a dead DSE field. The two new fields
(`chain_spread_pct`, `chain_oi_depth`) are distinct, purpose-built indicators with clear
semantics. No need to retrofit the old function.

### Non-Functional Requirements

#### NFR-1: Performance
- Chain aggregation (spread pct, OI sum) is O(n) per chain — negligible vs. API fetch time
- `log10` and division are trivially fast
- No impact on scan pipeline latency

#### NFR-2: Backward compatibility
- New `IndicatorSignals` fields default to `None`
- `active_indicators` logic already skips `None` fields — old scans score identically
- `composite_score()` auto-renormalizes weights when indicators are missing
- SQLite persistence: `IndicatorSignals` is JSON-serialized — new fields appear as `null`
  in old rows, parsed as `None` on load

#### NFR-3: Observability
- New indicators appear in `NormalizationStats` persistence (scan Phase 4)
- CLI `scan` output and web UI scan results display liquidity indicators when present

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Score differentiation | Tickers with OI > 10,000 and spread < 5% score measurably higher than OI ~100 and spread ~25% | Compare composite scores with/without liquidity on a full S&P 500 scan |
| Outcome improvement | Recommendations with high liquidity scores have lower realized slippage | Compare T+1 P&L variance between high/low liquidity score quintiles (requires 30+ days of outcome data) |
| Zero regression | All existing 3,949+ tests pass without modification | CI pipeline |
| Backward compat | Historical scan loads produce identical composite scores | Load a pre-liquidity scan and verify scores match |

## Constraints & Assumptions

1. **No new API calls** — all data comes from the option chain already fetched in Phase 3
2. **Module boundaries respected** — `scoring/` accesses contract data through typed models only; `indicators/` uses pandas in/out; computation helpers in `scoring/contracts.py` stay within its boundary
3. **Pydantic v2 models** with `X | None` syntax, `math.isfinite()` validators, NaN defense
4. **Config via DI** — any new thresholds (e.g., liquidity multiplier weights) go in `PricingConfig`
5. **Float type** for liquidity metrics — these are ratios and scores, not prices
6. **The composite formula tolerates partial coverage** — new indicators participate only when populated via `active_indicators` filtering
7. **Phase 3 currently does NOT re-score** — liquidity indicators will be computed and persisted, but will only affect composite scores when Phase 3 re-scoring is implemented (separate task, out of scope)

**Assumption:** Phase 3 re-scoring (recomputing composite after options data enrichment)
is a prerequisite for liquidity indicators to affect the top-N ranking. Without it,
liquidity indicators are persisted but only influence single-ticker normalization
(debate route) and contract selection (FR-3). This is still valuable but the full
benefit requires re-scoring.

## Out of Scope

- **Phase 3 composite re-scoring** — enriching the composite score after option chain
  fetch. This is a separate epic that would benefit liquidity AND the existing 4 options
  indicators (`iv_rank`, `iv_percentile`, `put_call_ratio`, `max_pain_distance`)
- **Historical option volume trends** — requires new data sources
- **Real-time spread monitoring** — requires streaming data
- **Per-expiration liquidity comparison** — current pipeline selects one expiration; we
  score that expiration's chain only
- **Populating the existing `spread_quality` DSE field** — remains a dead field
- **Debate agent prompt changes** — agents already receive market context; no prompt
  modifications needed for liquidity indicators
- **Frontend UI changes for liquidity display** — indicators will appear in existing
  scan result tables automatically via the generic indicator rendering

## Dependencies

### Internal
- `models/scan.py` — `IndicatorSignals` model (add 2 fields)
- `scoring/composite.py` — `INDICATOR_WEIGHTS` table (add 2 entries, redistribute)
- `scoring/normalization.py` — `DOMAIN_BOUNDS`, `INVERTED_INDICATORS` (add entries)
- `scoring/contracts.py` — `select_by_delta()` (add liquidity multiplier)
- `scan/indicators.py` or `scan/pipeline.py` — Phase 3 wiring (compute new indicators)
- `models/config.py` — `PricingConfig` (optional: liquidity multiplier config params)

### External
- None — no new packages, APIs, or services

## Task Breakdown

| # | Task | Files | Size | Depends On |
|---|------|-------|------|------------|
| 1 | Add `chain_spread_pct` and `chain_oi_depth` fields to `IndicatorSignals` | `models/scan.py` | S | — |
| 2 | Add computation functions for chain spread pct and OI depth | `scoring/contracts.py` or new `scoring/liquidity.py` | M | 1 |
| 3 | Add entries to `INDICATOR_WEIGHTS`, `DOMAIN_BOUNDS`, `INVERTED_INDICATORS` | `scoring/composite.py`, `scoring/normalization.py` | S | 1 |
| 4 | Redistribute existing weights (sum must remain 1.0) | `scoring/composite.py` | S | 3 |
| 5 | Wire computation into Phase 3 pipeline | `scan/pipeline.py` or `scan/indicators.py` | M | 2 |
| 6 | Implement liquidity score multiplier in `select_by_delta()` | `scoring/contracts.py` | M | 1 |
| 7 | Add config params to `PricingConfig` if needed | `models/config.py` | S | — |
| 8 | Unit tests for new computation functions | `tests/unit/scoring/` | M | 2 |
| 9 | Unit tests for weight redistribution (sum=1.0, active_indicators) | `tests/unit/scoring/` | S | 3, 4 |
| 10 | Unit tests for liquidity multiplier in select_by_delta | `tests/unit/scoring/` | M | 6 |
| 11 | Integration test: full scan with liquidity scoring | `tests/unit/scan/` | M | 5 |
| 12 | Backward compatibility test: load pre-liquidity scan | `tests/unit/scoring/` | S | 3 |
| 13 | Update normalization stats persistence for new indicators | `data/repository.py` (if needed) | S | 5 |

**Estimated total effort:** Medium epic (~13 tasks, 6S + 6M + 1 integration)

## Verification Checklist

- [x] No new API calls or external dependencies (FR uses existing chain data)
- [x] No module boundary violations (scoring accesses models only, not services)
- [x] All new fields have `math.isfinite()` guards (via IndicatorSignals model_validator)
- [x] Inverted indicator flagged: `chain_spread_pct` added to `INVERTED_INDICATORS`
- [x] NormalizationStats persistence covers new indicators (auto via existing JSON serialization)
- [x] Single-ticker normalization has domain bounds: (0.0, 30.0) and (0.0, 6.0)
- [x] Backward compatible: `None` defaults, `active_indicators` auto-skips missing
- [x] Config thresholds in `PricingConfig`, not hardcoded
- [x] Float type for ratios/scores, not Decimal
- [x] Edge cases handled: zero contracts (None), single contract, identical metrics
