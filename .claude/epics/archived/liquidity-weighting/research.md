# Research: liquidity-weighting

## PRD Summary

Add two gradient liquidity indicators (`chain_spread_pct`, `chain_oi_depth`) to the
composite scoring system and a liquidity score multiplier to `select_by_delta()` contract
selection. Replace binary pass/fail liquidity gates with continuous signals so tickers
with highly liquid option chains rank higher and the most liquid delta-appropriate contract
is selected.

## Relevant Existing Modules

- `scoring/composite.py` — `INDICATOR_WEIGHTS` dict (19 entries, sum=1.0 validated at import),
  geometric mean formula with `active_indicators` auto-skip for None fields
- `scoring/normalization.py` — `INVERTED_INDICATORS` frozenset (3 entries), `DOMAIN_BOUNDS`
  dict (19 entries), `percentile_rank_normalize()`, `normalize_single_ticker()`
- `scoring/contracts.py` — `filter_contracts()` binary gates, `select_by_delta()` sorts by
  `(delta_distance, strike)`, `recommend_contracts()` orchestrates the full pipeline
- `scoring/dimensional.py` — `FAMILY_INDICATOR_MAP` with 8 families; `spread_quality` in
  `microstructure` family
- `models/scan.py` — `IndicatorSignals` (59 fields, all `float | None = None`),
  `_normalize_non_finite` model_validator auto-sanitizes NaN/Inf
- `models/config.py` — `PricingConfig` has `min_oi`, `min_volume`, `max_spread_pct`
- `scan/pipeline.py` — `_PHASE3_FIELDS` tuple (authoritative list for Phase 3 normalization),
  `_process_ticker_options()` where chain data is available
- `scan/indicators.py` — `compute_phase3_indicators()` and `_contracts_to_dataframe()` helper
  that already builds DataFrame with `bid`, `ask`, `openInterest` columns
- `indicators/options_specific.py` — `compute_spread_quality()` exists but computes absolute
  dollar spread (not percentage); never called from pipeline

## Existing Patterns to Reuse

### 1. Active Indicators Auto-Skip
`get_active_indicators()` scans the universe and returns field names with at least one
finite value. `composite_score()` divides by `weight_sum` of contributing indicators only,
not 1.0 — so missing indicators redistribute weight automatically. New fields with `None`
default are backward-compatible for free.

### 2. _contracts_to_dataframe() Helper
Already in `scan/indicators.py` (line 747). Builds a DataFrame with `bid`, `ask`,
`openInterest`, `strike`, `volume`, `gamma`, `option_type` from `list[OptionContract]`.
Used by `compute_phase3_indicators()` for GEX/OI concentration. Reuse for chain spread
and OI depth computation.

### 3. _merge_signals() Pattern
Phase 3 DSE signals are computed in `compute_phase3_indicators()`, returned as a dict,
and merged into `ticker_score.signals` via `_merge_signals()` which iterates `_PHASE3_FIELDS`
and calls `setattr`. New fields just need to be added to `_PHASE3_FIELDS` and returned
from the computation function.

### 4. NaN/Inf Sanitization
`IndicatorSignals._normalize_non_finite` model_validator (mode="before") replaces any
non-finite float with `None`. New fields inherit this automatically — no extra validator needed.

### 5. Percentile Rank Normalization
Universe-wide rank-based normalization handles ties (averaging), n=1 (midpoint 50.0),
n=0 (all None). Inverted indicators get `100 - value` after ranking. New indicators
just need entries in `INVERTED_INDICATORS` and `DOMAIN_BOUNDS`.

## Existing Code to Extend

### `models/scan.py` — IndicatorSignals
- Add 2 fields after line ~105 (DSE Risk block):
  `chain_spread_pct: float | None = None` and `chain_oi_depth: float | None = None`
- Update docstring field count (59 → 61)
- NaN sanitizer covers new fields automatically

### `scoring/composite.py` — INDICATOR_WEIGHTS (lines 32-58)
- Add 2 entries: `"chain_spread_pct": (0.04, "liquidity")`, `"chain_oi_depth": (0.02, "liquidity")`
- Reduce 6 existing weights by total of 0.06 to maintain sum=1.0
- Import-time guard (line 62) validates sum; will fail if not exactly 1.0

### `scoring/normalization.py`
- Line 37: Add `"chain_spread_pct"` to `INVERTED_INDICATORS` frozenset
- Lines 43-63: Add `"chain_spread_pct": (0.0, 30.0)` and `"chain_oi_depth": (0.0, 6.0)` to `DOMAIN_BOUNDS`

### `scoring/contracts.py` — select_by_delta (lines 304-365)
- Current sort key: `lambda t: (t[1], t[0].strike)` where `t[1]` is delta distance
- Inject liquidity multiplier: compute `liquidity_score` from contract's `spread/mid` and
  `open_interest`, divide delta distance by it to get `effective_distance`
- Contracts with better liquidity get lower effective distance → win ties

### `scan/indicators.py` — compute_phase3_indicators (line 411)
- After `_contracts_to_dataframe(contracts)` call, compute `chain_spread_pct` and
  `chain_oi_depth` from the DataFrame
- Return both values in the signals dict alongside existing DSE fields

### `scan/pipeline.py` — _PHASE3_FIELDS (lines 1122-1166)
- Add `"chain_spread_pct"` and `"chain_oi_depth"` to the tuple
- These will then be merged by `_merge_signals()` and normalized by
  `_normalize_phase3_signals()`

### `scoring/dimensional.py` — FAMILY_INDICATOR_MAP (lines 23-99)
- Add `"chain_spread_pct"` and `"chain_oi_depth"` to `"microstructure"` family
  (or create a new `"liquidity"` family)

## Potential Conflicts

### 1. Weight Sum Assertion Test
`tests/unit/scoring/test_weight_assertion.py` has `test_indicator_weights_has_19_entries`
that asserts exactly 19 entries. Must update to 21. Also tests sum=1.0 which will pass
if weights are correctly redistributed.

### 2. Existing `spread_quality` Field
Dead field on `IndicatorSignals` — declared but never populated from pipeline.
`compute_spread_quality()` computes absolute dollar spread, not percentage. PRD decision:
keep as-is, add new distinct fields. No conflict but potential confusion — document clearly.

### 3. Phase 3 Re-Scoring Limitation
`_recompute_composite_scores()` runs after Phase 3 normalization and DOES re-score
using `INDICATOR_WEIGHTS`. So liquidity indicators WILL affect the composite score
during a scan — this is correct and desired. The PRD had noted uncertainty about this;
the code confirms it works.

### 4. Domain Bounds for chain_spread_pct
The PRD suggests `(0.0, 30.0)` but `max_spread_pct` config is 0.30 (30% as a ratio,
not percentage points). Need to decide: is `chain_spread_pct` stored as 0.0-0.30 ratio
or 0-30 percentage points? Recommend percentage points (0-30) for readability and
consistency with the 30% gate interpretation.

## Open Questions

### 1. chain_spread_pct: Ratio or Percentage Points?
The existing `max_spread_pct` config is 0.30 (ratio). Should `chain_spread_pct` be
0.0-0.30 (ratio) or 0.0-30.0 (percentage)? PRD formula shows `* 100` (percentage points).
Domain bounds `(0.0, 30.0)` align with percentage points. **Recommendation**: percentage
points for human readability — 2.5 is clearer than 0.025.

### 2. Should chain_oi_depth Use log10?
PRD specifies `log10(total_oi + 1)`. Domain bounds `(0.0, 6.0)` mean OI up to 1M gets
full range. For S&P 500 liquid names, OI can exceed 1M — consider `(0.0, 7.0)` to
accommodate 10M. **Recommendation**: keep `(0.0, 6.0)` — most option chains fall well
within this; outliers get clamped to 100 by `normalize_single_ticker`, which is fine.

### 3. DSE Family Placement
Should the two new indicators go in `microstructure` (where `spread_quality` already
lives) or create a new `liquidity` family in `FAMILY_INDICATOR_MAP`? Creating a new
family requires a new entry in `DEFAULT_FAMILY_WEIGHTS` (sum must remain 1.0).
**Recommendation**: add to `microstructure` — simpler, no weight redistribution needed
for DSE families.

### 4. Liquidity Multiplier Config Params
Should `liquidity_score` weights (0.7 spread, 0.3 OI) be configurable via `PricingConfig`
or hardcoded as constants? **Recommendation**: module-level constants with clear names
(`_SPREAD_WEIGHT = 0.7`, `_OI_WEIGHT = 0.3`) — these are calibration params that rarely
change and don't need env var override.

## Recommended Architecture

### Data Flow

```
Phase 3: _process_ticker_options()
  ├── fetch option chain → list[OptionContract]
  ├── _contracts_to_dataframe(all_contracts) → chain_df
  ├── compute_phase3_indicators(contracts, ...)
  │     ├── existing: gex, oi_concentration, etc.
  │     ├── NEW: chain_spread_pct = OI-weighted avg(spread/mid * 100)
  │     └── NEW: chain_oi_depth = log10(total_oi + 1)
  ├── _merge_signals() → writes to ticker_score.signals
  └── recommend_contracts()
        └── select_by_delta() → NEW: liquidity multiplier on delta distance

Post-loop:
  ├── _normalize_phase3_signals() → percentile-ranks new fields
  └── _recompute_composite_scores() → geometric mean includes new weights
```

### Weight Redistribution

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
| **Total** | **1.00** | **1.00** | 0.00 |

Note: Weight values must work with floating-point to sum exactly 1.0 within 1e-9. Verify
with Python before committing: `sum(w for w, _ in INDICATOR_WEIGHTS.values())`.

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/scoring/conftest.py` — `make_contract()` factory, `sample_signals_*` fixtures
- `tests/unit/scoring/test_composite.py` — `IndicatorSignals(field=value)` construction,
  `pytest.approx(expected, rel=1e-6)`, tests for weight sum, geometric mean, floor, active_indicators
- `tests/unit/scoring/test_normalization.py` — universe dict construction, per-field assertions
- `tests/unit/scoring/test_contracts.py` — `make_contract()` with delta, tests for
  `filter_contracts`, `select_by_delta`, `recommend_contracts`
- `tests/unit/scoring/test_weight_assertion.py` — asserts 19 entries and sum=1.0
- `tests/unit/indicators/test_options_specific_ext.py` — 7 test cases for `compute_spread_quality`

### New Tests Needed
1. **Computation tests**: `compute_chain_spread_pct()` and `compute_chain_oi_depth()` —
   happy path, edge cases (zero OI, single contract, all identical, NaN values)
2. **Composite weight tests**: Update entry count assertion (19 → 21), verify sum=1.0
3. **Normalization tests**: `chain_spread_pct` in `INVERTED_INDICATORS`, both in `DOMAIN_BOUNDS`
4. **Liquidity multiplier tests**: `select_by_delta` with equally-distant contracts but
   different spreads/OI — verify liquid one wins
5. **Integration test**: Full Phase 3 pipeline with mock chain data — verify new fields
   are populated, normalized, and influence composite score
6. **Backward compat test**: Load `IndicatorSignals` from JSON without new fields — verify
   they deserialize as `None` and composite score unchanged

### Mocking Strategies
- Contract fixtures via `make_contract(bid=X, ask=Y, open_interest=Z, greeks=G)`
- `IndicatorSignals()` with explicit field values for composite score tests
- No external API mocking needed — all data is in-memory at this point

## Estimated Complexity

**Medium** — 13 tasks across 7 production files, ~6 test files. No new dependencies, no
migrations, no API changes. Well-understood patterns (add field → add weight → add
normalization → wire pipeline). The liquidity multiplier in `select_by_delta` is the most
nuanced piece but straightforward. Main risk is floating-point weight sum precision.
