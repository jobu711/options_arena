---
name: volatility-intelligence
status: backlog
created: 2026-03-14T14:08:52Z
progress: 0%
prd: .claude/prds/volatility-intelligence.md
github: https://github.com/jobu711/options_arena/issues/499
---

# Epic: volatility-intelligence

## Overview

Add put-call parity IV smoothing and per-contract mispricing detection to the options pipeline. IV smoothing pairs call/put IVs at the same strike to cancel bid-ask noise before Greeks computation. Mispricing z-scores from the already-fitted vol surface (native-quant) identify contracts where the market is pricing vol too high or too low. Zero new dependencies — scipy already in tree.

## Architecture Decisions

- **IV smoothing in `pricing/iv_smoothing.py`**: Scalar float in/out, no pandas — matches pricing module convention. Liquidity-weighted average using inverse relative spread.
- **Surface indicators complete existing stub**: `indicators/vol_surface.py` already has `VolSurfaceIndicators` NamedTuple and `compute_surface_indicators()` stub from native-quant. This epic fills them in — no new files in indicators/.
- **Mispricing as tiebreaker, not weight**: `iv_surface_residual` is direction-dependent (overpriced vol is bad for buyers, good for sellers). Added as contract-level tiebreaker in `select_by_delta()`, NOT in `INDICATOR_WEIGHTS`. Avoids weight redistribution complexity.
- **Enhance existing `render_volatility_context()`**: Function already exists in `agents/_parsing.py` from native-quant (lines 466-548). Add surface mispricing fields — no new rendering function needed.
- **Config toggles for backward compat**: `PricingConfig.use_parity_smoothing: bool = True`, `ScanConfig.fit_vol_surface: bool = True`. Both default on but can be disabled.

## Technical Approach

### New File (1)
- `src/options_arena/pricing/iv_smoothing.py` — `smooth_iv_parity()` function. Scalar float in/out, liquidity-weighted put-call parity averaging.

### Modified Files (up to 9)
- `models/enums.py` — Add `SMOOTHED` to `GreeksSource`
- `models/options.py` — Add `smoothed_iv: float | None` to `OptionContract`
- `models/config.py` — Add config toggles to `PricingConfig` and `ScanConfig`
- `models/analysis.py` — Add 3 fields to `MarketContext` + validators
- `scoring/contracts.py` — IV smoothing in `compute_greeks()`, tiebreaker in `select_by_delta()`
- `indicators/vol_surface.py` — Complete `VolSurfaceIndicators` + `compute_surface_indicators()`
- `scan/phase_options.py` — Call `compute_surface_indicators()` after contract recommendation, map to signals
- `agents/_parsing.py` — Enhance `render_volatility_context()` with mispricing fields
- `api/schemas.py` — Add 3 vol surface fields to API response schema

### No Migration Needed
Surface residual and R² flow through `IndicatorSignals` → `ticker_scores` JSON blob (already schema-flexible). `smoothed_iv` is ephemeral (used during Greeks computation, not persisted separately). No new SQLite columns required.

## Implementation Strategy

### Wave 1 (Parallel — no dependencies between them)
- **Issue 1**: IV smoothing foundation (new file + model extensions)
- **Issue 3**: Surface indicators completion (extend existing stub)

### Wave 2 (Depends on Wave 1)
- **Issue 2**: Smoothing integration into `compute_greeks()`
- **Issue 4**: Pipeline integration + MarketContext fields

### Wave 3 (Depends on Wave 2)
- **Issue 5**: Agent prompt enrichment + scoring tiebreaker

### Risk Mitigation
- Config toggles ensure backward compatibility — disable smoothing/surface if issues arise
- All new model fields are `Optional` with `None` defaults — zero regression risk
- `compute_greeks()` modification is the highest-risk change — test exhaustively

### Testing Approach
- Unit tests for `smooth_iv_parity()` edge cases (NaN, single-side, wide spreads, zero-bid)
- Unit tests for `compute_surface_indicators()` mapping (empty result, valid z-scores, single-DTE)
- Integration tests for smoothing through `compute_greeks()` pipeline
- Integration tests for surface indicators through Phase 3
- Parametrized edge cases: sparse chains, single-DTE, all-NaN IVs

## Task Breakdown Preview

- [ ] Issue 1: IV smoothing function + model extensions — Create `pricing/iv_smoothing.py`, add `SMOOTHED` to `GreeksSource`, add `smoothed_iv` to `OptionContract`, add `use_parity_smoothing` config toggle. ~20 tests.
- [ ] Issue 2: Smoothing integration into `compute_greeks()` — Group contracts by (strike, expiration), call `smooth_iv_parity()`, use smoothed IV as sigma, set `greeks_source=SMOOTHED`. ~15 tests.
- [ ] Issue 3: Surface indicators completion — Fill `VolSurfaceIndicators` NamedTuple fields, implement `compute_surface_indicators()` to map contract keys to z-scores from `VolSurfaceResult`. Add `fit_vol_surface` config toggle. ~25 tests.
- [ ] Issue 4: Pipeline + MarketContext integration — Add `iv_surface_residual`, `surface_fit_r2`, `surface_is_1d` to `MarketContext` with validators. Add to `IndicatorSignals`. Wire `compute_surface_indicators()` into `phase_options.py`. Add to API schemas. ~10 tests.
- [ ] Issue 5: Agent prompt enrichment + scoring tiebreaker — Enhance `render_volatility_context()` with mispricing section. Add delta tiebreaker in `select_by_delta()` favoring underpriced vol for BULLISH, overpriced for BEARISH. ~10 tests.

## Dependencies

### Internal (all satisfied)
- `native-quant` epic complete (merged 2026-03-13) — `vol_surface.py` exists with 624 LOC
- `VolSurfaceResult` NamedTuple with `z_scores`, `r_squared`, `is_1d_fallback` fields
- `render_volatility_context()` exists in `_parsing.py` — enhancement only
- `compute_vol_surface()` already called in `phase_options.py`

### External
- None. scipy `SmoothBivariateSpline`/`UnivariateSpline` already in dependency tree.

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Parity smoothing applied | >60% of contracts with both call+put at same strike |
| Surface fit R² (liquid chains) | >0.85 mean on top 20 S&P 500 |
| `iv_surface_residual` populated | >50% of debate tickers |
| Existing test suite | 100% pass (zero regressions) |
| New tests | ~80 across unit + integration |
| Config toggle off | Behavior identical to pre-epic |

## Estimated Effort

- **Size**: Large (L)
- **New file**: 1 (`pricing/iv_smoothing.py`)
- **Modified files**: Up to 9 across 6 modules
- **New tests**: ~80
- **Critical path**: Issue 1 → Issue 2 → Issue 4 → Issue 5 (4 sequential steps)
- **Parallelizable**: Issues 1 and 3 (Wave 1)

## Tasks Created

- [ ] #500 - IV Smoothing Foundation (parallel: true)
- [ ] #501 - Smoothing Integration into compute_greeks (parallel: false, depends: #500)
- [ ] #502 - Surface Indicators Completion (parallel: true)
- [ ] #503 - Pipeline + MarketContext Integration (parallel: false, depends: #501, #502)
- [ ] #504 - Agent Prompt Enrichment + Scoring Tiebreaker (parallel: false, depends: #503)

Total tasks: 5
Parallel tasks: 2 (#500, #502 — Wave 1)
Sequential tasks: 3 (#501, #503, #504 — Waves 2-3)

## Test Coverage Plan

Total test files planned: 5
Total test cases planned: ~55
