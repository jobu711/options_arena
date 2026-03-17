# Research: scientific-ml-integration

## PRD Summary

Integrate `arch` (GARCH), statsmodels, scikit-learn, PyTorch Lightning, and expanded FRED economic data into Options Arena. Four new capability areas:

1. **Volatility forecasting** — GARCH/EGARCH via `arch >=7.0` (not statsmodels) replacing backward-looking EWMA
2. **Regime classification** — Markov-switching models (statsmodels) + ML classifiers (scikit-learn) replacing threshold heuristics
3. **Neural pricing** — IV surface fitting + trajectory forecasting (PyTorch Lightning) complementing BSM/BAW
4. **Macro context** — 8 FRED series (yield curve, Fed funds, VIX, CPI, industrial production, unemployment) for agent enrichment. Note: NAPM (ISM PMI) removed from FRED in June 2016; using INDPRO (Industrial Production) instead.

**Restructured**: 3 independent epics (A: Statistical Foundation, B: ML Classification, C: Neural Models) with 13 issues total across 8 new files, ~220 estimated tests. FR-S5 (indicator weight validation) relocated to `ai-agency-evolution` PRD Epic 5.

## Relevant Existing Modules

### `indicators/` (CLAUDE.md: pure pandas in / pandas out)
- **vol_forecast.py** (new): GARCH/EGARCH forecasting + ADF tests
- **regime_ml.py** (new): Markov-switching + ML regime classification
- **macro.py** (new): Macro regime derivation from FRED data
- **Constraint**: No Pydantic models, no API calls. Returns `pd.Series` or `float | None`. Must use `validate_aligned()`, `InsufficientDataError`, `math.isfinite()` guards. Vectorized numpy/pandas ops only.
- **Existing code**: `regime.py` (278 lines) — rule-based `classify_market_regime()` with 4-state `MarketRegime` enum. `iv_analytics.py` (430 lines) — `compute_ewma_vol_forecast()` (RiskMetrics EWMA, not GARCH), `classify_vol_regime()`. `flow_analytics.py` (215 lines) — 5 flow functions, no ML. `hv_estimators.py` (246 lines) — Parkinson, Rogers-Satchell, Yang-Zhang. `vol_surface.py` (623 lines) — scipy spline surface fitting.

### `pricing/` (CLAUDE.md: pure scalar math, no pandas)
- **neural_surface.py** (new): PyTorch Lightning IV surface model
- **trajectory.py** (new): LSTM price trajectory forecasting
- **Constraint**: Scalar float in/out at public API. PyTorch internals invisible at boundary. Cannot import services/, indicators/, scan/.
- **Existing code**: `bsm.py`, `american.py`, `dispatch.py` — BSM + BAW closed-form models.

### `scoring/` (CLAUDE.md: typed models, pricing/dispatch only)
- **clustering.py** (new): Contract Greeks clustering via K-means
- **Constraint**: Must return typed model (not dict). `INDICATOR_WEIGHTS` sum must equal 1.0 (import-time guard). Imports `pricing/dispatch` only.
- **Existing code**: `composite.py` (191 lines) — 24 indicators across 7 categories with sum-to-1.0 guard. `contracts.py` (493 lines) — `filter_contracts → select_expiration → compute_greeks → select_by_delta → recommend_contracts`. `dimensional.py` (358 lines) — per-family dimensional scores, `REGIME_WEIGHT_PROFILES`.

### `services/` (CLAUDE.md: only layer touching external APIs)
- **fred.py** (modify): Extend from single DGS10 series to 8 series with per-series TTL
- **Constraint**: Every public method async, returns typed Pydantic models. Never-raises pattern. `httpx.AsyncClient`, 24h TTL caching.
- **Existing code**: `fred.py` (239 lines) — single series `DGS10`, `CachedRate` NamedTuple, two-tier cache (in-memory + SQLite), `fetch_risk_free_rate() -> float`. Safe to add new methods without changing existing API.

### `models/` (CLAUDE.md: no business logic, no I/O)
- **macro.py** (new): `MacroContext`, `MacroRegimeResult`, `FredSeriesConfig` models
- **analysis.py** (modify): Add ML fields to `MarketContext` + validators
- **scan.py** (modify): Add ML fields to `IndicatorSignals` (currently 65 fields)
- **config.py** (modify): Add `MLConfig(BaseModel)` submodel + feature flags on `ScanConfig`
- **Constraint**: `frozen=True` for snapshots, `X | None` unions, `field_validator` with `math.isfinite()`. Config submodels are `BaseModel` (not `BaseSettings`).

### `agents/` (CLAUDE.md: no data fetching, pre-enriched data only)
- **_parsing.py** (modify): Add `render_macro_context()`, extend `render_volatility_context()` with vol forecast
- **Constraint**: ML outputs arrive via `MarketContext` fields. Context rendering uses `_render_optional()` with `math.isfinite()` guards. String concatenation (not `str.format()`).

### `scan/` (CLAUDE.md: thin orchestrator, no business logic)
- **phase_scoring.py** (modify): Wire ML indicator computation in Phase 2
- **phase_options.py** (modify): Wire macro fetch + neural surface in Phase 3
- **Constraint**: Cannot call pricing/ directly. Feature flag gating via `ScanConfig.enable_*`. New ML fields must be in `_PHASE3_FIELDS` tuple for normalization.

## Existing Patterns to Reuse

### 1. Feature Flag Pattern (models/config.py)
```python
class ScanConfig(BaseModel):
    enable_iv_analytics: bool = True  # existing pattern
    enable_ml_vol_forecast: bool = False  # new: opt-in, off by default
```
All ML features default to `False` — opt-in activation. Follows `FinancialDatasetsConfig` and `IntelligenceConfig` precedent.

### 2. Indicator Registration Pattern (scan/indicators.py)
Standard indicators use `IndicatorSpec` registry. Non-standard signatures (GARCH, ML regime) go in `_compute_ohlcv_dse()` or a new `_compute_ml_indicators()` helper, gated by config flag.

### 3. FRED Never-Raises Pattern (services/fred.py)
```python
async def fetch_macro_context(self) -> MacroContext:
    try: return await self._batch_fetch_series()
    except Exception: return MacroContext.fallback()
```

### 4. Guarded Import Pattern (services/openbb_service.py)
```python
def _get_statsmodels():
    try: import statsmodels.tsa.regime_switching.markov_regression; return ...
    except ImportError: return None
```
statsmodels, scikit-learn, torch/lightning all use this pattern — never hard imports in production path.

### 5. Context Rendering Pattern (agents/_parsing.py)
`_render_optional(label, value, fmt)` for each ML field. New fields added to appropriate domain renderer.

### 6. IndicatorSignals Extension Pattern (models/scan.py)
All `float | None = None` with comment block headers. `_normalize_non_finite` model_validator handles NaN/Inf → None.

### 7. VolSurfaceResult Compatibility (indicators/vol_surface.py)
NamedTuple with tiered computation. Neural surface should produce a parallel `NeuralSurfaceResult` NamedTuple (NamedTuples can't be subclassed for extension).

### 8. async Wrapping for Sync ML (services/ pattern)
`asyncio.to_thread(fn, *args)` + `asyncio.wait_for(timeout=...)` for all synchronous statsmodels/sklearn calls.

## Existing Code to Extend

| File | What Exists | What Needs Changing |
|------|-------------|---------------------|
| `services/fred.py` (239 lines) | Single DGS10 fetch, 2-tier cache, never-raises | Parameterize `_fetch_from_fred(series_id)`, add `fetch_macro_context()`, per-series TTL config |
| `indicators/regime.py` (278 lines) | `classify_market_regime()` (4-state heuristic) | Keep existing, add Markov-switching as complement in `regime_ml.py` |
| `indicators/iv_analytics.py` (430 lines) | `compute_ewma_vol_forecast()` (EWMA λ=0.94) | Keep existing, GARCH goes in new `vol_forecast.py` |
| `indicators/flow_analytics.py` (215 lines) | 5 pure-math flow functions | Add `detect_flow_anomalies()` using Isolation Forest |
| `scoring/composite.py` (191 lines) | 24 indicators, sum-to-1.0 guard | Add ML indicator weights, redistribute existing to maintain sum |
| `scoring/contracts.py` (493 lines) | `select_by_delta()`, `filter_contracts()` | Add optional clustering call after Greeks computation |
| `models/scan.py` (231 lines) | `IndicatorSignals` (68 fields) | Add ~8-12 ML indicator fields |
| `models/analysis.py` (867 lines) | `MarketContext` (~80 optional fields) | Add ~10-15 ML + macro fields, extend `validate_optional_finite` list |
| `models/config.py` (442 lines) | `ScanConfig`, `AppSettings` | Add `MLConfig(BaseModel)`, 4-6 feature flags |
| `agents/_parsing.py` | 4 domain renderers | Add ML fields to `render_volatility_context()`, new `render_macro_context()` section in `render_fundamental_context()` |
| `scan/phase_scoring.py` (~159 lines) | `run_scoring_phase()` | Wire `_compute_ml_indicators()` gated by config |
| `scan/phase_options.py` | Phase 3 orchestration | Wire macro fetch, neural surface, add fields to `_PHASE3_FIELDS` |

## Potential Conflicts

### 1. INDICATOR_WEIGHTS Sum-to-1.0 Guard (CRITICAL)
Adding any new ML indicator weight to `scoring/composite.py` requires proportional reduction of existing weights. The import-time `sum==1.0` assertion will block startup if violated. Every weight addition needs a redistribution pass. **Mitigation**: Plan weight redistribution before implementation; test import immediately.

### 2. IndicatorSignals Field Count Growth
Model has 65 fields, adding ~8-12 more. The `_normalize_non_finite` validator iterates all fields — safe but increasing iteration cost. **Mitigation**: Acceptable overhead; group ML fields with clear comment block.

### 3. MarketContext Validator List
The massive `validate_optional_finite` `@field_validator` covers every optional float field by name. New ML fields MUST be added to this list or NaN/Inf will silently pass. **Mitigation**: Add to validator list in same commit as field addition; test with NaN values.

### 4. Optional Heavy Dependencies
statsmodels (~50MB), scikit-learn (~30MB), PyTorch (~2GB) significantly increase install size. **Mitigation**: Guarded imports + optional extras group in pyproject.toml (`uv add --optional ml statsmodels scikit-learn`). Phase 3 (PyTorch) as separate optional extra (`uv add --optional neural torch pytorch-lightning`).

### 5. FRED API Rate Limits
Expanding from 1 to 8 series multiplies API calls 8x. **Mitigation**: Batch fetch with `asyncio.gather()`, per-series TTL caching (24h daily, 168h monthly), never-raises pattern.

### 6. Dimensional Score Integration
`scoring/dimensional.py` `REGIME_WEIGHT_PROFILES` uses `MarketRegime` enum for regime-adjusted weights. ML regime output should map to existing `MarketRegime` values or extend the enum. **Mitigation**: Map Markov-switching states to existing 4-state enum; don't create a parallel regime taxonomy.

## Open Questions

1. **Dependency strategy**: Should statsmodels/scikit-learn be required deps or optional extras? PyTorch is clearly optional, but Phase 1 libs are lighter. The PRD says "all added via `uv add`" without specifying optional.

2. **Weight redistribution**: How should the 24 existing indicator weights be redistributed when adding ML signals (GARCH forecast, regime probability)? Should ML indicators replace existing ones (e.g., GARCH replaces EWMA) or add new weight slots?

3. **Offline training data**: The ML regime classifier (FR-S4) needs historical scan outcome data. How much data has accumulated? Is there enough for meaningful training? (FR-S5 weight validation relocated to ai-agency-evolution.)

4. **`analysis/` module ambiguity**: The system-patterns.md boundary table lists `analysis/` as a module, but the actual vol surface and HV estimator code lives in `indicators/`. Where should new ML model code live — `indicators/` (established) or a new `analysis/ml/` package?

5. **Neural surface warm-start**: FR-S8 specifies per-ticker model checkpoint persistence. Where should checkpoints be stored? `data/` directory (alongside SQLite)? A new `models_cache/` directory?

6. **Phase 3 performance budget**: PRD allows <3s for Phase 1 features and <6s including neural models. Current Phase 3 takes ~2-4s per ticker. Does this leave enough headroom for GARCH (500ms) + Markov (1s) + neural inference (100ms)?

## Recommended Architecture

### Dependency Groups
```toml
[project.optional-dependencies]
ml = ["arch>=7.0", "statsmodels>=0.14", "scikit-learn>=1.5"]
neural = ["torch>=2.3", "pytorch-lightning>=2.3"]
```
Note: `arch >=7.0` is a standalone GARCH library (MIT), separate from statsmodels.

### New Module Structure
```
indicators/
    vol_forecast.py    # GARCH/EGARCH (arch, guarded import) + ADF (statsmodels, guarded)
    regime_ml.py       # Markov-switching + ML classification (statsmodels + sklearn, guarded)
    macro.py           # Macro regime derivation (pure math, no ML deps)
    flow_analytics.py  # +detect_flow_anomalies() (sklearn IsolationForest, guarded)

pricing/
    neural_surface.py  # MLP IV surface (PyTorch Lightning, guarded import)
    trajectory.py      # LSTM trajectories (PyTorch Lightning, guarded import)

scoring/
    clustering.py      # K-means on Greeks vectors (sklearn, guarded import)

models/
    macro.py           # MacroContext, MacroRegimeResult, FredSeriesConfig

tools/
    train_regime_classifier.py  # Offline training script
    # validate_indicator_weights.py — relocated to ai-agency-evolution PRD (Epic 5)
```

### Integration Flow
```
Phase 1 (universe) — unchanged
Phase 2 (indicators):
  existing indicators → IndicatorSignals
  + GARCH/EGARCH vol forecast (gated by enable_ml_vol_forecast)
  + Markov-switching regime (gated by enable_ml_regime)
Phase 3 (options):
  existing chain/IV → IndicatorSignals
  + FRED macro fetch → MacroContext → macro indicators
  + ML regime classification inference (gated)
  + Neural surface (gated by enable_neural_pricing)
  + Contract clustering (gated by enable_contract_clustering)
  + Flow anomaly detection (gated by enable_flow_anomalies)
Phase 4 (persist) — unchanged (new fields auto-persisted via IndicatorSignals)
Agents:
  + MacroContext block in fundamental/risk agent prompts
  + Vol forecast vs IV comparison in volatility agent prompt
  + Regime probabilities in all agent prompts
  + Flow anomaly flags in flow agent prompt
```

### Config Structure
```python
class MLConfig(BaseModel):
    """ML/statistical model configuration. BaseModel, NOT BaseSettings."""
    garch_p: int = 1
    garch_q: int = 1
    markov_n_regimes: int = 3
    regime_model_path: Path | None = None
    contract_n_clusters: int = 4
    surface_method: Literal["spline", "neural"] = "spline"
    trajectory_horizons: list[int] = [30, 60, 90]
    model_cache_dir: Path | None = None

class ScanConfig(BaseModel):
    # Existing flags...
    enable_ml_vol_forecast: bool = False
    enable_ml_regime: bool = False
    enable_macro_context: bool = False
    enable_neural_pricing: bool = False
    enable_contract_clustering: bool = False
    enable_flow_anomalies: bool = False
```

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/indicators/` — pure function tests, parametrized with `@pytest.mark.parametrize`, test NaN/None edge cases, `InsufficientDataError` on bad input
- `tests/unit/scoring/` — weight sum validation, normalization tests, direction tests
- `tests/unit/services/` — mock httpx responses, test caching, test fallback on error
- `tests/unit/models/` — Pydantic validation tests, NaN rejection, frozen model tests
- `tests/unit/agents/` — mock `TestModel`, test prompt rendering, test output validation

### Test Strategy for ML Features
- **Vol forecast**: Parametrized tests with known GARCH parameters on synthetic AR(1)-GARCH(1,1) returns. Test convergence failure → None. Test ADF on stationary/non-stationary series.
- **Markov regime**: Test on synthetic 2-regime data (low-vol/high-vol). Test convergence failure → None. Test transition probability bounds.
- **ML regime classifier**: Test with pre-trained fixture model on known feature vectors. Test missing model → None.
- **Contract clustering**: Test K-means on synthetic Greeks vectors. Test <10 contracts → empty dict.
- **Neural surface**: Test with synthetic IV surface data. Test <30 points → spline fallback. Test PyTorch not installed → None.
- **FRED expansion**: Mock httpx responses for each series. Test per-series TTL. Test batch failure isolation.
- **Macro regime**: Test expansionary/contractionary/transitional classification rules.
- **Agent rendering**: Test each ML field appears in appropriate context block when populated.

### Mocking Strategies
- `unittest.mock.patch()` for guarded imports (simulate missing statsmodels/sklearn/torch)
- `httpx` mock transport for FRED API responses
- `pydantic_ai.models.test.TestModel` for agent tests
- Synthetic data generators for time series (known parameters → expected results)

## Estimated Complexity

**XL** — Justification:
- 4 new heavy dependencies (arch, statsmodels, scikit-learn, PyTorch Lightning) with guarded import patterns
- 8 new source files across 7 modules
- ~220 new tests across 3 epics
- Touches every layer: models, indicators, scoring, pricing, services, agents, scan, tools
- 3 delivery epics with cross-epic dependencies
- Offline training scripts (tools/) are a new code category for this project
- Weight redistribution in composite scoring requires careful tuning
- Optional dependency management adds CI/CD complexity
- Neural models (Epic C) are the project's first PyTorch integration

**Restructured into 3 independent epics** (5+4+4 issues) within the project's observed 4-7 issue sweet spot.

## Cross-PRD Contracts

### Contract 1: WeightSnapshot Schema (owned by ai-agency)
- scientific-ml adds new ML indicators to `INDICATOR_WEIGHTS` with static weight redistribution (maintains `sum == 1.0`)
- ai-agency Epic 5 extends `WeightSnapshot` with `WeightType.INDICATOR` and builds the dynamic tuning loop
- scientific-ml does NOT modify `WeightSnapshot` or auto-tune infrastructure

### Contract 2: Agent Context Rendering (additive convention)
- Both PRDs append independent `render_*_context()` functions to `agents/_parsing.py`
- Each function is self-contained, returns `str | None`, called by orchestrator
- scientific-ml: `render_macro_context()`, vol forecast fields in `render_volatility_context()`
- ai-agency: `render_learned_patterns()` for strategy memory injection

### Contract 3: Volatility Agent Dual Modification (non-conflicting sections)
- scientific-ml modifies system prompt content + `DebateDeps` fields (vol forecast context)
- ai-agency modifies tool registration + adds `DeskDeps` for interactive mode
- Agent operates in one mode at a time (debate vs interactive) — no runtime conflict

### Dependency Graph (cross-PRD)
```
Epic A: Statistical ···soft···> ai-agency Epic 1 (Vol desk gains garch_forecast tool)
Epic B: ML Classification ···soft···> ai-agency Epic 5 (more indicators to tune)
Epic C: Neural Models — no cross-PRD dependencies
All soft deps degrade gracefully to None.
```
