---
name: dead-code-audit
description: Remove ~1,720 lines of dead code, wire 16 never-connected indicator functions, and modernize the DebatePhase enum to match the 6-agent protocol
status: planned
created: 2026-03-16T22:00:00Z
depends_on: complexity-reduction
---

# PRD: Dead Code Audit & Pipeline Wiring

## Executive Summary

A comprehensive dead-code audit of Options Arena identified 56 findings across 17 modules: 38 dead functions/fields/classes, 6 redundancies, 5 simplifications, and 7 low-alpha items. This PRD addresses all findings in 4 execution waves. Waves 1-3 are pure subtraction (~1,270 lines removed). Wave 4 is additive — wiring 16 never-connected indicator functions into the scan pipeline and modernizing the `DebatePhase` enum to match the 6-agent protocol.

**Relationship to `complexity-reduction` PRD**: That PRD covers OpenBB removal, EGARCH deletion, dead HV estimators, and `classify_market_regime()` removal. This PRD covers everything else found in the audit. Items already handled by `complexity-reduction` are marked "SKIP — covered by complexity-reduction" and excluded from scope.

## Problem Statement

The codebase has accumulated dead code through 34 epics across 9 development phases:

1. **Legacy debate protocol**: The old bull/bear 2-agent debate was replaced by a 6-agent protocol, but `bull.py`, `bear.py`, their prompt files, 8 `DebateDeps` fields, and several helper functions were never removed (~250 lines).
2. **Never-wired indicators**: 16 indicator functions are fully implemented and tested but never called from the scan pipeline. Their corresponding `IndicatorSignals` fields are always `None`. The `hurst_exponent` even has a composite weight (0.01) that silently redistributes.
3. **Dead repository methods**: 6 query methods persist data that is never read back.
4. **Dead config/model fields**: 7 config fields control features that don't exist. 3 `MarketContext` fields are never populated. 4 model methods have zero production callers.
5. **Stale API surface**: 3 unused DI providers, 1 dead schema, dead `__init__.py` re-exports across 3 modules.

## User Stories

1. **As a contributor**, I want dead legacy code removed so grep results don't include false positives from the old bull/bear debate path.
   - AC: `bull.py`, `bear.py`, and all associated dead fields/helpers deleted.
2. **As a user**, I want all implemented indicators wired into the pipeline so my scan scores reflect the full signal set.
   - AC: `hurst_exponent` and 15 other indicator functions produce values in `IndicatorSignals` during scans.
3. **As a maintainer**, I want config fields that control nothing removed so I don't debug phantom feature flags.
   - AC: `enable_clustering`, `contract_n_clusters`, `enable_flow_anomaly`, `enable_regime_weights` deleted.
4. **As a developer**, I want the `DebatePhase` enum to reflect the actual 6-agent protocol so WebSocket progress events are meaningful.
   - AC: `DebatePhase` has members TREND, VOLATILITY, FLOW, FUNDAMENTAL, RISK, CONTRARIAN. Progress callback invoked per agent.

## Architecture & Design

### Wave 1 — Legacy Debate Removal (zero risk, pure subtraction)

| File | Change |
|------|--------|
| `agents/bull.py` | **Delete entire file** |
| `agents/bear.py` | **Delete entire file** |
| `agents/prompts/bull.py` | **Delete entire file** |
| `agents/prompts/bear.py` | **Delete entire file** |
| `agents/prompts/__init__.py` | Remove BULL/BEAR exports |
| `agents/_parsing.py` | Remove 8 dead `DebateDeps` fields: `opponent_argument`, `bear_counter_argument`, `bull_response`, `bear_response`, `bull_rebuttal`, `vol_response`, `spread_analysis`, `constraint_warnings` |
| `agents/orchestrator.py` | Remove 6 kwarg sites that set dead DebateDeps fields. Delete `_opposite_direction()` (line 778). Remove `_resolve_api_key()` from `model_config.py` (line 286) |
| `agents/_parsing.py` | Delete `build_cleaned_trade_thesis()` (line 123) |
| `agents/volatility.py` | Delete dead `if ctx.deps.bull_response` block (lines 44-51) |
| `agents/flow_agent.py` | Delete dead `if ctx.deps.bull_response` block (lines 45-52) |
| `agents/fundamental_agent.py` | Delete dead `if ctx.deps.bull_response` block (lines 49-56) |
| `api/deps.py` | Delete `get_financial_datasets()`, `get_intelligence()`, `get_openbb()` DI providers |
| `api/schemas.py` | Delete `SectorInfo` class (line 685) |
| `models/analysis.py` | Remove 3 dead `MarketContext` fields: `ml_regime`, `ml_regime_confidence`, `flow_anomaly_score` |
| `models/config.py` | Remove 4 dead fields: `MLConfig.enable_clustering`, `.contract_n_clusters`, `.enable_flow_anomaly`, `DebateConfig.enable_regime_weights`. Remove `contract_n_clusters` validator |
| `models/openbb.py` | Delete `OpenBBHealthStatus` class (line 179) |

**Estimated removal**: ~400 lines source + ~300 lines tests

### Wave 2 — Dead Function Removal (zero risk, pure subtraction)

| File | Change |
|------|--------|
| `scoring/clustering.py` | **Delete entire file** (351 lines) — or move to `analysis/` if future wiring is desired |
| `scoring/__init__.py` | Remove `cluster_contracts_by_greeks` export |
| `scoring/dimensional.py` | Delete `apply_regime_weights()` (line 233) and `REGIME_WEIGHT_PROFILES` dict |
| `scoring/__init__.py` | Remove `apply_regime_weights` export |
| `services/helpers.py` | Delete `fetch_with_retry()` (~50 lines) |
| `services/market_data.py` | Delete `fetch_universe_data()`, `UniverseData` dataclass, `_serialize_universe_data()`, `_deserialize_universe_data()` (~100 lines) |
| `pricing/neural_surface.py` | Delete `predict_iv()` (~60 lines) |
| `models/enums.py` | Remove `SpreadType.CALENDAR` and `SpreadType.BUTTERFLY` |
| `data/_metadata.py` | Delete `get_ticker_metadata()` (singular, line 87) |
| `data/_analytics.py` | Delete `get_normalization_stats()` (line 215), `get_outcomes_for_contract()` (line 350), `has_outcome()` (line 406) |
| `data/_spreads.py` | Delete `get_spread_recommendations()` (line 121) |
| `data/_scan.py` | Delete `get_last_debate_dates()` (line 333) |
| `models/analysis.py` | Delete `MarketContext.dse_ratio()`, `.financial_datasets_ratio()`, `.intelligence_ratio()` |
| `models/intelligence.py` | Delete `IntelligencePackage.intelligence_completeness()` |
| `utils/exceptions.py` | Delete `RateLimitExceededError` class |
| `api/app.py` | Remove `RateLimitExceededError` exception handler registration |

**Estimated removal**: ~750 lines source + ~400 lines tests

### Wave 3 — Re-export Cleanup & Dedup (zero risk, pure subtraction)

| File | Change |
|------|--------|
| `indicators/__init__.py` | Remove exports: `put_call_ratio_oi`, `map_regime_label_to_market_regime`, `test_stationarity` |
| `indicators/vol_forecast.py` | Rename `test_stationarity()` to `_test_stationarity()` |
| `services/__init__.py` | Remove exports: `filter_by_sectors`, `filter_by_industry_groups`, `classify_market_cap`, `BatchOHLCVResult`, `TickerOHLCVResult` |
| `analysis/__init__.py` | Remove individual valuation function exports (`compute_owner_earnings_dcf`, `compute_three_stage_dcf`, `compute_ev_ebitda_relative`, `compute_residual_income`) — keep `compute_composite_valuation` |
| `services/market_data.py` | Replace `_classify_market_cap()` with import from `services/universe.py::classify_market_cap()` |
| `reporting/debate_export.py`, `api/schemas.py`, `cli/rendering.py` | Extract `_UNLIMITED_SENTINEL = "999999.99"` to shared constant in `models/constants.py` (or `utils/`) |
| `reporting/CLAUDE.md` | Update to reflect actual file structure (only `debate_export.py`) and Markdown-only format |

**Estimated removal**: ~40 lines source, ~20 lines dedup

### Wave 4 — Indicator Wiring & DebatePhase Modernization (additive)

#### 4a. Wire `hurst_exponent` into Phase 2

| File | Change |
|------|--------|
| `scan/phase_scoring.py` | Add `hurst_exponent(close_series)` call in Phase 2 indicator computation. Map result to `IndicatorSignals.hurst_exponent` |

The weight (0.01), field, DOMAIN_BOUNDS, and family mapping already exist. Only the computation call is missing.

#### 4b. Wire 15 indicator functions into scan pipeline

These require additional data plumbing. Group by data dependency:

**Group A — Require VIX / cross-asset data (Phase 2, extend market data fetch)**:
- `compute_vix_term_structure()` — needs VIX futures or VIX spot
- `compute_risk_on_off()` — needs HYG, LQD ETF prices
- `compute_vix_correlation()` — needs VIX series

**Group B — Require sector/benchmark data (Phase 2)**:
- `compute_sector_momentum()` — needs sector ETF price
- `classify_market_regime()` — SKIP (covered by `complexity-reduction` PRD)

**Group C — Require option chain data (Phase 3, post-chain-fetch)**:
- `compute_pop()` — needs Greeks + contract data
- `compute_optimal_dte()` — needs DTE + theta/gamma ratio
- `compute_spread_quality()` — needs bid-ask spread data
- `compute_max_loss_ratio()` — needs contract premium + strike
- `detect_flow_anomalies()` — needs OI/volume data (already available in Phase 3)
- `compute_short_interest()` — needs `ticker_info.short_ratio` (available from `fetch_ticker_info`)

**Group D — Require vol surface data (Phase 3, post-surface-fit)**:
- `compute_put_skew()` — needs put-side IV curve
- `compute_call_skew()` — needs call-side IV curve
- `compute_skew_ratio()` — needs both skew values
- `put_call_ratio_oi()` — needs OI data (already available)

For each function wired:
1. Add computation call in appropriate scan phase
2. Map result to corresponding `IndicatorSignals` field
3. If no `IndicatorSignals` field exists, verify it does and add DOMAIN_BOUNDS entry if missing
4. Add integration test verifying the field is populated during a scan

#### 4c. Modernize `DebatePhase` enum

| File | Change |
|------|--------|
| `agents/orchestrator.py` | Replace `DebatePhase` members: `BULL` -> `TREND`, `BEAR` -> `VOLATILITY`, `REBUTTAL` -> `FLOW`, `VOLATILITY` -> `FUNDAMENTAL` (or add new members: `TREND`, `VOLATILITY`, `FLOW`, `FUNDAMENTAL`, `RISK`, `CONTRARIAN`) |
| `agents/orchestrator.py` | Wire `_progress` callback in `_run_debate_pipeline()` — emit progress event before each agent run |
| `api/ws.py` | Update WebSocket message types to match new enum values |

**Estimated addition**: ~150 lines source + ~200 lines tests

## Requirements

### Functional Requirements

1. All scan pipeline results remain identical after Waves 1-3 (pure subtraction of dead code)
2. After Wave 4a, `hurst_exponent` appears in scan results with non-None values
3. After Wave 4b, all 15 wired indicators populate their `IndicatorSignals` fields when data is available
4. After Wave 4c, WebSocket debate progress events report per-agent phase names matching the 6-agent protocol
5. No exported symbol exists with zero call sites in pipeline, API, or CLI (verified by grep)

### Non-Functional Requirements

1. `mypy --strict` passes after each wave
2. `ruff check` passes after each wave
3. All remaining tests pass after each wave (tests for deleted code are also deleted)
4. No new dependencies added
5. Each wave is an atomic commit — tests green at every boundary

## Testing Strategy

### Tests to delete (Waves 1-2)
- `tests/unit/agents/test_bull.py`
- `tests/unit/agents/test_bear.py`
- Tests for `build_cleaned_trade_thesis()` in `test_prompt_enhancements.py`
- Tests for `_opposite_direction()` in `test_orchestrator.py`
- Tests for `_resolve_api_key()` in `test_model_config.py`
- Tests for `cluster_contracts_by_greeks()` in scoring tests
- Tests for `apply_regime_weights()` in dimensional scoring tests
- Tests for `fetch_with_retry()` in helpers tests
- Tests for `fetch_universe_data()` in market data tests
- Tests for `predict_iv()` in neural surface tests
- Tests for 6 dead repository methods across data test files
- Tests for `SectorInfo` in `test_schemas.py`
- Tests for `OpenBBHealthStatus` in `test_openbb_models.py`
- Tests for `RateLimitExceededError` in `test_exceptions.py`
- Tests for dead `MarketContext` methods (`dse_ratio`, `financial_datasets_ratio`, `intelligence_ratio`)
- Tests for `IntelligencePackage.intelligence_completeness()`
- Tests asserting `SpreadType` member count (update count)

### Tests to add (Wave 4)
- Integration test: `hurst_exponent` populated during scan
- Integration tests: each newly-wired indicator function produces non-None output with valid input data
- Unit tests: `DebatePhase` has exactly 6 members matching protocol
- Integration test: WebSocket debate progress emits all 6 phase events

### Verification (after each wave)
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest -m "not exhaustive" -n auto -q
uv run mypy src/ --strict
```

## Success Criteria

1. All tests pass after each wave
2. `mypy --strict` clean
3. No function exported from any `__init__.py` has zero pipeline/API call sites
4. `DebateDeps` has 8 fields (down from 16)
5. `bull.py`, `bear.py`, `prompts/bull.py`, `prompts/bear.py` do not exist
6. `scoring/clustering.py` does not exist (or lives in `analysis/`)
7. `hurst_exponent` and all Group C/D indicators produce values during scans
8. WebSocket debate progress reports TREND/VOLATILITY/FLOW/FUNDAMENTAL/RISK/CONTRARIAN phases
9. `DebatePhase` enum has exactly 6 members matching the 6-agent protocol

## Constraints & Assumptions

- Wave 4b Group A (VIX/cross-asset) and Group B (sector ETFs) require new data fetches in `services/market_data.py`. These may need rate-limit consideration and caching strategy.
- `put_call_ratio_oi()` is a distinct signal from `put_call_ratio_volume()` (OI-based vs volume-based). Both should exist in the pipeline.
- `scoring/clustering.py` deletion is preferred over move-to-analysis — if clustering is needed later, it can be re-implemented with pipeline-aware design.
- Items covered by `complexity-reduction` PRD (EGARCH, HV Parkinson/Rogers-Satchell, `classify_market_regime`, OpenBB removal) are explicitly excluded from this PRD's scope.
- Wave 4b indicators that fail to compute due to missing data (e.g., no VIX data available) must gracefully return `None` — never raise.

## Execution Order & Dependencies

```
Wave 1 (legacy removal)  ─┐
Wave 2 (dead functions)   ─┼─ Independent, can run in parallel
Wave 3 (re-export cleanup) ─┘
         │
         v
Wave 4a (wire hurst)        ─ Quick, no new data deps
Wave 4b (wire 15 indicators) ─ Largest effort, needs data plumbing
Wave 4c (DebatePhase enum)   ─ Independent of 4b
```

Waves 1-3 have no interdependencies and can execute in parallel or any order.
Wave 4 depends on Waves 1-3 being complete (clean baseline).
Wave 4a, 4b, and 4c are independent of each other within Wave 4.

## Out of Scope

- OpenBB enrichment removal (covered by `complexity-reduction` PRD)
- EGARCH, HV Parkinson, HV Rogers-Satchell removal (covered by `complexity-reduction` PRD)
- `classify_market_regime()` removal (covered by `complexity-reduction` PRD)
- Adding composite weights for newly-wired indicators (separate evaluation after data collection)
- `IntelligenceService` sub-method privatization (low priority, would break test imports)
- API endpoint removal for frontend-uncalled routes (keep for API completeness)
- Migration file consolidation (would break version sequence for existing DBs)
- Renaming `OpenBBConfig` to `CBOEConfig`
