# Research: volatility-intelligence

## PRD Summary

Add two compounding volatility techniques: (1) put-call parity IV smoothing — pairing call/put IVs at same strike to cancel bid-ask noise before Greeks computation, and (2) fitted implied volatility surface with per-contract mispricing z-scores. Cleaner IVs → better surface fit → accurate mispricing → higher-alpha contract selection. Zero new dependencies (scipy already in tree).

## Relevant Existing Modules

- **`pricing/`** — BSM + BAW pricing, Greeks, IV. Scalar float in/out, no pandas. New `iv_smoothing.py` file created here. Boundary: cannot import services, indicators, scoring.
- **`indicators/`** — Pure numpy/scipy math. `vol_surface.py` (624 LOC) already exists from native-quant with `VolSurfaceResult` NamedTuple, tiered `compute_vol_surface()`, fitted surface implementation, and `compute_surface_indicators()` stub. Boundary: no Pydantic models, no API calls.
- **`scoring/`** — Normalization, composite, direction, contract selection. `contracts.py` has `compute_greeks()` and `select_by_delta()`. Boundary: imports `pricing/dispatch` only.
- **`scan/`** — 4-phase async pipeline. `phase_options.py` already imports and calls `compute_vol_surface()`. Integration point for surface indicators after contract recommendation.
- **`models/`** — Pydantic v2 models. `OptionContract` (frozen), `GreeksSource` enum, `MarketContext` (4 vol fields from native-quant), `IndicatorSignals` (65 fields). No logic, no I/O.
- **`agents/`** — PydanticAI debate. `_parsing.py` already has `render_volatility_context()` (lines 466-548) from native-quant — needs enhancement with surface mispricing fields.
- **`api/`** — FastAPI REST + WebSocket. `schemas.py` already has `skew_25d`, `smile_curvature`. Needs 3 new fields.

## Existing Patterns to Reuse

- **Frozen model updates**: `model_copy(update={...})` on `OptionContract` (used throughout `contracts.py`)
- **NaN/Inf defense**: `math.isfinite()` validators on all float|None fields (45+ existing in `validate_optional_finite`)
- **Tiered computation**: `compute_vol_surface()` already has Tier 1 (fitted) → Tier 2 (standalone) fallback pattern
- **Domain context rendering**: `_render_optional(label, value, fmt)` helper in `_parsing.py` for consistent None-safe formatting
- **Config toggles**: `ScanConfig.enable_iv_analytics: bool = True` pattern for opt-in features
- **Indicator weight guards**: Import-time `sum == 1.0` check in `composite.py`
- **Migration pattern**: Sequential SQL files in `data/migrations/` (latest: 032)

## Existing Code to Extend

### `indicators/vol_surface.py` (624 LOC — native-quant)
- `VolSurfaceResult` NamedTuple: 11 fields including `fitted_ivs`, `residuals`, `z_scores`, `r_squared`, `is_1d_fallback`, `is_standalone_fallback`
- `compute_vol_surface()`: Full tiered approach, Tier 1 fitted surface implemented with `SmoothBivariateSpline`
- `_fit_surface()` (lines 182-319): Already handles log-moneyness, sqrt-time, spline evaluation, residual/z-score/R² computation
- **Stub**: `VolSurfaceIndicators` NamedTuple (lines 601-605) — empty, needs fields
- **Stub**: `compute_surface_indicators()` (lines 608-623) — returns empty result, needs implementation

### `scoring/contracts.py` (494 LOC)
- `compute_greeks()` (lines 158-332): Currently uses `contract.market_iv` directly. Integration point for IV smoothing grouping by (strike, expiration).
- `select_by_delta()` (lines 360-438): Currently sorts by effective delta distance / liquidity + strike. Tiebreaker insertion point at lines 404-408.

### `agents/_parsing.py` (900+ LOC)
- `render_volatility_context()` (lines 466-548): **ALREADY EXISTS** from native-quant. Renders HV & Vol Surface section with `hv_yang_zhang`, `skew_25d`, `smile_curvature`, `prob_above_current`. **Missing**: `iv_surface_residual`, `surface_fit_r2` — this epic adds them.

### `models/analysis.py` — MarketContext (lines 52-479)
- 4 vol fields already present (lines 172-176): `hv_yang_zhang`, `skew_25d`, `smile_curvature`, `prob_above_current`
- All added to `validate_optional_finite` (lines 415-418)
- Pattern: add new fields after line 176, add to validator list

### `models/enums.py` — GreeksSource (lines 136-145)
- Currently: `COMPUTED`, `MARKET`. Add `SMOOTHED`.

### `models/config.py`
- `PricingConfig` (lines 69-89): Add `use_parity_smoothing: bool = True`
- `ScanConfig` (lines 28-67): Add `fit_vol_surface: bool = True`

## Potential Conflicts

- **`vol_surface.py` shared file**: native-quant created it, this epic extends it. Risk of merge conflict if native-quant has pending changes. **Mitigation**: native-quant is complete and merged (2026-03-13) — no conflict expected.
- **IndicatorSignals field count**: Already 65 fields. Adding 3 more (68 total). No functional issue but test parametrization may be affected. **Mitigation**: New fields are all Optional with None defaults.
- **INDICATOR_WEIGHTS sum guard**: `iv_surface_residual` is NOT added to weights (direction-dependent). No weight redistribution needed. **Mitigation**: tiebreaker-only integration avoids sum conflicts.
- **compute_greeks() modification**: Adding grouping logic changes a critical function. **Mitigation**: opt-in via `PricingConfig.use_parity_smoothing`, existing tests pass without smoothing.

## Open Questions

1. **Does `_fit_surface()` in native-quant already compute z-scores?** — Research confirms YES: `VolSurfaceResult` has `z_scores` field, computed in `_fit_surface()`. `compute_surface_indicators()` just needs to map contract keys to these z-scores.
2. **Does `render_volatility_context()` need a full rewrite or just enhancement?** — Enhancement only. The function exists and works. Add surface mispricing section after existing HV & Vol Surface block.
3. **Should migration 033 add columns to `recommended_contracts` or `ticker_scores`?** — Both: `iv_surface_residual` and `surface_fit_r2` should go on `ticker_scores` (indicator-level). `smoothed_iv` could go on `recommended_contracts` (contract-level audit trail).

## Recommended Architecture

### Implementation approach:
1. **Issue 1** (IV Smoothing Foundation): Create `pricing/iv_smoothing.py` with `smooth_iv_parity()`. Extend `GreeksSource` with `SMOOTHED`. Add `smoothed_iv` to `OptionContract`. Add `use_parity_smoothing` config toggle. ~20 tests.

2. **Issue 2** (Smoothing Integration): Modify `scoring/contracts.py` `compute_greeks()` to group by (strike, expiration), call `smooth_iv_parity()`, store result, use as sigma. ~15 tests.

3. **Issue 3** (Surface Indicators — parallel with 1): Complete `VolSurfaceIndicators` NamedTuple fields. Implement `compute_surface_indicators()` — map contract (strike, dte) keys to z-scores from `VolSurfaceResult`. Add `fit_vol_surface` config toggle. ~25 tests.

4. **Issue 4** (Pipeline + Models): Add 3 fields to `MarketContext`, 3 to `IndicatorSignals`, 3 to API schemas. Create migration 033. Integrate `compute_surface_indicators()` call in `phase_options.py` after contract recommendation. ~10 tests.

5. **Issue 5** (Agent Enrichment + Tiebreaker): Enhance `render_volatility_context()` with surface mispricing section. Add delta tiebreaker in `select_by_delta()`. ~10 tests.

### Dependency graph:
```
Issue 1 (IV smoothing) ──→ Issue 2 (scoring integration) ──┐
                                                             ├──→ Issue 4 (pipeline) ──→ Issue 5 (agents + tiebreaker)
Issue 3 (surface indicators) ──────────────────────────────┘
```

Issues 1 and 3 can run in parallel.

## Test Strategy Preview

- **Existing test patterns**: `tests/unit/pricing/`, `tests/unit/indicators/`, `tests/unit/scoring/` — parametrized tests with `@pytest.mark.parametrize`, fixtures for market data
- **Native-quant test files**: `tests/integration/test_native_quant_pipeline.py`, `tests/integration/test_native_quant_api.py` — pattern to follow for integration tests
- **Domain renderer tests**: `tests/unit/agents/test_domain_renderers.py` — test rendering functions
- **New test files expected**:
  - `tests/unit/pricing/test_iv_smoothing.py` (~20 tests)
  - `tests/unit/scoring/test_smoothing_integration.py` (~15 tests)
  - `tests/unit/indicators/test_surface_indicators.py` (~25 tests)
  - Enhancement of existing integration tests (~20 tests)
- **Mocking**: `unittest.mock.patch` for config toggles, synthetic option chains for surface fitting
- **Parametrized edge cases**: NaN IVs, single-side strikes, sparse chains, single-DTE, wide spreads

## Estimated Complexity

**Large (L)** — Justification:
- 1 new file + 9 modified files across 6 modules
- Critical path through pricing → scoring → scan → models → agents
- Non-trivial scipy surface fitting with quality gates and graceful degradation
- ~80 new tests across 3-4 test files
- Shared file coordination with native-quant (merged, but requires understanding 624 LOC)
- Multiple edge cases (sparse chains, single-DTE, NaN IVs, zero-bid contracts)
- Config toggles for backward compatibility
- Database migration for persistence
