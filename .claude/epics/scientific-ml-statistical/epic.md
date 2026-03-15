---
name: scientific-ml-statistical
status: backlog
created: 2026-03-15T14:00:00Z
progress: 0%
prd: .claude/prds/scientific-ml-integration.md
parent: .claude/epics/scientific-ml-integration
github: [Will be updated when synced to GitHub]
---

# Epic A: Statistical Computation Foundation (arch + statsmodels + FRED)

## Overview

Integrate `arch` (GARCH/EGARCH volatility forecasting), `statsmodels` (Markov-switching regime detection, ADF stationarity testing), and expanded FRED economic data into Options Arena. This epic establishes the statistical computation foundation that Epics B and C build upon.

**Shared research**: `.claude/epics/scientific-ml-integration/research.md`

## Architecture Decisions

1. **Optional dependency group** — `arch >=7.0,<9`, `statsmodels >=0.14` in `[project.optional-dependencies] ml = [...]`. Guarded imports via `_get_arch()` / `_get_sm()` pattern (see `openbb_service.py`).
2. **Config-gated features** — `MLConfig(BaseModel)` submodel on `ScanConfig` with `enable_garch: bool = False`, `enable_markov: bool = False`, `enable_macro: bool = False`. All disabled by default.
3. **Indicator module purity** — `indicators/vol_forecast.py`, `indicators/regime_ml.py`, `indicators/macro.py` use guarded imports internally but expose `float | None` / `NamedTuple` return types. No Pydantic models in indicators.
4. **Macro context via existing service pattern** — FRED expansion stays in `services/fred.py`, follows existing never-raises + two-tier cache pattern.
5. **Regime taxonomy reuse** — Markov-switching maps to existing `MarketRegime` enum. No parallel taxonomy.

## New Files (4)

| File | Module | Purpose |
|------|--------|---------|
| `models/macro.py` | models | `MacroContext`, `MacroRegimeResult`, `FredSeriesConfig` models |
| `indicators/vol_forecast.py` | indicators | GARCH/EGARCH forecasting via `arch` + ADF stationarity via `statsmodels` |
| `indicators/regime_ml.py` | indicators | Markov-switching regime detection via `statsmodels` |
| `indicators/macro.py` | indicators | Rule-based macro regime derivation from FRED data |

## Modified Files (11)

| File | Change |
|------|--------|
| `services/fred.py` | Batch multi-series fetch, per-series TTL, `fetch_macro_context()` |
| `models/analysis.py` | ML fields on `MarketContext` (vol forecast, regime probs, macro context) |
| `models/scan.py` | ~6 ML indicator fields on `IndicatorSignals` (currently 68 fields) |
| `models/config.py` | `MLConfig(BaseModel)` submodel + feature flags on `ScanConfig` |
| `agents/_parsing.py` | `render_macro_context()`, vol forecast in `render_volatility_context()` |
| `agents/fundamental_agent.py` | Consume `MacroContext` in prompt |
| `agents/risk.py` | Consume macro regime + regime transition probs |
| `agents/volatility.py` | Consume vol forecast vs IV comparison |
| `indicators/regime.py` | Integrate Markov-switching as alternative to heuristics |
| `scan/phase_scoring.py` | Wire GARCH + Markov + macro into Phase 2/3 |

## New Dependencies

- `arch >=7.0,<9` — MIT, standalone GARCH library (~5MB)
- `statsmodels >=0.14` — BSD, Markov-switching + ADF (~50MB)

## Issues

### A1: FRED Service Expansion + MacroContext Model
**FR**: FR-S11
**Description**: Extend `FredService` to fetch 8 FRED series (DGS10, DGS2, T10Y2Y, FEDFUNDS, VIXCLS, CPIAUCSL, INDPRO, UNRATE) with per-series TTL caching. Create `MacroContext` model in `models/macro.py` and `FredSeriesConfig` for series configuration. Add `fetch_macro_context()` batch method.
> **Context7 fix**: NAPM (ISM Manufacturing PMI) was removed from FRED in June 2016. Replaced with INDPRO (Industrial Production Index) as the manufacturing activity proxy.
**New files**: `models/macro.py`
**Modified files**: `services/fred.py`, `models/config.py`
**Est. tests**: ~25
**Acceptance criteria**:
- [ ] `FredSeriesConfig` with id, TTL, transform type
- [ ] `MacroContext` model with all 8 series fields (all `float | None`): DGS10, DGS2, T10Y2Y, FEDFUNDS, VIXCLS, CPIAUCSL, INDPRO, UNRATE
- [ ] `fetch_macro_context()` batch-fetches with per-series TTL
- [ ] Graceful degradation: partial data returns partial `MacroContext`
- [ ] Never raises — follows existing FRED pattern

### A2: Macro Regime Derivation + Agent Enrichment
**FR**: FR-S12
**Description**: Implement rule-based macro regime classification in `indicators/macro.py`. Enrich Fundamental Agent and Risk Agent prompts with macro context block. Add `render_macro_context()` to `agents/_parsing.py`.
**New files**: `indicators/macro.py`
**Modified files**: `agents/fundamental_agent.py`, `agents/risk.py`, `agents/_parsing.py`, `models/analysis.py`
**Depends on**: A1
**Est. tests**: ~15
**Acceptance criteria**:
- [ ] `compute_macro_regime()` classifies expansionary/contractionary/transitional
- [ ] `render_macro_context()` returns formatted string for agent prompts
- [ ] Fundamental Agent and Risk Agent prompts include macro block when available
- [ ] Returns None when MacroContext is incomplete

### A3: GARCH/EGARCH Volatility Forecasting + ADF Stationarity
**FR**: FR-S1, FR-S3
**Description**: Implement `compute_garch_forecast()` and `compute_egarch_forecast()` in `indicators/vol_forecast.py` using `arch` library. Include `test_stationarity()` ADF gate via `statsmodels`. Populate `vol_forecast_garch`, `vol_forecast_egarch` on `IndicatorSignals`.
**New files**: `indicators/vol_forecast.py`
**Modified files**: `models/analysis.py`
**Est. tests**: ~30
**Acceptance criteria**:
- [ ] GARCH(1,1) and EGARCH(1,1) h-step-ahead vol forecast
- [ ] ADF stationarity test gates GARCH fitting
- [ ] Returns None on insufficient data (<252 obs) or convergence failure
- [ ] Guarded `arch` import — returns None when not installed
- [ ] `iv_vs_forecast_spread` derived indicator computed

**Context7 implementation notes**:
- Use `arch_model(returns, vol='GARCH', p=1, q=1)` and `arch_model(returns, vol='EGARCH', p=1, o=1, q=1)` — EGARCH takes `(p, o, q)` not `(p, q)`
- Forecast via `res.forecast(horizon=N).variance` (DataFrame with `h.1`..`h.N` columns); `res.conditional_volatility` is in-sample only
- Convergence is **flag-based**, not exception-based: check `res.convergence_flag != 0` after `fit(disp='off')`
- No `variance_backcast` parameter exists — use `backcast` on `fit()` or rely on default
- The 252-observation minimum is a project policy for estimate reliability, not a library constraint

### A4: Markov-Switching Regime Detection
**FR**: FR-S2
**Description**: Implement `compute_markov_regime()` in `indicators/regime_ml.py` using `statsmodels.tsa.regime_switching.markov_regression.MarkovRegression`. Returns regime labels, smoothed probabilities, and transition matrix. Complements (not replaces) existing heuristic regime detection.
**New files**: `indicators/regime_ml.py`
**Modified files**: `indicators/regime.py`
**Depends on**: A3 (shares stationarity infrastructure)
**Est. tests**: ~20
**Acceptance criteria**:
- [ ] 3-regime Markov-switching model on daily returns
- [ ] Smoothed regime probabilities + transition matrix
- [ ] `regime_markov_label`, `regime_transition_prob` populated
- [ ] Falls back to None on convergence failure
- [ ] Guarded `statsmodels` import

**Context7 implementation notes**:
- Statsmodels uses `k_regimes` (not `n_regimes`): `MarkovRegression(returns, k_regimes=3)`
- Smoothed probabilities via `results.smoothed_marginal_probabilities`
- Transition matrix is on the **model**, not results: `model.regime_transition_matrix(results.params)[:, :, 0]` — must keep references to both objects; squeeze trailing dim from `(3,3,1)` to `(3,3)`
- Use `fit(search_reps=20)` for better convergence on difficult series
- Consider `MarkovAutoregression` as alternative if daily returns show serial correlation

### A5: Statistical Pipeline Integration
**FR**: Pipeline wiring
**Description**: Wire GARCH, Markov-switching, and macro context into scan Phase 2/3. Add config flags to `MLConfig`. Enrich Volatility Agent with vol forecast vs IV comparison. Weight redistribution for new indicators.
**Modified files**: `scan/phase_scoring.py`, `agents/volatility.py`, `models/config.py`
**Depends on**: A1, A2, A3, A4
**Est. tests**: ~15
**Acceptance criteria**:
- [ ] Phase 2 calls GARCH + Markov when config-enabled
- [ ] Phase 3 calls macro fetch when config-enabled
- [ ] Volatility Agent receives `iv_vs_forecast_spread` in context
- [ ] All features no-op when config flags are False
- [ ] Existing tests pass with default config (all disabled)

## Dependency Graph

```
A1 (FRED expansion)
 |
 v
A2 (macro regime + agents)
                            \
A3 (GARCH + ADF)             \
 |                             → A5 (pipeline wiring)
 v                            /
A4 (Markov-switching)        /
```

A1 and A3 can run in parallel. A2 depends on A1. A4 depends on A3. A5 depends on all.

## Estimated Effort

- **Size**: L (~3-4 sessions)
- **Tests**: ~105 new tests
- **Risk**: Low — `arch` and `statsmodels` are well-established libraries with predictable APIs

## Success Criteria

| Metric | Target |
|--------|--------|
| GARCH forecast populated | >80% of tickers with 252+ days history |
| Markov regime populated | >70% of tickers |
| FRED macro series fetched | 8/8 series, <2s batch with caching |
| Existing test suite | 100% pass (zero regressions) |
| Default config behavior | Identical to current — all features off |
