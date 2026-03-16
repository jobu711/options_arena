---
name: complexity-reduction
description: Remove dead code, redundant vol estimators, and OpenBB enrichment service to reduce maintenance burden
status: planned
created: 2026-03-16T16:50:24Z
---

# PRD: complexity-reduction

## Executive Summary

Options Arena has accumulated ~3,400 lines of dead or redundant source code and ~2,800 lines of associated tests across three areas: a superseded regime classifier, redundant volatility estimators, and an OpenBB enrichment service that conflicts with the project's own FastAPI dependency. Removing these reduces maintenance burden, eliminates a dependency version conflict, and clarifies which systems are authoritative for each domain.

## Problem Statement

### What problem are we solving?

The codebase has grown to ~45K lines across 132 source files. Several features are dead code (never called from the pipeline), redundant (multiple implementations of the same concept), or effectively disabled (OpenBB can't be installed alongside current FastAPI). These inflate CI time, test surface, and cognitive load for contributors without providing proportional value.

### Why is this important now?

- OpenBB SDK pins `fastapi<0.129`; the project requires `fastapi>=0.133.1`. This conflict means OpenBB enrichment is disabled for all default installs. The 552 test references and ~1,800 lines of source are pure maintenance cost.
- FinancialDatasets (plain httpx, zero extra deps) provides a superset of OpenBB's fundamental data (30 unique fields vs 7 overlapping). Keeping both creates confusion about which is authoritative.
- Three vol estimators (`compute_egarch_forecast`, `compute_hv_parkinson`, `compute_hv_rogers_satchell`) are computed or exported but carry zero composite scoring weight and zero agent prompt exposure.
- `classify_market_regime()` was superseded by ML classifiers in `regime_ml.py` but never removed.

## User Stories

1. **As a contributor**, I want dead code removed so I don't waste time understanding functions that are never called.
   - AC: No exported function exists that has zero call sites in the pipeline or API.
2. **As a maintainer**, I want the OpenBB enrichment removed so CI doesn't carry 552 test references for a feature no one can activate without version conflicts.
   - AC: `openbb_service.py` and `models/openbb.py` deleted. CBOE chain provider preserved.
3. **As a user**, I want one authoritative source for fundamental data so debate agent prompts aren't confused by two overlapping data feeds.
   - AC: FinancialDatasets is the sole fundamental data source. OpenBB enrichment fields removed from `MarketContext`.

## Architecture & Design

### Chosen Approach

Approach A: Surgical Dead Code Removal — remove confirmed dead functions, the redundant EGARCH estimator, unused HV estimators, and the entire OpenBB enrichment service while preserving the CBOE chain provider.

### Module Changes

#### 1. Dead Regime Function

| File | Change |
|------|--------|
| `indicators/regime.py` | Delete `classify_market_regime()`. Keep `compute_rs_vs_spx()`, `compute_correlation_regime_shift()` |
| `indicators/__init__.py` | Remove `classify_market_regime` export |

#### 2. Dead/Redundant Volatility Estimators

| File | Change |
|------|--------|
| `indicators/hv_estimators.py` | Delete `compute_hv_parkinson()`, `compute_hv_rogers_satchell()`. Keep `compute_hv_yang_zhang()` only |
| `indicators/vol_forecast.py` | Delete `compute_egarch_forecast()` and `_EGARCH_SIMULATIONS` constant |
| `indicators/__init__.py` | Remove `compute_hv_parkinson`, `compute_hv_rogers_satchell`, `compute_egarch_forecast` exports |
| `models/scan.py` | Remove `vol_forecast_egarch: float | None = None` from `IndicatorSignals` |
| `scan/phase_scoring.py` | Remove EGARCH computation block in `_compute_garch_for_ticker()` |
| `scoring/dimensional.py` | Remove `"vol_forecast_egarch"` from `FAMILY_INDICATOR_MAP["iv_vol"]` |

#### 3. OpenBB Enrichment Service Removal

| File | Change |
|------|--------|
| `services/openbb_service.py` | **Delete entire file** |
| `models/openbb.py` | **Delete entire file** |
| `services/__init__.py` | Remove `OpenBBService` re-export |
| `models/__init__.py` | Remove `FundamentalSnapshot`, `UnusualFlowSnapshot`, `NewsSentimentSnapshot` re-exports |
| `models/config.py` (`OpenBBConfig`) | Remove enrichment fields: `enabled`, `fundamentals_enabled`, `unusual_flow_enabled`, `news_sentiment_enabled`, `fundamentals_cache_ttl`, `flow_cache_ttl`, `news_cache_ttl`. Keep CBOE fields: `cboe_chains_enabled`, `chains_cache_ttl`, `chain_validation_mode`, `request_timeout`, `max_retries` |
| `models/analysis.py` (`MarketContext`) | Remove OpenBB-sourced fields: `net_call_premium`, `net_put_premium`, `options_put_call_ratio` (from OpenBB flow), `news_sentiment`, `news_sentiment_label`, `recent_headlines`. Adjust `enrichment_ratio()` to exclude removed fields |
| `agents/orchestrator.py` | Remove `fundamentals: FundamentalSnapshot | None` param from `build_market_context()`. Remove OpenBB field mappings (lines 390-510 OpenBB sections). Simplify FD-first priority to direct FD mapping |
| `agents/_parsing.py` | Remove 3 OpenBB rendering sections: "Fundamental Profile" (lines 908-924), "Unusual Options Flow" (lines 979-989), "News Sentiment" (lines 991-999). FD-sourced fundamental rendering (lines 681-726) remains |
| `api/app.py` | Remove `OpenBBService` creation in `lifespan()`. Remove `app.state.openbb` |
| `api/deps.py` | Remove `get_openbb()` dependency |
| `api/routes/debate.py` | Remove `openbb_svc` usage and `fundamentals=` kwarg from `run_debate()` calls |
| `api/schemas.py` | Remove `SentimentLabel` import (line 31) and `news_sentiment_label` field (line 535) |
| `cli/commands.py` | Remove OpenBB service creation and `fundamentals=` pass-through |
| `services/health.py` | Remove `check_openbb()` method and its call in `check_all()` |
| `models/enums.py` | Delete `SentimentLabel` StrEnum (lines 205-213) — used only by OpenBB |

### Data Models

**Removed models** (delete files):
- `FundamentalSnapshot` — 10 fields, all available from FinancialDatasets
- `UnusualFlowSnapshot` — `net_call_premium`/`net_put_premium` always `None`
- `NewsSentimentSnapshot` — VADER sentiment on yfinance news (IntelligenceService covers news)

**Modified models:**
- `IndicatorSignals` — remove `vol_forecast_egarch` field
- `MarketContext` — remove 6 OpenBB-sourced fields
- `OpenBBConfig` — slim to 5 CBOE-only fields (from 12)

**Unchanged models:**
- `FinancialMetricsData`, `IncomeStatementData`, `BalanceSheetData`, `FinancialDatasetsPackage` — sole fundamental data source
- All `IntelligenceService` models — unchanged

### Core Logic

**Regime**: `classify_market_regime()` deleted. The ML classifiers in `regime_ml.py` (Markov-switching + GBM) are the authoritative regime detection. `compute_rs_vs_spx()` and `compute_correlation_regime_shift()` remain as they are actively called from `scan/indicators.py`.

**Volatility**: GARCH is the sole parametric vol forecaster (composite weight 0.02, in agent prompts). EGARCH removed — at horizon=1 with 252-obs windows, EGARCH's leverage parameter adds estimation variance without meaningful gain. EWMA and HV-20d retained for their distinct functional roles (forward-looking forecast and backward-looking realized, respectively — both are dependencies of downstream signals). Yang-Zhang is the sole OHLC HV estimator — it mathematically subsumes both Parkinson and Rogers-Satchell.

**Fundamentals**: FinancialDatasets is the sole fundamental data source. The orchestrator's `build_market_context()` drops the `fundamentals` parameter. FD fields map directly to `MarketContext.fd_*` fields without OpenBB fallback logic.

## Requirements

### Functional Requirements

1. Core scan-debate pipeline produces identical results when OpenBB is not installed (which is the default state for all users)
2. CBOE chain provider (`cboe_provider.py`) continues to work when OpenBB SDK is installed
3. FinancialDatasets enrichment works identically to current behavior
4. No remaining exports with zero call sites in pipeline/API (except `scoring/clustering.py` which is intentionally kept for future wiring)
5. `health` command no longer reports OpenBB enrichment status

### Non-Functional Requirements

1. Estimated reduction: ~3,400 lines source, ~2,800 lines tests
2. No new dependencies added
3. All existing tests pass (after removing tests for deleted code)
4. `mypy --strict` passes
5. `ruff check` passes

## API / CLI Surface

**Removed from health check response:**
- OpenBB enrichment status fields

**No new commands, endpoints, or flags.**

## Testing Strategy

### Tests to delete
- 9 dedicated OpenBB test files (~130 KB total):
  - `tests/unit/agents/test_openbb_context.py`
  - `tests/unit/agents/test_openbb_prompts.py`
  - `tests/unit/api/test_app_lifespan_openbb.py`
  - `tests/unit/api/test_debate_openbb.py`
  - `tests/unit/cli/test_debate_openbb.py`
  - `tests/unit/models/test_openbb_models.py`
  - `tests/unit/services/test_openbb_health.py`
  - `tests/unit/services/test_openbb_service.py`
  - `tests/integration/test_openbb_integration.py`
- Parametrized cases for `compute_hv_parkinson`, `compute_hv_rogers_satchell`, `compute_egarch_forecast`
- Cases for `classify_market_regime`
- Cases referencing `vol_forecast_egarch` signal field

### Tests to update
- ~10 additional test files with OpenBB references (orchestrator, debate routes, chain migration, recon, provider orchestration, etc.) — remove OpenBB-specific fixtures, mocks, and assertions
- Tests constructing `OpenBBConfig` — update to reflect slimmed CBOE-only fields
- Tests constructing `MarketContext` with removed OpenBB fields
- Tests mocking `build_market_context()` with `fundamentals=` param

### Verification
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest -m "not exhaustive" -n auto -q
uv run mypy src/ --strict
```

## Success Criteria

1. All tests pass after removal
2. `mypy --strict` clean
3. No function exported from `indicators/__init__.py` has zero pipeline call sites
4. `openbb_service.py` and `models/openbb.py` do not exist
5. `MarketContext` has no OpenBB-sourced fields
6. `OpenBBConfig` contains only CBOE chain fields

## Constraints & Assumptions

- CBOE chain provider (`cboe_provider.py`) is architecturally independent from `openbb_service.py` and will not be affected by the enrichment service removal
- The `vaderSentiment` optional dependency becomes unnecessary after OpenBB news removal — no code path uses it
- K-means clustering (`scoring/clustering.py`) is intentionally preserved for future pipeline wiring — it is NOT in scope for removal
- The inline regime threshold logic in `scan/phase_options.py` (lines 966-974) is a separate issue (duplication of `map_regime_label_to_market_regime()`); not in scope for this PRD but flagged for future cleanup

## Out of Scope

- Renaming `OpenBBConfig` to `CBOEConfig` (follow-up if desired)
- Wiring K-means clustering into the pipeline (separate PRD)
- Fixing the `iv_vs_forecast_spread` semantic mislabeling (EWMA-vs-GARCH, not IV-vs-GARCH)
- Removing analytics/backtesting system
- Removing market heatmap
- Consolidating the `phase_options.py` inline regime mapping with `map_regime_label_to_market_regime()`

## Dependencies

- No external dependencies. Pure code subtraction.
- FinancialDatasets service must remain functional (no changes to it)
- CBOE chain provider must remain functional (no changes to it)
