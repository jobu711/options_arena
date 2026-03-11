# Research: volatility-intelligence

## PRD Summary

Two compounding volatility techniques: (1) **put-call parity IV smoothing** — average call/put IVs at same strike weighted by inverse bid-ask spread to cancel noise before Greeks computation, and (2) **fitted implied volatility surface** with per-contract mispricing z-scores via scipy spline interpolation across strike × DTE. Cleaner IVs → better surface fit → accurate mispricing detection → higher-alpha contract selection. Zero new dependencies (uses existing scipy).

5 delivery issues with dependency chain: Issues 1+3 parallel → Issue 2 depends on 1 → Issue 4 depends on 2+3 → Issue 5 depends on 4.

## Relevant Existing Modules

- `pricing/` — Pure scalar math. `dispatch.py` routes Greeks computation. New `iv_smoothing.py` goes here. Constraints: no pandas, no services, scalar float in/out, `math.log/sqrt/exp` only (no numpy).
- `indicators/` — Pure math, pandas/numpy in/out, no Pydantic. New `volatility_surface.py` goes here with NamedTuple returns. Uses numpy arrays for surface fitting.
- `scoring/` — `contracts.py` has `compute_greeks()` (3-tier: MARKET → COMPUTED → exclude). IV smoothing integrates as pre-processing step in Tier 2. `composite.py` has `INDICATOR_WEIGHTS` with import-time sum=1.0 guard. `normalization.py` has `INVERTED_INDICATORS` frozenset and `DOMAIN_BOUNDS`.
- `scan/` — `phase_options.py` orchestrates Phase 3: chain fetch → indicators → contract selection. Surface fitting inserts between chain fetch and `compute_phase3_indicators()`. `_PHASE3_FIELDS` tuple controls field merge.
- `models/` — `OptionContract` (frozen), `GreeksSource` enum, `IndicatorSignals` (61 fields, NOT frozen), `MarketContext` (50+ fields). All need extensions with `float | None` + `math.isfinite()` validators.
- `agents/` — `_parsing.py` renders `MarketContext` into prompt text via `_render_optional()` helper. New VOLATILITY SURFACE block follows existing pattern.

## Existing Patterns to Reuse

- **`model_copy(update={...})` on frozen contracts**: Already used in `compute_greeks()` (line ~279) for `greeks`, `market_iv`, `greeks_source`. Adding `smoothed_iv` is identical.
- **Three-tier Greeks resolution**: Tier 1 (CBOE native), Tier 2 (local compute), Tier 3 (fail/exclude). IV smoothing becomes pre-processing in Tier 2.
- **`_PHASE3_FIELDS` + `_merge_signals()` + `_normalize_phase3_signals()`**: Phase 3 indicator registration. New fields just need entries in `_PHASE3_FIELDS` tuple.
- **`_render_optional(label, value, fmt)` in `_parsing.py`**: NaN-safe rendering for `float | None` fields. All surface fields use this.
- **`IndicatorSignals._normalize_non_finite` model_validator**: Auto-converts NaN/Inf → None at boundary. New fields inherit this automatically.
- **`ScanConfig` boolean toggle pattern**: `enable_iv_analytics: bool = True` — follow for `fit_vol_surface: bool = True`.
- **`PricingConfig.validate_all_finite` model_validator**: Only checks `float` fields. `bool` config fields (`use_parity_smoothing`) need no extra validator.
- **`validate_optional_finite` on MarketContext**: Single field_validator decorating all optional float fields. New fields must be added to its field list.
- **Exception isolation in `compute_phase3_indicators()`**: `try/except Exception` per indicator with `logger.warning()`.

## Existing Code to Extend

| File | What Exists | What Changes |
|------|-------------|-------------|
| `models/enums.py` (lines 132-141) | `GreeksSource(StrEnum)` with `COMPUTED`, `MARKET` | Add `SMOOTHED = "smoothed"` |
| `models/options.py` (lines 85-191) | `OptionContract` frozen model with `market_iv`, `bid_iv`, `ask_iv` | Add `smoothed_iv: float | None = None` + validator; add new `VolatilitySurface` model |
| `models/scan.py` (lines 31-132) | `IndicatorSignals` with 61 fields | Add 4 fields: `iv_surface_residual`, `atm_iv_interpolated`, `surface_fit_r2`, `smile_curvature_30d` |
| `models/analysis.py` (lines 52-162, 346-432) | `MarketContext` with 50+ optional float fields | Add 5 fields + extend `validate_optional_finite` field list |
| `models/config.py` (lines 37-261) | `ScanConfig` + `PricingConfig` | Add `fit_vol_surface: bool = True` and `use_parity_smoothing: bool = True` |
| `scoring/contracts.py` (lines 157-305) | `compute_greeks()` iterates contracts individually | Pre-group by (strike, exp), pair call/put, smooth, use smoothed IV as sigma |
| `scan/phase_options.py` (lines 92-140, ~500-535) | `_PHASE3_FIELDS` tuple; Phase 3 flow | Add 4 fields to tuple; insert surface fitting call after chain fetch |
| `scan/indicators.py` (lines 411-720) | `compute_phase3_indicators()` | Receive surface result, use `atm_iv_interpolated` when available |
| `agents/_parsing.py` (lines 466-531, 939-997) | `render_volatility_context()`, `render_context_block()` | Add VOLATILITY SURFACE rendering block |
| `pricing/__init__.py` | Re-exports `option_greeks`, `option_iv`, `option_price` only | `iv_smoothing.py` NOT added to `__init__` — scoring imports directly |
| `indicators/__init__.py` | Alphabetical `__all__` of all public functions | Add surface functions to import block + `__all__` |

**No longer modified** (Q1 resolution): `scoring/composite.py` and `scoring/normalization.py` — residual is a contract-level sort signal, not a universe-level scoring indicator.

## Potential Conflicts

- ~~**`INDICATOR_WEIGHTS` sum guard**~~ — **RESOLVED by Q1**: residual stays at contract level, no weight changes needed.
- ~~**Direction-dependent inversion**~~ — **RESOLVED by Q1**: sort key in `select_by_delta()` replaces `INVERTED_INDICATORS` entry.
- ~~**`SmoothBivariateSpline` minimum data**~~ — **RESOLVED by Q2**: adaptive degree (`kx = min(3, n_unique - 1)`) handles this automatically.
- **`validate_optional_finite` field list**: Single `@field_validator(...)` decorator in `MarketContext` lists every optional float field name. Missing a new field here means NaN/Inf silently passes validation.
- **IndicatorSignals field count**: Tests or docs may assert "61 fields" — adding 4 changes the count.
- **NamedTuple vs indicators convention**: indicators/ currently uses NO NamedTuples — functions return `pd.Series` or scalar `float` only. The PRD specifies NamedTuple, which is a reasonable extension for multi-value returns that aren't Series. This is a new pattern for the module — document in `indicators/CLAUDE.md`.

## Open Questions — RESOLVED

### Q1: Direction-dependent scoring → Contract-level sort key, not universe scoring

**Problem**: `INVERTED_INDICATORS` is a static frozenset. Overpriced IV is bad for longs but good for shorts. A frozenset can't express direction-dependent inversion.

**Resolution**: Don't put `iv_surface_residual` in `INDICATOR_WEIGHTS` at all. Add it to `OptionContract` as a field. After surface fitting, stamp each contract with its z-score. In `select_by_delta()`, add it as a sort tiebreaker: `(effective_distance, surface_penalty, strike)`. Positive residual = overpriced vol = sorts later. Works for both directions because `filter_contracts()` already selected the correct side (calls for longs, puts for shorts) — we always want cheaper vol.

**Eliminates**: FR-V7 weight redistribution, `INVERTED_INDICATORS` changes, direction-dependent inversion complexity. The recommended contract's residual flows naturally to `MarketContext` for agents.

### Q2: 2D spline threshold → Adaptive degree from data

**Problem**: scipy `SmoothBivariateSpline(kx=3, ky=3)` needs >16 points. PRD says 6.

**Resolution**: Adapt the spline degree to available data: `kx = min(3, n_unique_moneyness - 1)`, `ky = min(3, n_unique_dte - 1)`. If `ky < 1` (single DTE): 1D fallback. If `kx < 1` (single strike): return None. The PRD's 6-point minimum stays as an absolute floor pre-filter. Catch scipy `ValueError`, retry with reduced degree, then `None`.

This is mathematically rigorous — a cubic through 3 unique DTEs degrades naturally to linear in the DTE dimension. No magic thresholds.

### Q3: ATM IV interpolated → Coexist, don't replace

**Problem**: `atm_iv_30d` feeds `iv_hv_spread` (existing indicator in 21-weight composite). Replacing it silently changes all scan rankings.

**Resolution**: `atm_iv_interpolated` is a new parallel field. `atm_iv_30d` continues feeding `iv_hv_spread` unchanged. Both flow to `MarketContext`. Agents see both — the discrepancy itself is a signal. Zero behavioral change to existing indicators, zero test regressions. If surface ATM IV proves reliably better, swapping is a one-line change in a future PR.

### Q4: Smoothing scope → Smooth all contracts once, feed everything downstream

**Problem**: Surface fitting needs IVs from ALL expirations. Greeks need smoothed IV. Where does smoothing happen?

**Resolution**: Insert one step in `process_ticker_options()` after `all_contracts` flattening (line 490), before `compute_options_indicators()` (line 501):
```python
if pricing_config.use_parity_smoothing:
    all_contracts = smooth_chain_iv(all_contracts)
```
`smooth_chain_iv()` is a pure function in `scoring/contracts.py`: groups by (strike, expiration), pairs call/put, returns new contracts with `smoothed_iv` populated. One O(n) pass feeds both surface fitting and Greeks computation. In `compute_greeks()`, one line change: `sigma = contract.smoothed_iv or contract.market_iv`.

### Q5: Config placement → Each controls its semantic owner

**Resolution**:
- `PricingConfig.use_parity_smoothing: bool = True` — IV preparation is a pricing concern. `compute_greeks()` already receives `PricingConfig`.
- `ScanConfig.fit_vol_surface: bool = True` — surface fitting is a pipeline orchestration concern.

The two are independent: smoothing improves Greeks even without surface fitting. Surface fitting works (less well) without smoothing. Independent toggles respect this.

## Recommended Architecture

```
NEW FILES (2):
  src/options_arena/pricing/iv_smoothing.py          (~60 LOC, pure scalar math)
  src/options_arena/indicators/volatility_surface.py  (~200 LOC, numpy/scipy)

MODIFIED FILES (9):
  models/enums.py          → GreeksSource.SMOOTHED
  models/options.py        → OptionContract.smoothed_iv + iv_surface_residual + VolatilitySurface model
  models/config.py         → PricingConfig.use_parity_smoothing + ScanConfig.fit_vol_surface
  models/scan.py           → 4 new IndicatorSignals fields (surface metrics for MarketContext)
  models/analysis.py       → 5 new MarketContext fields + validators
  scoring/contracts.py     → smooth_chain_iv() + compute_greeks() smoothed_iv + select_by_delta() residual sort
  scan/phase_options.py    → _PHASE3_FIELDS + smoothing step + surface fitting call
  scan/indicators.py       → compute_phase3_indicators() surface integration
  agents/_parsing.py       → VOLATILITY SURFACE rendering block

NOT MODIFIED (Q1 resolution):
  scoring/composite.py     — no weight redistribution needed
  scoring/normalization.py — no INVERTED_INDICATORS changes needed
```

**Data flow** (reflecting resolved Q1-Q5):
```
process_ticker_options() in scan/phase_options.py:
  1. Fetch chain → flatten all_contracts (line 488-490)
  2. [NEW] smooth_chain_iv(all_contracts)           # Q4: one pass, feeds everything
  │     └─> pricing/iv_smoothing.smooth_iv_parity() per (strike,exp) pair
  │     └─> model_copy(update={"smoothed_iv": ...}) on each contract
  3. compute_options_indicators(all_contracts, spot) # existing (line 501)
  4. [NEW] fit_volatility_surface(strikes, dtes, smoothed_ivs, spot)
  │     └─> indicators/volatility_surface: VolSurfaceFitResult
  │     └─> stamp iv_surface_residual on each contract via model_copy
  5. compute_phase3_indicators(all_contracts, ...)   # existing (line 517)
  │     └─> surface fields flow into IndicatorSignals via _merge_signals
  6. recommend_contracts(all_contracts, ...)          # existing (line 553)
        └─> compute_greeks(): sigma = smoothed_iv or market_iv
        └─> select_by_delta(): sort key includes iv_surface_residual
        └─> recommended contract carries residual → MarketContext → agents
```

**Key architectural decisions**:
- IV smoothing: pure scalar function in `pricing/iv_smoothing.py`, bulk wrapper `smooth_chain_iv()` in `scoring/contracts.py`
- Surface fitting: numpy/scipy in `indicators/volatility_surface.py`, called from `scan/phase_options.py`
- Residual lives on `OptionContract` (not `INDICATOR_WEIGHTS`): contract-level signal in `select_by_delta()` sort key
- `atm_iv_interpolated` coexists with `atm_iv_30d` — never replaces existing indicator inputs
- Spline degree adapts to data (`kx = min(3, n_unique - 1)`) — no magic thresholds
- Config: `PricingConfig.use_parity_smoothing` + `ScanConfig.fit_vol_surface` (independent toggles)
- Graceful degradation: sparse data → None fields, pipeline continues unaffected

## Test Strategy Preview

- **Pricing tests**: `tests/unit/pricing/test_iv_smoothing.py` — ~20 parametrized tests, pure math, no mocks. Cover: equal IVs, one-sided (call-only/put-only), zero-bid, wildly different IVs, NaN/Inf inputs. Use `pytest.approx(rel=1e-6)`.
- **Indicator tests**: `tests/unit/indicators/test_volatility_surface.py` or `tests/unit/scan/test_volatility_surface.py` — ~25 tests. Synthetic IV surfaces with known analytical solutions. Cover: well-fitted surface, sparse data (None return), single-expiration (1D fallback), all-NaN IVs, R² quality thresholds.
- **Scoring tests**: Extend `tests/unit/scoring/test_contracts.py` — ~15 tests for parity smoothing integration in `compute_greeks()`. Mock `smooth_iv_parity` at module boundary. Cover: paired call/put, unpaired, CBOE-preserved (Tier 1 unaffected), config disabled.
- **Integration tests**: Extend `tests/unit/scan/test_phase_options.py` — ~10 tests for surface fitting in Phase 3 pipeline. Cover: field merge into IndicatorSignals, config disabled, sparse chain fallback.
- **Agent tests**: Extend `tests/unit/agents/test_parsing.py` — ~10 tests for rendering block. Cover: all fields populated, all None, mixed.
- **Mocking pattern**: `patch("options_arena.scoring.contracts.smooth_iv_parity")` for scoring tests. `patch("options_arena.indicators.volatility_surface.SmoothBivariateSpline")` for surface tests if needed.
- **Test fixtures**: `make_contract()` factory in `tests/unit/scoring/conftest.py` already supports keyword overrides — use for parity pairs.

## Estimated Complexity

**M-L (Medium-Large)** — revised down from L after resolving open questions:
- 2 new files + 9 modified files across 6 modules (composite.py and normalization.py no longer modified — Q1 resolution eliminates FR-V7 weight redistribution)
- ~70 new tests across 3-5 test files
- New scipy usage pattern (`SmoothBivariateSpline`) not yet in codebase
- Multiple integration points in the scan pipeline
- ~350 LOC new code + ~200 LOC test code

Complexity bounded by: zero new dependencies, pure computation insertion (no new data sources or API calls), all new fields are optional with None defaults (backward-compatible), no weight redistribution (Q1), no existing indicator behavioral changes (Q3), and the two core algorithms are well-understood math.
