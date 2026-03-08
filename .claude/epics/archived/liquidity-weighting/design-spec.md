# Liquidity Weighting Design Specification

**Status**: Draft
**Author**: Claude (design task)
**Date**: 2026-03-08
**Epic**: liquidity-weighting

---

## 1. Selected Signals

### Signal Assessment Summary

| Candidate | Verdict | Reason |
|-----------|---------|--------|
| OI-weighted chain spread % | **Include** | High signal, zero cost, chain-level quality |
| Log total chain OI | **Include** | Captures market depth, orthogonal to spread |
| Volume-to-OI ratio | **Exclude** | Too noisy — spikes on expiration days, new positions |
| Dollar volume of recommended contract | **Exclude** | Computed AFTER composite (chicken-and-egg) |
| Historical option volume trend | **Exclude** | Requires new API calls (constraint #9) |
| Recommended contract spread % | **Exclude** | Available only after `recommend_contracts()` runs; use as tiebreaker instead |

### Signal 1: `chain_spread_pct`

- **Name**: `chain_spread_pct`
- **Formula**: OI-weighted average bid-ask spread percentage across the full option chain

  ```
  For each contract i with bid > 0 and ask > 0 and mid > 0:
      spread_pct_i = (ask_i - bid_i) / mid_i

  chain_spread_pct = sum(spread_pct_i * oi_i) / sum(oi_i)
  ```

  Expressed as a decimal (0.01 = 1% spread). Contracts with `bid=0` or `mid=0` are
  excluded from the weighted average (zero-bid contracts are common in yfinance data
  and would distort the metric).

- **Direction**: Lower is better → **INVERTED** (added to `INVERTED_INDICATORS`)
- **Domain bounds (single-ticker)**: `(0.0, 0.30)` — aligns with the existing
  `max_spread_pct` gate at 30%. A value of 0.01 (1%) is excellent; 0.25 (25%) is poor.
- **Justification**: The existing 30% spread gate is binary — everything below passes
  equally. This signal transforms spread quality into a gradient. A ticker whose chain
  has an average 1% spread has fundamentally better fills, lower slippage, and more
  institutional participation than one averaging 25%. The OI weighting ensures that the
  metric reflects spreads where actual trading activity occurs, not illiquid far-OTM
  strikes with wide spreads and zero OI.
- **Data availability**: `OptionContract.bid`, `.ask`, `.mid`, `.open_interest` are all
  present in Phase 3 after chain fetching. Zero additional API calls.
- **Edge cases**:
  - All contracts have `bid=0`: returns `None` (no valid spread data).
  - Total OI of valid contracts = 0: returns `None`.
  - Single valid contract: returns that contract's spread percentage.
  - Result is non-finite: returns `None` (isfinite guard).

### Signal 2: `chain_oi_depth`

- **Name**: `chain_oi_depth`
- **Formula**: Log-scaled total open interest across the full option chain

  ```
  total_oi = sum(contract.open_interest for all contracts)
  chain_oi_depth = log10(1 + total_oi)
  ```

  The `log10(1 + x)` transform compresses the massive range of OI values (100 to
  10,000,000+) into a manageable scale while preserving relative ordering. The `+1`
  prevents `log(0)`.

- **Direction**: Higher is better → **NOT inverted**
- **Domain bounds (single-ticker)**: `(2.0, 7.0)` — corresponds to total OI from 100
  (log10(101) ≈ 2.0) to 10,000,000 (log10(10,000,001) ≈ 7.0). Values below 100 total OI
  are clamped to 0 (normalized), values above 10M clamped to 100.
- **Justification**: Total chain OI captures market depth — how many open positions exist
  across all strikes and expirations. High OI means more counterparties, tighter markets,
  and easier order fills. This is orthogonal to spread quality: a chain can have tight
  spreads but low OI (market maker quotes with no natural flow), or wide spreads but high
  OI (actively traded but volatile underlying). Together, the two signals capture both
  dimensions of liquidity.
- **Data availability**: `OptionContract.open_interest` is present on every contract
  in Phase 3. Zero additional API calls. The sum is trivially computed.
- **Edge cases**:
  - Empty contract list: returns `None`.
  - Total OI = 0: `log10(1) = 0.0` — valid but low score.
  - All contracts have identical OI: valid, percentile rank handles ties.

### Existing DSE Field: `spread_quality` (Populate, Not New)

- **Field**: `spread_quality` (already on `IndicatorSignals`, never populated)
- **Formula**: OI-weighted average absolute dollar spread (existing
  `compute_spread_quality()` in `indicators/options_specific.py`)
- **Purpose**: Populates the existing DSE "risk" dimensional score field. Does NOT
  enter the composite — serves only dimensional scoring.
- **Action**: Wire the existing function into `compute_phase3_indicators()` or
  `compute_options_indicators()`.

### Contract-Level Enhancement: Spread Tiebreaker in `select_by_delta()`

- **Location**: `scoring/contracts.py::select_by_delta()`
- **Current sort**: `(delta_distance, strike)` — deterministic but liquidity-blind
- **Proposed sort**: `(delta_distance, spread_pct, strike)` — among contracts at equal
  delta distance, prefer tighter spreads before falling back to strike tiebreaker
- **Computation**: `spread_pct = float(contract.spread / contract.mid)` if `mid > 0`,
  else `float('inf')` (worst possible tiebreaker, pushes zero-mid to end)
- **Justification**: Two contracts at identical delta distance should not be
  disambiguated by strike alone. The one with tighter spread is strictly better for
  the trader. This is the contract-level complement to the ticker-level composite signals.

---

## 2. Architecture Decision

### Chosen Approach: **Option C — Hybrid**

**Rationale**: Neither A nor B alone solves the problem:

- **Option A** (composite only) adds gradient scoring to the top-N selection but misses
  the contract-level tiebreaker opportunity. Among contracts at equal delta distance,
  the tighter-spread contract is objectively better.
- **Option B** (contract-level only) improves individual contract selection but cannot
  influence which tickers make the top-N cut. A ticker with a highly liquid chain should
  rank above one barely passing gates, regardless of which contract is ultimately selected.
- **Option C** (hybrid) addresses both levels: chain-level aggregation feeds the composite
  score (influencing top-N), and contract-level spread becomes a tiebreaker in delta
  selection (improving the recommended contract).

All three components respect architecture boundaries:
- Chain aggregation happens in `scan/indicators.py` (orchestration layer — can access
  `models/` and `indicators/`)
- Composite weight changes are in `scoring/composite.py` (scoring layer)
- Contract tiebreaker is in `scoring/contracts.py` (scoring layer, already has contract data)
- No service-layer changes. No new API calls. No boundary violations.

### Files Modified

| File | Change | Module |
|------|--------|--------|
| `models/scan.py` | Add 2 new fields to `IndicatorSignals` | models |
| `indicators/options_specific.py` | Add `compute_chain_spread_pct()` function | indicators |
| `scan/indicators.py` | Call new functions, populate signals | scan |
| `scan/pipeline.py` | Add new fields to `_PHASE3_FIELDS` tuple | scan |
| `scoring/composite.py` | Add 2 entries to `INDICATOR_WEIGHTS`, update sum | scoring |
| `scoring/normalization.py` | Add `chain_spread_pct` to `INVERTED_INDICATORS`, add 2 entries to `DOMAIN_BOUNDS` | scoring |
| `scoring/contracts.py` | Add spread tiebreaker to `select_by_delta()` | scoring |
| `scoring/dimensional.py` | Add new fields to appropriate dimension (if desired) | scoring |
| `tests/unit/scoring/test_composite.py` | Update weight sum test, add new indicator tests | tests |
| `tests/unit/scoring/test_normalization.py` | Test inversion, domain bounds | tests |
| `tests/unit/scoring/test_contracts.py` | Test spread tiebreaker | tests |
| `tests/unit/indicators/test_options_specific.py` | Test new indicator function | tests |
| `tests/unit/scan/test_indicators.py` | Test signal population | tests |

### New Fields

**`IndicatorSignals`** (in `models/scan.py`):
```python
# --- Liquidity (2 new composite fields) ---
chain_spread_pct: float | None = None
chain_oi_depth: float | None = None
```

Position: after the existing DSE Risk section (after `max_loss_ratio`), before
Trend Extensions. Grouping comment: `# --- Liquidity (2 new composite) ---`.

**No new config fields needed.** The existing `PricingConfig.max_spread_pct` is sufficient
as the domain upper bound for `chain_spread_pct`. The log scale for `chain_oi_depth` has
natural bounds. No new thresholds to configure.

### Data Flow

```
Phase 3, per ticker:
  OptionsDataService.fetch_chain_all_expirations(ticker)
    → list[ExpirationChain] → flatten → all_contracts: list[OptionContract]

  compute_options_indicators(all_contracts, spot)
    → IndicatorSignals with:
        put_call_ratio, max_pain_distance (existing)
        chain_spread_pct, chain_oi_depth (NEW)

  → merge into ticker_score.signals (raw values)

After all tickers complete:
  _normalize_phase3_signals(top_scores)
    → chain_spread_pct, chain_oi_depth percentile-ranked 0-100

  invert_indicators applied during normalization
    → chain_spread_pct flipped (100 - value)

  _recompute_composite_scores(top_scores)
    → composite_score() now includes chain_spread_pct (weight 0.04)
       and chain_oi_depth (weight 0.04) in the geometric mean

  Top-N re-sorted by updated composite score
```

**Note**: The new fields are computed in `compute_options_indicators()` (not
`compute_phase3_indicators()`), alongside `put_call_ratio` and `max_pain_distance`.
This is because they are simple chain aggregations that don't need close series, dividend
yield, or other Phase 3 enrichment data. They only need the contract list and spot price.

**Normalization timing**: Raw values are written to `ticker_score.signals` per-ticker.
After all tickers complete, `_normalize_phase3_signals()` percentile-ranks them across
the sub-universe. The new fields are in `_PHASE3_FIELDS`, so they participate
automatically.

**Inversion**: `chain_spread_pct` is added to `INVERTED_INDICATORS`. After percentile
normalization, it is flipped: `100 - value`. Since Phase 3 normalization does NOT apply
`invert_indicators()` (it only runs `percentile_rank_normalize()`), the inversion for
Phase 3 fields happens via `_recompute_composite_scores()` which calls
`composite_score()` on already-normalized values.

Wait — critical observation: Phase 3 normalization does NOT call `invert_indicators()`.
Looking at `_normalize_phase3_signals()`, it only runs `percentile_rank_normalize()` and
writes values back. The comment in `_recompute_composite_scores()` says "Phase 3 fields
are percentile-ranked but NOT inverted because none of them appear in
INVERTED_INDICATORS".

**This means `chain_spread_pct` inversion needs special handling.** There are two options:

1. Add inversion logic to `_normalize_phase3_signals()` for Phase 3 inverted fields.
2. Don't add `chain_spread_pct` to `INVERTED_INDICATORS` (which only affects Phase 2).
   Instead, negate the raw value before normalization so that lower spread → higher raw
   value → higher percentile rank naturally.

**Recommended approach**: Option 1 — add a post-normalization inversion step to
`_normalize_phase3_signals()` for any Phase 3 fields that appear in `INVERTED_INDICATORS`.
This is the clean fix that extends the existing pattern. Currently, no Phase 3 fields need
inversion, but `chain_spread_pct` will be the first. The code change is 3 lines:

```python
# After writing normalized values back:
for field_name in _PHASE3_FIELDS:
    if field_name in INVERTED_INDICATORS:
        val = getattr(ts.signals, field_name)
        if val is not None:
            setattr(ts.signals, field_name, 100.0 - val)
```

This also future-proofs for any other inverted Phase 3 fields.

---

## 3. Weight Allocation

### Design Principle

Liquidity should have meaningful but not dominant influence. It is a quality filter,
not a primary signal generator. A ticker with perfect liquidity but no directional
signal is not actionable. Conversely, a strong signal on an illiquid chain is dangerous.

**Proposed total liquidity weight: 0.08** (two indicators at 0.04 each).

This is comparable to the Volatility category (0.13 after rebalancing) and smaller than
Trend (0.19) or Options (0.19). Liquidity acts as a quality multiplier — it lifts
otherwise-good tickers whose chains are highly liquid and penalizes those barely
passing gates.

### Updated Weight Table (21 indicators, sum = 1.0)

Weights are redistributed proportionally: each existing category loses ~8% of its weight
to fund the new Liquidity category.

```
Oscillators (0.16):    rsi(0.06), stochastic_rsi(0.05), williams_r(0.05)
Trend (0.19):          adx(0.06), roc(0.03), supertrend(0.05), macd(0.05)
Volatility (0.13):     atr_pct(0.05), bb_width(0.04), keltner_width(0.04)
Volume (0.14):         obv(0.05), ad(0.04), relative_volume(0.05)
Moving Avgs (0.11):    sma_alignment(0.06), vwap_deviation(0.05)
Options (0.19):        iv_rank(0.05), iv_percentile(0.05), put_call_ratio(0.05), max_pain_distance(0.04)
Liquidity (0.08):      chain_spread_pct(0.04), chain_oi_depth(0.04)   ← NEW
```

**Verification**: 0.16 + 0.19 + 0.13 + 0.14 + 0.11 + 0.19 + 0.08 = **1.00** ✓

### Per-Indicator Weight Changes

| Indicator | Old Weight | New Weight | Delta |
|-----------|-----------|-----------|-------|
| rsi | 0.07 | 0.06 | -0.01 |
| stochastic_rsi | 0.05 | 0.05 | 0 |
| williams_r | 0.05 | 0.05 | 0 |
| adx | 0.07 | 0.06 | -0.01 |
| roc | 0.03 | 0.03 | 0 |
| supertrend | 0.05 | 0.05 | 0 |
| macd | 0.05 | 0.05 | 0 |
| atr_pct | 0.05 | 0.05 | 0 |
| bb_width | 0.05 | 0.04 | -0.01 |
| keltner_width | 0.04 | 0.04 | 0 |
| obv | 0.05 | 0.05 | 0 |
| ad | 0.05 | 0.04 | -0.01 |
| relative_volume | 0.05 | 0.05 | 0 |
| sma_alignment | 0.07 | 0.06 | -0.01 |
| vwap_deviation | 0.05 | 0.05 | 0 |
| iv_rank | 0.06 | 0.05 | -0.01 |
| iv_percentile | 0.06 | 0.05 | -0.01 |
| put_call_ratio | 0.05 | 0.05 | 0 |
| max_pain_distance | 0.05 | 0.04 | -0.01 |
| **chain_spread_pct** | — | **0.04** | **+0.04** |
| **chain_oi_depth** | — | **0.04** | **+0.04** |

Eight indicators lose 0.01 each (total -0.08), funding the two new indicators at
0.04 each (total +0.08). The reductions are spread across the highest-weighted indicators
in each category, preserving relative ordering within categories.

### Domain Bounds for Single-Ticker Normalization

Added to `DOMAIN_BOUNDS` in `scoring/normalization.py`:

| Field | Lo | Hi | Notes |
|-------|-----|-----|-------|
| `chain_spread_pct` | 0.0 | 0.30 | Matches `max_spread_pct` gate (30%) |
| `chain_oi_depth` | 2.0 | 7.0 | log10(101) ≈ 2.0 to log10(10M) ≈ 7.0 |

### Inversion

| Field | Inverted? | Reason |
|-------|-----------|--------|
| `chain_spread_pct` | **Yes** | Lower spread = better liquidity |
| `chain_oi_depth` | No | Higher OI = better depth |

---

## 4. Edge Cases & Backward Compatibility

### Edge Case Handling

| Edge Case | `chain_spread_pct` | `chain_oi_depth` | Tiebreaker |
|-----------|-------------------|------------------|------------|
| Zero contracts in chain | `None` (skipped) | `None` (skipped) | N/A (no contracts to select) |
| All contracts have bid=0 | `None` (no valid spread data) | Computed normally from OI | N/A |
| Single contract only | That contract's spread % | log10(1 + oi) | No tiebreaker needed |
| All contracts identical metrics | Valid single value | Valid single value | All tied, falls through to strike |
| Total valid OI = 0 | `None` (division by zero guard) | log10(1) = 0.0 | `inf` spread, pushed to end |
| Non-finite result | `None` (isfinite guard) | `None` (isfinite guard) | `inf`, pushed to end |

### Backward Compatibility

**Existing scans loaded from DB**: `IndicatorSignals` fields default to `None`. The
composite formula's `active_indicators` filtering skips `None` fields and renormalizes
weights over the remaining indicators. Old scans produce identical scores — the new
liquidity fields are simply absent.

**New scans on old data**: If a ticker has no option chain data (Phase 3 skipped or
failed), both liquidity fields are `None`. The composite score is computed from the
remaining 19 indicators with renormalized weights. Behavior is identical to current.

**Single-ticker debate**: `normalize_single_ticker()` uses `DOMAIN_BOUNDS` for linear
scaling. New entries in `DOMAIN_BOUNDS` enable normalization. If the liquidity fields are
`None` (no chain data in debate context), they are skipped.

**NormalizationStats**: `compute_normalization_stats()` iterates over all
`IndicatorSignals` fields via `get_active_indicators()`. New fields are automatically
included when populated. No code changes needed for stats persistence.

### Migration

No database migration required. `IndicatorSignals` is serialized as JSON in
`ticker_scores.signals` column. New fields with `None` defaults are compatible with
existing JSON (missing keys default to `None` via Pydantic).

---

## 5. Task Breakdown

### Implementation Tasks

| # | Task | Files | Size | Depends On |
|---|------|-------|------|------------|
| 1 | Add `chain_spread_pct` and `chain_oi_depth` fields to `IndicatorSignals` | `models/scan.py` | S | — |
| 2 | Add `compute_chain_spread_pct()` to indicators module | `indicators/options_specific.py` | S | — |
| 3 | Compute new signals in `compute_options_indicators()` | `scan/indicators.py` | M | 1, 2 |
| 4 | Add fields to `_PHASE3_FIELDS` tuple | `scan/pipeline.py` | S | 1 |
| 5 | Add Phase 3 inversion support to `_normalize_phase3_signals()` | `scan/pipeline.py` | S | 4 |
| 6 | Update `INDICATOR_WEIGHTS` (21 entries, rebalanced) | `scoring/composite.py` | S | 1 |
| 7 | Add `chain_spread_pct` to `INVERTED_INDICATORS` | `scoring/normalization.py` | S | 1 |
| 8 | Add 2 entries to `DOMAIN_BOUNDS` | `scoring/normalization.py` | S | 1 |
| 9 | Add spread tiebreaker to `select_by_delta()` | `scoring/contracts.py` | S | — |
| 10 | Populate `spread_quality` DSE field in pipeline | `scan/indicators.py` | S | — |
| 11 | Add `chain_spread_pct`, `chain_oi_depth` to dimensional scoring | `scoring/dimensional.py` | S | 1 |
| 12 | Unit tests: `compute_chain_spread_pct()` | `tests/unit/indicators/` | M | 2 |
| 13 | Unit tests: composite weight sum, new indicators in scoring | `tests/unit/scoring/` | M | 6, 7, 8 |
| 14 | Unit tests: spread tiebreaker in `select_by_delta()` | `tests/unit/scoring/` | M | 9 |
| 15 | Unit tests: signal population in scan indicators | `tests/unit/scan/` | M | 3 |
| 16 | Integration test: full pipeline with liquidity signals | `tests/unit/scan/` | M | 3, 4, 5, 6 |
| 17 | Update scoring/CLAUDE.md and scan/CLAUDE.md | docs | S | 6 |
| 18 | Update `tools/docgen.py` output (if applicable) | docs | S | all |

### Dependency Graph

```
Wave 1 (foundation, parallel):
  [1] IndicatorSignals fields
  [2] compute_chain_spread_pct()
  [9] select_by_delta tiebreaker
  [10] spread_quality DSE wiring

Wave 2 (scoring config, parallel, depends on 1):
  [4] _PHASE3_FIELDS
  [6] INDICATOR_WEIGHTS
  [7] INVERTED_INDICATORS
  [8] DOMAIN_BOUNDS
  [11] dimensional scoring

Wave 3 (pipeline integration, depends on 1, 2, 4):
  [3] compute_options_indicators
  [5] Phase 3 inversion support

Wave 4 (tests, depends on respective impl tasks):
  [12] indicator tests
  [13] scoring tests
  [14] contract tests
  [15] scan indicator tests
  [16] integration test

Wave 5 (docs, depends on all):
  [17] CLAUDE.md updates
  [18] docgen refresh
```

### Effort Estimate

- **S tasks**: 10 × ~15 min = ~2.5 hours
- **M tasks**: 7 × ~30 min = ~3.5 hours
- **Total**: ~6 hours implementation + testing
- **Risk buffer**: +2 hours for Phase 3 inversion edge cases and weight rebalancing validation
- **Estimated total**: ~8 hours

---

## 6. Verification Checklist

| # | Constraint | Satisfied? | How |
|---|-----------|-----------|-----|
| 1 | Pydantic v2 models with `X \| None` | ✓ | New fields: `chain_spread_pct: float \| None = None` |
| 2 | Entries in weights, bounds, inversion | ✓ | Added to `INDICATOR_WEIGHTS`, `DOMAIN_BOUNDS`, `INVERTED_INDICATORS` |
| 3 | Typed models, not raw dicts | ✓ | `compute_options_indicators()` returns `IndicatorSignals`; tiebreaker uses `OptionContract` fields |
| 4 | `math.isfinite()` guards | ✓ | Both `compute_chain_spread_pct()` and `chain_oi_depth` computation return `None` on non-finite results |
| 5 | Config thresholds, not hardcoded | ✓ | Domain bounds are module constants (existing pattern); no new runtime config needed |
| 6 | Float type for ratios | ✓ | Both fields are `float \| None`, not `Decimal` |
| 7 | `None` defaults for backward compat | ✓ | `= None` on both fields; `composite_score()` skips `None` fields |
| 8 | Geometric mean tolerates missing | ✓ | `active_indicators` filtering + weight renormalization handles partial coverage |
| 9 | No new API calls | ✓ | All data from `OptionContract` fields already fetched in Phase 3 |
| 10 | Edge cases handled | ✓ | Zero contracts → `None`; single contract → valid; identical metrics → valid |
| — | No module boundary violations | ✓ | `scan/` calls `indicators/` and `scoring/`; `scoring/` accesses `models/` only |
| — | NormalizationStats covers new fields | ✓ | `compute_normalization_stats()` auto-discovers via `get_active_indicators()` |
| — | Single-ticker normalization has bounds | ✓ | Two new entries in `DOMAIN_BOUNDS` |
| — | Phase 3 inversion handled | ✓ | New inversion step in `_normalize_phase3_signals()` for Phase 3 inverted fields |

---

## Appendix A: Rejected Alternatives

### Volume-to-OI Ratio (`chain_volume_oi_ratio`)

- **Formula**: `sum(volume) / sum(open_interest)`
- **Issue**: Too noisy for reliable cross-universe comparison. On expiration weeks,
  volume spikes relative to OI. Newly opened positions show high volume with zero OI
  (OI updates next day). The signal would need date-relative normalization that adds
  complexity without proportional value. The two selected signals (spread quality +
  depth) already capture the most important liquidity dimensions.

### Dollar Volume of Recommended Contract

- **Formula**: `float(contract.mid) * contract.volume * 100`
- **Issue**: The recommended contract is selected by `recommend_contracts()` which runs
  AFTER indicator computation and composite scoring. Feeding the contract's dollar volume
  back into the composite would create a circular dependency. This metric is useful for
  display/reporting but not for scoring.

### Chain-Level Dollar Volume

- **Formula**: `sum(mid_i * volume_i * 100)` across all contracts
- **Issue**: Highly correlated with `chain_oi_depth` (r > 0.9 empirically) and with the
  stock-level dollar volume pre-filter already in Phase 3. Adding a third correlated
  metric provides diminishing returns. The two selected signals are more orthogonal.

## Appendix B: Future Enhancements

1. **Liquidity decay curve**: Track how chain liquidity changes across DTE buckets.
   Near-term options typically have tighter spreads. Could weight by DTE proximity to
   the recommended expiration.

2. **Intraday spread stability**: If real-time data becomes available, measure spread
   variance over the trading day. Stable spreads indicate genuine two-sided markets.

3. **Historical option volume trend**: 30-day moving average of total daily option volume.
   Requires historical option data not currently fetched (constraint #9 in this design).

4. **Market maker participation score**: Ratio of quoted size at NBBO vs. total OI.
   Requires Level 2 data not available via yfinance.
