---
name: liquidity-weighting
status: backlog
created: 2026-03-08T14:48:16Z
progress: 0%
prd: .claude/prds/liquidity-weighting.md
github: https://github.com/jobu711/options_arena/issues/375
---

# Epic: liquidity-weighting

## Overview

Add gradient liquidity scoring to replace binary pass/fail option chain filters. Two new
indicators (`chain_spread_pct`, `chain_oi_depth`) enter the composite scoring system as a
new "Liquidity" category (weight 0.06), and a liquidity score multiplier breaks ties in
`select_by_delta()` contract selection. No new API calls, no migrations, no new dependencies.

## Architecture Decisions

### 1. Percentage Points for chain_spread_pct
Store as 0.0–30.0 (percentage points, `* 100`), not 0.0–0.30 ratio. Consistent with
domain bounds `(0.0, 30.0)` and human-readable (2.5% vs 0.025). The existing
`max_spread_pct` config stays as a ratio (0.30) — the computation multiplies by 100.

### 2. DSE Family: Add to Microstructure
Add both new indicators to the existing `microstructure` family in `FAMILY_INDICATOR_MAP`
(where `spread_quality` already lives). Avoids creating a new DSE family and
redistributing `DEFAULT_FAMILY_WEIGHTS`.

### 3. Module-Level Constants for Multiplier Weights
Liquidity multiplier calibration params (`_SPREAD_WEIGHT = 0.7`, `_OI_WEIGHT = 0.3`) as
module-level constants in `scoring/contracts.py`, not `PricingConfig`. These are internal
calibration values that don't need env var override.

### 4. Compute in scan/indicators.py, Not New File
Add `compute_chain_spread_pct()` and `compute_chain_oi_depth()` inside
`scan/indicators.py`'s `compute_phase3_indicators()`, reusing the existing
`_contracts_to_dataframe()` helper. No new `scoring/liquidity.py` file needed.

### 5. spread_quality Left As-Is
The dead `spread_quality` field and `compute_spread_quality()` function remain untouched.
New fields have distinct names and different semantics (percentage vs absolute dollar).

## Technical Approach

### Data Flow

```
Phase 3: _process_ticker_options()
  ├── fetch option chain → list[OptionContract]
  ├── compute_phase3_indicators(contracts, ...)
  │     ├── _contracts_to_dataframe(contracts) → chain_df (already built)
  │     ├── NEW: chain_spread_pct = OI-weighted avg(spread/mid * 100)
  │     └── NEW: chain_oi_depth = log10(total_oi + 1)
  ├── _merge_signals() → writes to ticker_score.signals
  └── recommend_contracts()
        └── select_by_delta() → NEW: liquidity multiplier on effective_distance

Post-loop:
  ├── _normalize_phase3_signals() → percentile-ranks new fields
  └── _recompute_composite_scores() → geometric mean now includes liquidity weights
```

### Weight Redistribution (21 indicators, sum = 1.0)

| Indicator | Current | New | Delta |
|-----------|---------|-----|-------|
| rsi | 0.07 | 0.065 | -0.005 |
| adx | 0.07 | 0.065 | -0.005 |
| atr_pct | 0.05 | 0.045 | -0.005 |
| obv | 0.05 | 0.045 | -0.005 |
| iv_rank | 0.06 | 0.05 | -0.01 |
| iv_percentile | 0.06 | 0.05 | -0.01 |
| put_call_ratio | 0.05 | 0.04 | -0.01 |
| max_pain_distance | 0.05 | 0.04 | -0.01 |
| **chain_spread_pct** | — | **0.04** | +0.04 |
| **chain_oi_depth** | — | **0.02** | +0.02 |
| All others | unchanged | unchanged | — |

### Liquidity Score Multiplier (select_by_delta)

```python
spread_pct = float(c.spread / c.mid) if c.mid > 0 else 0.0
liq = (1 - spread_pct / max_spread_pct) * 0.7 + min(log10(c.open_interest + 1) / 4, 1.0) * 0.3
effective_distance = delta_distance / max(liq, 0.01)
```

Delta proximity remains dominant — a contract at distance 0.01 with poor liquidity (0.033
effective) still beats distance 0.10 with perfect liquidity (0.10 effective).

### Files Modified

| File | Change |
|------|--------|
| `models/scan.py` | Add 2 fields to `IndicatorSignals` |
| `scoring/composite.py` | Add 2 entries + redistribute 8 weights in `INDICATOR_WEIGHTS` |
| `scoring/normalization.py` | Add to `INVERTED_INDICATORS` + `DOMAIN_BOUNDS` |
| `scoring/contracts.py` | Liquidity multiplier in `select_by_delta()`, add constants |
| `scoring/dimensional.py` | Add 2 fields to `microstructure` family |
| `scan/indicators.py` | Compute chain_spread_pct + chain_oi_depth in `compute_phase3_indicators()` |
| `scan/pipeline.py` | Add 2 fields to `_PHASE3_FIELDS` tuple |

## Task Breakdown Preview

- [ ] Task 1: Add model fields — `chain_spread_pct`, `chain_oi_depth` on `IndicatorSignals` (S)
- [ ] Task 2: Add computation logic — compute both indicators in `compute_phase3_indicators()` (M)
- [ ] Task 3: Update scoring tables — weights, domain bounds, inversion, DSE family (S)
- [ ] Task 4: Wire into Phase 3 pipeline — add to `_PHASE3_FIELDS` (S)
- [ ] Task 5: Implement liquidity multiplier — modify `select_by_delta()` sort key (M)
- [ ] Task 6: Unit tests — computation functions, weight sum, normalization entries (M)
- [ ] Task 7: Unit tests — liquidity multiplier, backward compat, integration (M)
- [ ] Task 8: Update existing test assertions — weight count 19→21 (S)

## Dependencies

### Internal
- No prerequisite epics — all touched modules are stable on master
- Research confirms Phase 3 re-scoring already works via `_recompute_composite_scores()`

### External
- None — no new packages, APIs, or services

## Success Criteria (Technical)

- All 3,949+ existing tests pass (zero regression)
- Weight sum validated at import: `abs(sum - 1.0) < 1e-9`
- `IndicatorSignals` from pre-liquidity JSON deserializes with new fields as `None`
- Composite score unchanged for signals where `chain_spread_pct` and `chain_oi_depth` are `None`
- `select_by_delta` prefers tighter-spread contract when delta distances are equal
- `select_by_delta` prefers closer-delta contract regardless of liquidity difference

## Tasks Created
- [ ] 001.md - Add model fields for chain_spread_pct and chain_oi_depth (parallel: false)
- [ ] 002.md - Compute chain_spread_pct and chain_oi_depth in Phase 3 (parallel: true)
- [ ] 003.md - Update scoring tables — weights, domain bounds, inversion, DSE family (parallel: true)
- [ ] 004.md - Wire into Phase 3 pipeline — add to _PHASE3_FIELDS (parallel: false)
- [ ] 005.md - Implement liquidity multiplier in select_by_delta() (parallel: true)
- [ ] 006.md - Unit tests — computation functions and scoring integration (parallel: true)
- [ ] 007.md - Unit tests — liquidity multiplier and backward compat (parallel: true)
- [ ] 008.md - Update existing test assertions for new weight count (parallel: true)

Total tasks: 8
Parallel tasks: 6
Sequential tasks: 2
Estimated total effort: 11.5 hours

## Test Coverage Plan
Total test files planned: 6
Total test cases planned: 39

## Estimated Effort

**Medium** — 8 tasks (4S + 4M), 7 production files, ~6 test files. No migrations, no
new dependencies. Well-understood patterns. Estimated 1 session.
