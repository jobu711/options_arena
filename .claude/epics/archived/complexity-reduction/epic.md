---
name: complexity-reduction
status: completed
created: 2026-03-16T16:59:52Z
updated: 2026-03-16T22:00:00Z
completed: 2026-03-16T22:00:00Z
progress: 100%
prd: .claude/prds/complexity-reduction.md
github: https://github.com/jobu711/options_arena/issues/545
---

# Epic: complexity-reduction

## Overview

Pure code subtraction epic — remove ~3,400 lines of dead/redundant source code and ~2,800 lines of associated tests across three areas: a dead regime classifier, redundant volatility estimators (Parkinson, Rogers-Satchell, EGARCH), and the entire OpenBB enrichment service (disabled for all users due to FastAPI version conflict). No new features, no schema migrations, no API additions.

## Architecture Decisions

- **GARCH is the sole parametric vol forecaster** — EGARCH removed (marginal gain over GARCH at horizon=1). Yang-Zhang is the sole OHLC HV estimator (mathematically subsumes Parkinson and Rogers-Satchell).
- **FinancialDatasets is the sole fundamental data source** — OpenBB enrichment removed entirely. FD fields map directly to MarketContext without OpenBB fallback logic.
- **ML classifiers are authoritative for regime detection** — `classify_market_regime()` removed; `regime_ml.py` (Markov-switching + GBM) retained.
- **OpenBBConfig kept but slimmed** — Retains 5 CBOE chain fields only. Not renamed (out of scope per PRD).
- **CBOE chain provider preserved** — `cboe_provider.py` is architecturally independent from `openbb_service.py`.

## Technical Approach

This is pure deletion work organized in 3 waves of increasing integration risk, with test verification between each wave.

### Wave 1: Dead Indicator Functions + Pipeline References
Remove 4 dead functions from `indicators/`, their exports, and all downstream references in models, scoring, and scan pipeline.

**Files modified:**
- `indicators/regime.py` — delete `classify_market_regime()`
- `indicators/hv_estimators.py` — delete `compute_hv_parkinson()`, `compute_hv_rogers_satchell()`
- `indicators/vol_forecast.py` — delete `compute_egarch_forecast()`, `_EGARCH_SIMULATIONS`
- `indicators/__init__.py` — remove 4 dead exports
- `models/scan.py` — remove `vol_forecast_egarch` field from `IndicatorSignals`
- `scoring/dimensional.py` — remove `vol_forecast_egarch` from `FAMILY_INDICATOR_MAP["iv_vol"]`
- `scan/phase_scoring.py` — remove EGARCH computation block

### Wave 2: OpenBB Service + Model Deletion
Delete entire files and slim remaining models/config.

**Files deleted:**
- `services/openbb_service.py`
- `models/openbb.py`

**Files modified:**
- `models/config.py` — slim `OpenBBConfig` to 5 CBOE-only fields
- `models/analysis.py` — remove 12 OpenBB-sourced fields from `MarketContext`, adjust `enrichment_ratio()`
- `models/__init__.py` — remove 5 OpenBB model re-exports
- `models/enums.py` — delete `SentimentLabel` StrEnum
- `services/__init__.py` — remove `OpenBBService` re-export
- `services/health.py` — remove `check_openbb()` method

### Wave 3: Integration Point Cleanup
Remove OpenBB from orchestrator, API, CLI, and agent parsing.

**Files modified:**
- `agents/orchestrator.py` — remove `fundamentals`/`flow`/`sentiment` params from `build_market_context()` + `run_debate()`, remove OpenBB field waterfalls
- `agents/_parsing.py` — remove 3 OpenBB rendering sections (fundamental profile, unusual flow, news sentiment)
- `api/app.py` — remove OpenBB service creation in `lifespan()`
- `api/deps.py` — remove `get_openbb()` dependency
- `api/routes/debate.py` — remove OpenBB imports, fetch blocks, parameter passing
- `api/schemas.py` — remove `SentimentLabel` import + `news_sentiment_label` field
- `cli/commands.py` — remove OpenBB import, service instantiation, `--no-openbb` flag

### Dependency Cleanup
- Remove `vaderSentiment` from optional dependencies (no code path uses it after OpenBB news removal)

## Implementation Strategy

- **3 waves with test gates**: Run `pytest -m "not exhaustive" -n auto -q` + `mypy --strict` after each wave before proceeding
- **Test cleanup parallel with each wave**: Delete/update tests for removed code in the same task as the source removal
- **Risk mitigation**: Each wave is independently committable and revertable. Wave 1 (indicators) is lowest risk. Wave 3 (integration points) is highest risk due to breadth.

## Task Breakdown Preview

- [x] Task 1: Remove dead indicator functions + scoring/scan pipeline references + associated tests
- [x] Task 2: Delete OpenBB models + service, slim config, remove MarketContext fields, clean exports + health check + enums + associated tests
- [x] Task 3: Clean integration points — orchestrator, API, CLI, agent parsing + associated tests
- [x] Task 4: Remove `vaderSentiment` dependency + final verification (ruff, mypy, full test suite)

## Dependencies

- No external dependencies. Pure code subtraction.
- FinancialDatasets service remains untouched.
- CBOE chain provider (`cboe_provider.py`) remains untouched.

## Success Criteria (Technical)

1. All tests pass after removal (`pytest -m "not exhaustive" -n auto -q`)
2. `mypy --strict` clean
3. No function exported from `indicators/__init__.py` has zero pipeline call sites
4. `openbb_service.py` and `models/openbb.py` do not exist
5. `MarketContext` has no OpenBB-sourced fields
6. `OpenBBConfig` contains only CBOE chain fields (5 fields)
7. `ruff check` passes

## Estimated Effort

- **4 tasks**, each independently committable
- **Overall**: Medium complexity — breadth of files touched (~18 source + ~10 test) but each change is straightforward deletion
- **Estimated reduction**: ~3,400 source lines + ~2,800 test lines = ~6,200 total lines removed
- **Critical path**: Wave 3 (integration points) is the riskiest due to touching orchestrator, API, and CLI simultaneously

## Tasks Created

- [x] #546 - Remove dead indicator functions and pipeline references (parallel: false)
- [x] #547 - Delete OpenBB models, service, slim config, and clean MarketContext (parallel: false, depends: #546)
- [x] #548 - Clean integration points — orchestrator, API, CLI, agent parsing (parallel: false, depends: #547)
- [x] #549 - Remove vaderSentiment dependency and final verification (parallel: false, depends: #548)

Total tasks: 4
Parallel tasks: 0
Sequential tasks: 4 (strict dependency chain: #546 → #547 → #548 → #549)
Estimated total effort: 9-12 hours

## Test Coverage Plan

Total test files to DELETE: ~9 (dedicated OpenBB + dead indicator tests)
Total test files to UPDATE: ~10 (MarketContext, OpenBBConfig, orchestrator, routes, CLI references)
Verification: full test suite run after each wave + final comprehensive gate
