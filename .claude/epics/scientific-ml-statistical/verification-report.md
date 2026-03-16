---
epic: scientific-ml-statistical
verified: 2026-03-15T22:00:00Z
result: PASS
pass: 28
warn: 0
fail: 0
skip: 0
total: 28
tests_total: 260
test_functions: 189
---

# Verification Report: scientific-ml-statistical

## Summary

**Result: 28/28 PASS** — All acceptance criteria verified with code evidence and passing tests.

| Metric | Value |
|--------|-------|
| Acceptance criteria | 28/28 PASS |
| Test functions | 189 (across 9 test files) |
| Test cases (parametrized) | 260/260 passed |
| New source files | 4 created |
| Modified source files | 13 |
| Total LOC added | ~3,600 |
| Regressions | 0 (128/128 critical tests pass) |

## Traceability Matrix

### A1: FRED Service Expansion + MacroContext Model (#533)

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| 1 | FredSeriesConfig with id, TTL, transform | `models/macro.py:23-40` — NamedTuple with series_id, ttl_hours, transform | test_macro.py | PASS |
| 2 | MacroContext with 8 float\|None fields | `models/macro.py:57-106` — 8 fields, frozen, isfinite validators | 36 tests in test_macro.py | PASS |
| 3 | fetch_macro_context() batch method | `services/fred.py:170-186` — asyncio.gather with return_exceptions | 21 tests in test_fred_macro.py | PASS |
| 4 | Graceful degradation (partial data) | `services/fred.py:361-403` — per-series error isolation | test_partial_data_returns_partial_context | PASS |
| 5 | Never raises — existing FRED pattern | `services/fred.py:170-186` — outer try/except → fallback() | test_unexpected_exception_returns_fallback | PASS |

### A2: Macro Regime Derivation + Agent Enrichment (#535)

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| 6 | compute_macro_regime() classifies 3 regimes | `indicators/macro.py:33-103` — expansionary/contractionary/transitional | 23 tests in test_macro.py | PASS |
| 7 | render_macro_context() formatted string | `agents/_parsing.py:784` — uses _render_optional pattern | 18 tests in test_macro_rendering.py | PASS |
| 8 | Fundamental Agent includes macro block | `agents/fundamental_agent.py:45-48` — MACRO_CONTEXT delimiters | test_macro_rendering.py | PASS |
| 9 | Risk Agent includes macro | `agents/risk.py:43-46` — same delimiter pattern | test_macro_rendering.py | PASS |
| 10 | Returns None when incomplete | `indicators/macro.py:47-53` — completeness_ratio < 0.5 gate | test_insufficient_data | PASS |

### A3: GARCH/EGARCH Volatility Forecasting (#534)

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| 11 | GARCH(1,1) h-step-ahead forecast | `indicators/vol_forecast.py:96-168` — arch_model + annualization | 38 tests in test_vol_forecast.py | PASS |
| 12 | EGARCH(1,1,1) with leverage | `indicators/vol_forecast.py:171-253` — vol='EGARCH', p=1, o=1, q=1 | test_egarch_* tests | PASS |
| 13 | ADF stationarity gate | `indicators/vol_forecast.py:59-93` — adfuller pre-check | test_stationarity_* tests | PASS |
| 14 | Returns None on <252 obs | `vol_forecast.py:126-127` — _MIN_OBSERVATIONS=252 | test_insufficient_data | PASS |
| 15 | Guarded arch import | `vol_forecast.py:37-45` — _get_arch() returns module or None | test_arch_not_installed | PASS |
| 16 | iv_vs_forecast_spread field | `models/scan.py` — IndicatorSignals field | test_new_fields_default_none | PASS |

### A4: Markov-Switching Regime Detection (#536)

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| 17 | compute_markov_regime() with k_regimes | `indicators/regime_ml.py:77-183` — MarkovRegression(k_regimes) | 29 tests in test_regime_ml.py | PASS |
| 18 | Smoothed probabilities | `regime_ml.py:114-116` — smoothed_marginal_probabilities | test_smoothed_probs_sum_to_one | PASS |
| 19 | Transition matrix | `regime_ml.py:118-123` — regime_transition_matrix[:,:,0].T | test_transition_matrix_row_stochastic | PASS |
| 20 | regime_markov_label, regime_transition_prob | `models/scan.py` — 2 new float\|None fields | test_new_fields_default_none | PASS |
| 21 | Guarded statsmodels import | `regime_ml.py:66-74` — _get_markov_regression() | test_statsmodels_not_installed | PASS |

### A5: Statistical Pipeline Integration (#537)

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| 22 | Phase 2 calls GARCH+Markov when enabled | `scan/phase_scoring.py:95-101` — _compute_ml_indicators() | 10 tests in test_phase_scoring_ml.py | PASS |
| 23 | Phase 3 calls macro when enabled | `scan/phase_options.py` — fetch_macro_context() gated | test_ml_pipeline_disabled.py | PASS |
| 24 | Volatility Agent gets iv_vs_forecast_spread | `agents/_parsing.py` — GARCH forecast + spread rendered | 10 tests in test_volatility_ml_context.py | PASS |
| 25 | Weight redistribution (sum=1.0) | `scoring/composite.py:71-72` — import-time assertion | test_weights_sum_to_one | PASS |
| 26 | MLConfig feature flags (default off) | `models/config.py:31-61` — 3 booleans, all False | test_ml_pipeline_disabled.py | PASS |

### Architecture

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| 27 | Optional deps in pyproject.toml | `pyproject.toml` — ml = ["arch>=7.0,<9", "statsmodels>=0.14"] | N/A | PASS |
| 28 | No Pydantic models in indicators/ | vol_forecast.py, regime_ml.py — zero BaseModel imports | N/A | PASS |

## Test Files

| File | Functions | Passed |
|------|-----------|--------|
| tests/unit/models/test_macro.py | 36 | 36 |
| tests/unit/services/test_fred_macro.py | 21 | 21 |
| tests/unit/indicators/test_vol_forecast.py | 38 | 38 |
| tests/unit/indicators/test_macro.py | 23 | 23 |
| tests/unit/agents/test_macro_rendering.py | 18 | 18 |
| tests/unit/indicators/test_regime_ml.py | 29 | 29 |
| tests/unit/scan/test_phase_scoring_ml.py | 10 | 10 |
| tests/unit/agents/test_volatility_ml_context.py | 10 | 10 |
| tests/integration/test_ml_pipeline_disabled.py | 4 | 4 |
| **Total** | **189** | **260 (parametrized)** |

## Regression Check

- Critical tier: 128/128 passed
- Composite scoring: 19/19 passed
- Scan model: 31/31 passed
- Existing FRED: 19/19 passed

## Notes

- One flaky test (`test_high_vol_regime_detected_at_end`) due to Markov-switching model stochasticity — passes consistently on re-run. Consider adding `pytest.mark.flaky` or fixed seed.
- Runtime warnings from arch/statsmodels on convergence failure tests are expected and suppressed by the implementation (returns None).
