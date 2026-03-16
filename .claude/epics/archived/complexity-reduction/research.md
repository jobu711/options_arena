# Research: complexity-reduction

## PRD Summary

Remove ~3,400 lines of dead/redundant source code and ~2,800 lines of associated tests across three areas:
1. **Dead regime function**: `classify_market_regime()` superseded by ML classifiers
2. **Redundant volatility estimators**: Parkinson, Rogers-Satchell HV (subsumed by Yang-Zhang), EGARCH forecast (marginal gain over GARCH)
3. **OpenBB enrichment service**: Disabled for all users due to FastAPI version conflict (`fastapi<0.129` vs `>=0.133.1`); FinancialDatasets provides a superset

## Relevant Existing Modules

- `indicators/` — Pure math module (pandas in/out). Contains dead functions: `classify_market_regime()`, `compute_hv_parkinson()`, `compute_hv_rogers_satchell()`, `compute_egarch_forecast()`. Has own CLAUDE.md requiring docstrings + `InsufficientDataError` on bad input.
- `models/` — Pydantic v2 data shapes only. Contains `openbb.py` (5 models, 32 fields), `config.py` (OpenBBConfig class), `analysis.py` (MarketContext with 12 OpenBB-sourced fields), `scan.py` (IndicatorSignals with `vol_forecast_egarch`).
- `services/` — Sole external API layer. Contains `openbb_service.py` (~360 lines). ServiceBase pattern with config-gated features.
- `scoring/` — References `vol_forecast_egarch` in `dimensional.py` FAMILY_INDICATOR_MAP.
- `scan/` — Phase 2 calls EGARCH in `phase_scoring.py`. 4-phase async pipeline.
- `agents/` — `orchestrator.py` has `build_market_context()` with `fundamentals`/`flow`/`sentiment` params from OpenBB.
- `api/` — `app.py` creates OpenBBService in lifespan. `deps.py` has `get_openbb()`. `routes/debate.py` fetches OpenBB data.
- `cli/` — `commands.py` instantiates OpenBBService, has `--no-openbb` flag.
- `services/health.py` — Has `check_openbb()` method in health orchestration.

## Existing Patterns to Reuse

- **Re-export pattern**: Every `__init__.py` re-exports public API + `__all__`. Must update all affected `__init__.py` files when removing exports.
- **Config-gated features**: OpenBB uses `if settings.openbb.enabled:` guards. Entire config class can be deleted since CBOE chain config will remain.
- **Service lifecycle**: Services created in CLI/API lifespan, closed in `finally` blocks. Remove all OpenBBService instantiation + cleanup.
- **Never-raises pattern**: Services return fallback/None on error. Agent prompts already guard `if field is not None` — no prompt changes needed after field removal.
- **NaN defense**: MarketContext validators check `isfinite()` on all numeric fields. Removed fields simply disappear from the validator list.

## Existing Code to Extend

No new code is being written — this is pure subtraction. However:

- `indicators/hv_estimators.py` — Keep `compute_hv_yang_zhang()`, delete only Parkinson + Rogers-Satchell. File is NOT deleted entirely.
- `indicators/vol_forecast.py` — Keep `compute_garch_forecast()` + `test_stationarity()`, delete only `compute_egarch_forecast()`.
- `indicators/regime.py` — Delete `classify_market_regime()`, keep `compute_rs_vs_spx()` + `compute_correlation_regime_shift()`.
- `models/config.py` — PRD says slim OpenBBConfig to CBOE-only fields (5 fields: `cboe_chains_enabled`, `chains_cache_ttl`, `chain_validation_mode`, `request_timeout`, `max_retries`).

## Files to DELETE Entirely

| File | Lines | Reason |
|------|-------|--------|
| `src/options_arena/models/openbb.py` | ~199 | 5 models never usable (FastAPI conflict) |
| `src/options_arena/services/openbb_service.py` | ~360 | Entire service disabled |
| Test files for OpenBB (~7 files) | ~2,200 | Tests for deleted code |
| Test files for dead indicators | ~200 | Tests for Parkinson/Rogers-Satchell/EGARCH |

## Files to MODIFY

### Source Files (16 modifications)

| File | Change |
|------|--------|
| `indicators/regime.py` | Delete `classify_market_regime()` function |
| `indicators/hv_estimators.py` | Delete `compute_hv_parkinson()` + `compute_hv_rogers_satchell()`. Keep `compute_hv_yang_zhang()` |
| `indicators/vol_forecast.py` | Delete `compute_egarch_forecast()` + `_EGARCH_SIMULATIONS`. Keep GARCH + stationarity |
| `indicators/__init__.py` | Remove 3 dead exports from imports + `__all__` |
| `models/openbb.py` | DELETE ENTIRE FILE |
| `models/__init__.py` | Remove 5 OpenBB model re-exports from imports + `__all__` |
| `models/config.py` | Slim OpenBBConfig to 5 CBOE-only fields. Remove enrichment toggles + TTLs |
| `models/analysis.py` | Remove 12 OpenBB-sourced fields from MarketContext. Update `enrichment_ratio()` |
| `models/scan.py` | Remove `vol_forecast_egarch` from IndicatorSignals |
| `scoring/dimensional.py` | Remove `vol_forecast_egarch` from `FAMILY_INDICATOR_MAP["iv_vol"]` |
| `scan/phase_scoring.py` | Remove EGARCH computation block in `_compute_garch_for_ticker()` |
| `agents/orchestrator.py` | Remove `fundamentals`/`flow`/`sentiment` params from `build_market_context()` + `run_debate()`. Remove OpenBB field waterfalls |
| `services/__init__.py` | Remove `OpenBBService` re-export |
| `services/health.py` | Remove `check_openbb()` method + call in `check_all()` |
| `api/app.py` | Remove OpenBB service creation in `lifespan()`, `app.state.openbb` |
| `api/deps.py` | Remove `get_openbb()` dependency provider |
| `api/routes/debate.py` | Remove OpenBB imports, fetch blocks, parameter passing |
| `cli/commands.py` | Remove OpenBB import, service instantiation, `--no-openbb` flag, cleanup |

### MarketContext Fields to Remove (12 fields)

| Field | Type | Source |
|-------|------|--------|
| `pe_ratio` | `float \| None` | FundamentalSnapshot |
| `forward_pe` | `float \| None` | FundamentalSnapshot |
| `peg_ratio` | `float \| None` | FundamentalSnapshot |
| `price_to_book` | `float \| None` | FundamentalSnapshot |
| `debt_to_equity` | `float \| None` | FundamentalSnapshot |
| `revenue_growth` | `float \| None` | FundamentalSnapshot |
| `profit_margin` | `float \| None` | FundamentalSnapshot |
| `net_call_premium` | `float \| None` | UnusualFlowSnapshot |
| `net_put_premium` | `float \| None` | UnusualFlowSnapshot |
| `options_put_call_ratio` | `float \| None` | UnusualFlowSnapshot |
| `news_sentiment` | `float \| None` | NewsSentimentSnapshot |
| `recent_headlines` | `list[str] \| None` | NewsSentimentSnapshot |

Note: `news_sentiment_label` also to be removed if present.

## Potential Conflicts

1. **EGARCH is not fully dead**: Called in Phase 2 when `MLConfig.enable_garch=True`. PRD explicitly says to remove it — GARCH is the sole parametric vol forecaster. This is an intentional functional change, not dead code removal.
2. **CLI breaking change**: `--no-openbb` flag removed from debate command. Users with scripts referencing it will get Typer errors.
3. **Env var breaking change**: `ARENA_OPENBB__ENABLED=false` and other OpenBB env overrides will be ignored (no error, just unused).
4. **MarketContext field removal**: Agent prompts already guard with `if field is not None`, so prompts degrade gracefully. Output may differ slightly (no PE ratio analysis from OpenBB source).
5. **`classify_market_regime()` vs ML classifiers**: Must verify `classify_market_regime` in `regime.py` is NOT the same as `classify_regime_ml` in `regime_ml.py` (they are different — ML version is kept).

## Open Questions

1. **OpenBBConfig rename**: PRD says out of scope ("Renaming `OpenBBConfig` to `CBOEConfig` — follow-up if desired"). Keep the name as-is.
2. **MarketContext `enrichment_ratio()` removal**: PRD says "Adjust enrichment_ratio() to exclude removed fields." Should the method be kept (counting fewer fields) or deleted entirely? The PRD says adjust, not delete — keep it with remaining FD fields.
3. **`vaderSentiment` dependency**: No code path uses it after OpenBB news removal. Should it be removed from `pyproject.toml`? The PRD mentions it becomes unnecessary. Include in scope.

## Recommended Architecture

**Phased approach** (3 waves, test between each):

**Wave 1 — Dead Indicator Functions (lowest risk)**
- Delete `classify_market_regime()` from `regime.py`
- Delete `compute_hv_parkinson()` + `compute_hv_rogers_satchell()` from `hv_estimators.py`
- Delete `compute_egarch_forecast()` from `vol_forecast.py`
- Remove `vol_forecast_egarch` from IndicatorSignals + dimensional scoring
- Remove EGARCH block from `phase_scoring.py`
- Update `indicators/__init__.py` exports
- Delete/update associated tests

**Wave 2 — OpenBB Model + Service Deletion (moderate risk)**
- Delete `models/openbb.py` entirely
- Delete `services/openbb_service.py` entirely
- Slim `OpenBBConfig` to CBOE-only fields
- Remove 12 MarketContext fields + update `enrichment_ratio()`
- Update `models/__init__.py` + `services/__init__.py` exports
- Remove `check_openbb()` from health service
- Delete OpenBB test files

**Wave 3 — Integration Point Cleanup (highest risk, most files)**
- Remove OpenBB params from `build_market_context()` + `run_debate()` in orchestrator
- Remove OpenBB fetch blocks from `api/routes/debate.py`
- Remove `get_openbb()` from `api/deps.py`
- Remove OpenBB from `api/app.py` lifespan
- Remove OpenBB from `cli/commands.py` (import, instantiation, `--no-openbb` flag)
- Remove `vaderSentiment` from dependencies

## Test Strategy Preview

- **Existing test patterns**: pytest + pytest-asyncio, parametrized tests, `TestModel` for PydanticAI agents, factory fixtures for models
- **Test file locations**: `tests/unit/` mirrors `src/options_arena/` structure
- **Tests to delete**: ~7 OpenBB test files + Parkinson/Rogers-Satchell/EGARCH test cases
- **Tests to update**: MarketContext construction tests, OpenBBConfig tests, orchestrator tests with `fundamentals=` param, debate route tests with OpenBB mocks
- **Verification**: `uv run pytest -m "not exhaustive" -n auto -q` after each wave

## Estimated Complexity

**M (Medium)** — Pure code subtraction across ~18 source files + ~10 test files. No new features, no schema migrations, no API additions. Risk is moderate due to breadth (many files touched) but each individual change is straightforward deletion. Three waves with test verification between each keeps risk manageable.

Estimated reduction: ~3,400 source lines + ~2,800 test lines = **~6,200 total lines removed**.
