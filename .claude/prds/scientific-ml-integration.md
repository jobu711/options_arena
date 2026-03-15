---
name: scientific-ml-integration
description: Integrate arch, statsmodels, scikit-learn, PyTorch Lightning, and expanded FRED data into Options Arena for GARCH volatility forecasting, regime classification, neural pricing, and macro context
status: planned
created: 2026-03-13T00:00:00Z
---

# PRD: scientific-ml-integration

## Executive Summary

Integrate scientific computing and data libraries — `arch` (GARCH), statsmodels, scikit-learn, PyTorch Lightning, and expanded FRED economic data — into Options Arena's existing pipeline. These additions unlock four capabilities absent from the current system: (1) GARCH/EGARCH volatility forecasting via `arch` and Markov-switching regime detection via statsmodels, (2) ML-based market regime classification and contract clustering via scikit-learn, (3) neural IV surface fitting and trajectory forecasting via PyTorch Lightning, and (4) macro-economic context (yield curve spreads, CPI, PMI, unemployment) via expanded FRED series. Each library has a corresponding Claude Code skill installed at `.claude/skills/` providing API references and code templates.

**Delivery structure**: 3 independent epics (A: Statistical Foundation, B: ML Classification, C: Neural Models) with 13 issues total across 8 new files and ~220 estimated tests. Indicator weight validation (former FR-S5) has been relocated to the `ai-agency-evolution` PRD where it belongs architecturally.

**Relationship to other PRDs**: This PRD builds on foundations established by `native-quant` (HV estimators, vol surface, second-order Greeks) and `volatility-intelligence` (IV smoothing, fitted surface, mispricing detection). Statsmodels volatility forecasting extends the HV estimators in `indicators/volatility.py`. Scikit-learn regime classification enhances the existing regime detection in `indicators/regime.py`. PyTorch Lightning neural pricing complements the BSM/BAW models in `pricing/`. FRED expansion extends `services/fred.py`.

## Problem Statement

### 1. Volatility forecasting is backward-looking only

Options Arena computes historical volatility (close-to-close, Yang-Zhang via `native-quant`) but never *forecasts* future volatility. The Volatility Agent debates using realized vol and IV rank — both are descriptive, not predictive. GARCH-family models are the industry standard for volatility forecasting and can produce forward-looking vol estimates that directly compare against implied volatility, enabling a true "IV vs forecast HV" signal.

Additionally, volatility regimes (low-vol trending, high-vol mean-reverting, crisis) are detected via simple threshold heuristics in `indicators/regime.py`. Markov-switching models from statsmodels provide a statistically rigorous alternative with transition probabilities.

### 2. Regime detection is heuristic, contract analysis lacks clustering

Market regime classification in `indicators/regime.py` uses fixed thresholds. ML classifiers (Random Forest, Gradient Boosting) trained on historical market data can learn non-linear regime boundaries and provide probability-calibrated regime labels that improve downstream scoring and agent context.

Options flow analysis lacks anomaly detection — unusual volume/OI patterns that signal institutional activity are invisible. Contract evaluation treats each option independently with no Greek-profile clustering to reveal natural groupings (income plays, vol bets, directional leveraged positions).

### 3. Pricing and forecasting are purely parametric

BSM and BAW in `pricing/bsm.py` and `pricing/american.py` are closed-form parametric models. They cannot capture the complex, non-linear structure of real IV surfaces (skew dynamics, term structure kinks, event-driven distortions). Neural networks can learn the empirical IV surface from market data, providing a non-parametric complement.

Price trajectory forecasting for the underlying does not exist — agents have no probabilistic view of where the stock might be at expiration. LSTM/Transformer models can produce trajectory distributions that feed probability-of-profit estimates.

### 4. Macro context is limited to a single series

`services/fred.py` fetches only the 10-year Treasury yield (DGS10) as a risk-free rate proxy. Options pricing and agent decisions are influenced by broader macro conditions — yield curve inversions, Fed policy rate, inflation expectations, labor market health — none of which are available to agents. The Fundamental Agent and Risk Agent operate without macro context.

**Why now**: The `.claude/skills/` directory now contains API references and code templates for all four libraries. The existing pipeline architecture (indicators → scoring → agents) provides clean integration points. The `native-quant` and `volatility-intelligence` PRDs establish the vol surface and indicator infrastructure that these ML capabilities extend.

## User Stories

### US-1: Analyst wants forward-looking volatility forecasts
**As** a trader using the scan pipeline, **I want** GARCH-forecasted volatility alongside historical and implied volatility **so that** I can assess whether the market is pricing future vol too high or too low relative to a statistical forecast.

**Acceptance criteria:**
- GARCH(1,1) and EGARCH(1,1) forecasts computed from daily returns in `indicators/vol_forecast.py`
- `vol_forecast_garch` and `vol_forecast_egarch` populated on `IndicatorSignals`
- `iv_vs_forecast_spread` (IV minus GARCH forecast) available to Volatility Agent
- Graceful fallback to None when insufficient history (<252 trading days) or convergence failure

### US-2: Analyst wants statistically rigorous regime detection
**As** a trader, **I want** market regimes identified via Markov-switching models with transition probabilities **so that** I can understand the likelihood of regime changes, not just the current state.

**Acceptance criteria:**
- Markov-switching model fitted on returns in `indicators/regime_ml.py`
- Regime labels (low-vol, high-vol, crisis) with smoothed probabilities
- `regime_transition_prob` (probability of leaving current regime) available to agents
- Falls back to existing heuristic regime detection on convergence failure

### US-3: Analyst wants ML-based regime classification (was US-4)
**As** a trader, **I want** regime classification from a trained ML model that considers multiple features simultaneously **so that** regime labels account for the interaction between volatility, trend, volume, and macro indicators.

**Acceptance criteria:**
- GBM classifier trained on feature vectors from `indicators/` modules
- Regime probabilities (trending/mean-reverting/volatile) available to all agents
- Classification happens in Phase 2 (indicators) alongside existing regime heuristics
- Model retrained periodically via offline script in `tools/`

### US-4: Analyst wants contracts clustered by Greeks profile (was US-5)
**As** a trader evaluating a chain, **I want** contracts grouped by their Greeks profile (delta/gamma/theta/vega clustering) **so that** I can see natural groupings — income plays vs leveraged directional bets vs vol bets.

**Acceptance criteria:**
- K-means clustering on normalized Greeks vectors in `scoring/contracts.py`
- Cluster labels (e.g., "high-gamma-low-theta", "income", "vol-play") assigned to contracts
- Cluster context available in debate for contract selection discussion
- Degrades to no-clustering when chain has <10 contracts

### US-5: Analyst wants neural IV surface fitting (was US-6)
**As** a quantitative analyst, **I want** a neural network that fits the IV surface from market data **so that** I can capture non-linear surface features (skew dynamics, kinks, event distortions) that parametric splines miss.

**Acceptance criteria:**
- MLP-based IV surface model in `pricing/neural_surface.py` using PyTorch Lightning
- Trained on (log-moneyness, DTE, IV) triples from live chain data
- Produces fitted IVs and residuals compatible with `VolSurfaceResult`
- Falls back to scipy spline surface (`native-quant`) when insufficient data or GPU unavailable
- Model checkpoint persistence for warm-start across scans

### US-6: Analyst wants price trajectory forecasts (was US-7)
**As** a trader, **I want** probabilistic price trajectory forecasts at target expiration dates **so that** I can see model-estimated probability of profit for recommended contracts.

**Acceptance criteria:**
- LSTM or Transformer model in `pricing/trajectory.py` using PyTorch Lightning
- Produces distribution of price paths at 30/60/90 DTE horizons
- `prob_profit_neural` indicator derived from trajectory distribution
- Falls back to lognormal assumption (existing BSM framework) when model unavailable

### US-7: Analyst wants macro context in agent debates (was US-8)
**As** a trader, **I want** agents to reference yield curve slope, inflation trends, and labor market data **so that** macro regime context informs the trade thesis, especially for longer-dated options.

**Acceptance criteria:**
- `FredService` extended to fetch DGS10-DGS2 spread, FEDFUNDS, VIXCLS, CPIAUCSL, INDPRO, UNRATE
- Macro data cached with configurable TTL (24h default, 7d for monthly series)
- `MacroContext` model populated and available to Fundamental Agent and Risk Agent
- Macro regime label (expansionary/contractionary/transitional) derived from indicator combination

## Requirements

### Functional Requirements

#### FR-S1: statsmodels — Volatility Forecasting

Implement in `indicators/vol_forecast.py`:

```python
def compute_garch_forecast(
    returns: pd.Series,
    horizon: int = 5,
    model: str = "GARCH",  # or "EGARCH"
) -> VolForecastResult | None:
    """Fit GARCH/EGARCH model and produce h-step-ahead vol forecast.

    Returns None on insufficient data (<252 obs) or convergence failure.
    Uses `arch` package (`arch >=7.0`, MIT) for GARCH/EGARCH fitting.
    """
```

**Models**:
- GARCH(1,1): baseline symmetric volatility model
- EGARCH(1,1): asymmetric model capturing leverage effect (negative returns increase vol more than positive)

**Integration**:
- Called in Phase 2 indicator computation after price data is fetched
- Results populate `IndicatorSignals.vol_forecast_garch`, `vol_forecast_egarch`
- Derived indicator: `iv_vs_forecast_spread = atm_iv_30d - vol_forecast_garch`
- Volatility Agent prompt enriched with forecast vs IV comparison

#### FR-S2: statsmodels — Regime Detection via Markov-Switching

Implement in `indicators/regime_ml.py`:

```python
def compute_markov_regime(
    returns: pd.Series,
    n_regimes: int = 3,
) -> MarkovRegimeResult | None:
    """Fit Markov-switching model on returns.

    Returns regime labels, smoothed probabilities, and transition matrix.
    None on insufficient data or convergence failure.
    """
```

**Integration**:
- Complement (not replace) existing `indicators/regime.py` heuristics
- `regime_markov_label`, `regime_transition_prob` on `IndicatorSignals`
- All agents receive regime context; Risk Agent weighs transition probability

#### FR-S3: statsmodels — Stationarity Testing

Implement in `indicators/vol_forecast.py`:

```python
def test_stationarity(series: pd.Series) -> StationarityResult:
    """ADF test for stationarity. Used to validate indicator series
    before time series modeling."""
```

- Gate for GARCH fitting: only fit on stationary return series
- Diagnostic for custom indicators: log warning if non-stationary series used in scoring

#### FR-S4: scikit-learn — Market Regime Classification

Implement offline training in `tools/train_regime_classifier.py` and inference in `indicators/regime_ml.py`:

```python
def classify_regime_ml(
    feature_vector: dict[str, float],
    model_path: Path | None = None,
) -> RegimeClassification | None:
    """Classify market regime using pre-trained GBM model.

    Feature vector built from Phase 2 indicators. Returns class probabilities.
    None when model not available (graceful degradation).
    """
```

**Features**: RSI, ADX, ATR/price ratio, volume ratio, IV rank, IV-HV spread, put-call ratio, Bollinger %B, MACD histogram
**Labels**: trending-up, trending-down, mean-reverting, high-volatility, low-volatility
**Training**: offline script using labeled historical scan data

#### FR-S6: scikit-learn — Contract Clustering

Implement in `scoring/clustering.py`:

```python
def cluster_contracts_by_greeks(
    contracts: list[OptionContract],
    n_clusters: int = 4,
) -> dict[str, list[OptionContract]]:
    """K-means clustering on normalized (delta, gamma, theta, vega) vectors.
    Returns labeled groups for debate context."""
```

- Feature vector: normalized delta, gamma, theta, vega (min-max scaling)
- Cluster labels assigned via centroid analysis (highest feature → label)
- Integration: `scoring/contracts.py` calls after Greeks computation
- Degrades to empty dict when <10 contracts with valid Greeks

#### FR-S7: scikit-learn — Anomaly Detection for Flow

Implement in `indicators/flow_analytics.py` (extend existing):

```python
def detect_flow_anomalies(
    flow_features: pd.DataFrame,
) -> FlowAnomalyResult:
    """Isolation Forest on options flow features.
    Flags unusual volume/OI patterns for Flow Agent."""
```

- Features: volume/OI ratio, call/put volume ratio, volume vs 20d average, large trade concentration
- Flow Agent prompt enriched with anomaly flags

#### FR-S8: PyTorch Lightning — Neural IV Surface

Implement in `pricing/neural_surface.py`:

```python
class IVSurfaceNet(L.LightningModule):
    """MLP that maps (log_moneyness, dte) → IV.

    Trained per-ticker on live chain data. Produces fitted IVs and
    residuals compatible with VolSurfaceResult.
    """
```

**Architecture**:
- Input: (log_moneyness, dte_normalized) — 2 features
- Hidden: 3 layers, 64 units each, ReLU activation, BatchNorm
- Output: 1 unit (IV), softplus activation (ensures positive output)
- Loss: MSE on IV values, L2 regularization

**Integration**:
- Alternative surface fitter in `indicators/vol_surface.py` `compute_vol_surface()`
- Config flag `ScanConfig.surface_method: Literal["spline", "neural"] = "spline"`
- Falls back to spline when: <30 data points, Lightning not installed, GPU timeout
- Checkpoint saved per-ticker for warm-start on subsequent scans

#### FR-S9: PyTorch Lightning — Price Trajectory Forecasting

Implement in `pricing/trajectory.py`:

```python
class TrajectoryLSTM(L.LightningModule):
    """LSTM that produces probabilistic price trajectories.

    Input: 60-day historical (OHLCV + indicators) sequence.
    Output: distribution parameters (mean, std) at target horizons.
    """
```

**Architecture**:
- Input: 60-day sequence of (open, high, low, close, volume, returns, atr, rsi) — 8 features
- LSTM: 2 layers, 128 hidden units, dropout 0.2
- Output head: per-horizon (mean, std) for lognormal distribution at 30/60/90 DTE

**Integration**:
- `prob_profit_neural` indicator: P(S_T > strike) from predicted distribution
- Available to all agents as supplementary probability estimate
- Falls back to BSM lognormal assumption when model unavailable

#### FR-S10: PyTorch Lightning — Deep Hedging (Future Phase)

Placeholder for Phase 3:
- Neural network that learns optimal hedging strategy for Greek-neutral portfolio construction
- Trains on simulated paths from GARCH process
- Outputs hedge ratios that minimize PnL variance
- **Deferred**: requires stable vol forecasting (FR-S1) and trajectory models (FR-S9) first

#### FR-S11: FRED Expanded — Additional Economic Series

Extend `services/fred.py` `FredService`:

```python
# New series to fetch alongside existing DGS10
FRED_SERIES: dict[str, FredSeriesConfig] = {
    "DGS10": FredSeriesConfig(id="DGS10", ttl_hours=24, transform="level"),
    "DGS2": FredSeriesConfig(id="DGS2", ttl_hours=24, transform="level"),
    "DGS10_DGS2": FredSeriesConfig(id="T10Y2Y", ttl_hours=24, transform="level"),  # yield curve spread
    "FEDFUNDS": FredSeriesConfig(id="FEDFUNDS", ttl_hours=168, transform="level"),  # weekly update sufficient
    "VIXCLS": FredSeriesConfig(id="VIXCLS", ttl_hours=24, transform="level"),
    "CPIAUCSL": FredSeriesConfig(id="CPIAUCSL", ttl_hours=168, transform="pct_change_yoy"),
    "INDPRO": FredSeriesConfig(id="INDPRO", ttl_hours=168, transform="pct_change_yoy"),  # Industrial Production Index (NAPM removed from FRED 2016)
    "UNRATE": FredSeriesConfig(id="UNRATE", ttl_hours=168, transform="level"),
}
```

**Integration**:
- `MacroContext` model in `models/analysis.py` aggregates all series
- `FredService.fetch_macro_context() -> MacroContext` — batch fetch with per-series TTL caching
- `macro_regime` derived: expansionary (PMI>50, low unemployment, positive yield curve), contractionary (inverse), transitional
- Fundamental Agent and Risk Agent prompts enriched with macro block

#### FR-S12: FRED Expanded — Macro Regime Signal

Implement in `indicators/macro.py`:

```python
def compute_macro_regime(macro: MacroContext) -> MacroRegimeResult:
    """Classify macro environment from FRED data.

    Rules:
    - Expansionary: yield_curve_spread > 0 AND pmi > 50 AND unemployment < 5%
    - Contractionary: yield_curve_spread < 0 OR pmi < 45
    - Transitional: all other
    """
```

- Simple rule-based initially (ML regime via FR-S4 can later incorporate macro features)
- Available to Risk Agent for position sizing context
- Available to Fundamental Agent for sector rotation signals

### Non-Functional Requirements

#### NFR-ML1: New Dependencies
Unlike `native-quant` and `volatility-intelligence`, this PRD requires new packages:
- `arch >=7.0` — GARCH/EGARCH volatility forecasting (Epic A, standalone MIT library)
- `statsmodels` — Markov-switching models, ADF stationarity tests (Epic A)
- `scikit-learn` — classifiers, clustering, anomaly detection (Epic B)
- `pytorch-lightning` — neural network training (Epic C)
- `torch` — PyTorch backend for Lightning (Epic C)

All added via `uv add` with version pins.

#### NFR-ML2: Graceful Degradation
Every ML-powered feature must degrade gracefully:
- statsmodels convergence failure → None (existing heuristics used)
- scikit-learn model not trained → None (no regime/clustering)
- PyTorch not installed → spline fallback (existing `native-quant` surface)
- FRED API down → cached values or None (existing pattern)

The pipeline must never error due to ML model unavailability.

#### NFR-ML3: Performance Budget
- Phase 2 (indicators): GARCH fit ~500ms per ticker, Markov-switching ~1s → budget +2s per ticker
- Phase 3 (scoring): clustering <100ms, anomaly detection <200ms
- Neural surface: inference <50ms (training ~5s, cached checkpoint), trajectory inference <100ms
- FRED batch fetch: parallelized, <2s total with caching

Total per-ticker overhead: <3s for Phase 1 features, <6s including neural models.

#### NFR-ML4: Offline vs Online Separation
- **Online (in pipeline)**: GARCH forecast, Markov regime, ML regime inference, contract clustering, anomaly detection, neural surface inference, FRED fetch
- **Offline (in tools/)**: regime classifier training, indicator weight validation, trajectory model training, neural surface pre-training

Training never happens in the scan pipeline. Only inference from pre-trained models.

#### NFR-ML5: Backward Compatibility
- All new `IndicatorSignals` and `MarketContext` fields are `Optional` with `None` defaults
- Existing scoring, agents, and tests unaffected when ML features return None
- Config flags gate each ML feature independently (`ScanConfig.use_garch_forecast: bool = False`, etc.)
- Default config has all ML features disabled — opt-in activation

## Technical Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Options Arena Pipeline                     │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Phase 1  │ Phase 2  │ Phase 3  │ Scoring  │ Debate Agents   │
│ Price    │ Indicators│ Options │          │                 │
│ Data     │          │ Chain   │          │                 │
├──────────┼──────────┼──────────┼──────────┼─────────────────┤
│          │ +GARCH   │ +Neural  │ +Cluster │ +MacroContext   │
│ +FRED    │ +Markov  │  Surface │ +Anomaly │ +Vol Forecast   │
│  expand  │ +ML      │ +Traj.  │  detect  │ +Regime Probs   │
│          │  regime  │  model  │          │ +Neural Probs   │
└──────────┴──────────┴──────────┴──────────┴─────────────────┘

Skills (.claude/skills/):
├── statsmodels/       → FR-S1, FR-S2, FR-S3
├── scikit-learn/      → FR-S4, FR-S6, FR-S7
├── pytorch-lightning/ → FR-S8, FR-S9, FR-S10
└── fred-economic-data/→ FR-S11, FR-S12
```

### New Files

| File | Module | Purpose |
|------|--------|---------|
| `indicators/vol_forecast.py` | indicators | GARCH/EGARCH forecasting + ADF tests |
| `indicators/regime_ml.py` | indicators | Markov-switching + ML regime classification |
| `indicators/macro.py` | indicators | Macro regime derivation from FRED data |
| `scoring/clustering.py` | scoring | Contract Greeks clustering |
| `pricing/neural_surface.py` | pricing | PyTorch Lightning IV surface model |
| `pricing/trajectory.py` | pricing | LSTM price trajectory forecasting |
| `models/macro.py` | models | MacroContext, MacroRegimeResult models |
| `tools/train_regime_classifier.py` | tools | Offline regime classifier training |

### Modified Files

| File | Change |
|------|--------|
| `services/fred.py` | Extend with additional series, batch fetch, per-series TTL |
| `indicators/flow_analytics.py` | Add Isolation Forest anomaly detection |
| `indicators/regime.py` | Integrate Markov-switching as alternative to heuristics |
| `scoring/contracts.py` | Add Greeks clustering call |
| `models/analysis.py` | Add MacroContext fields, vol forecast fields to MarketContext |
| `models/config.py` | ML feature flags on ScanConfig, PricingConfig |
| `agents/_parsing.py` | Render macro context, vol forecast, regime probs blocks |
| `agents/fundamental_agent.py` | Consume MacroContext in prompt |
| `agents/risk.py` | Consume macro regime + regime transition probs |
| `agents/volatility.py` | Consume vol forecast vs IV comparison |
| `agents/flow_agent.py` | Consume anomaly detection flags |
| `scan/phase_options.py` | Neural surface + trajectory model integration |

### Data Flow

```
FRED API ──→ FredService.fetch_macro_context() ──→ MacroContext
                                                      │
Historical prices ──→ GARCH fit ──→ vol_forecast_garch ──→ IndicatorSignals
                  ──→ Markov-switching ──→ regime_markov   │
                  ──→ ML regime ──→ regime_ml_label        │
                                                           ▼
Option chain ──→ Neural surface ──→ VolSurfaceResult  ──→ MarketContext
             ──→ Greeks compute ──→ Contract clustering     │
             ──→ Flow features ──→ Anomaly detection        ▼
                                                     Agent Prompts
Price history ──→ Trajectory LSTM ──→ prob_profit_neural ──┘
```

## Success Criteria

| Metric | Target |
|--------|--------|
| GARCH forecast populated | >80% of tickers with 252+ days history |
| Markov regime populated | >70% of tickers (convergence-dependent) |
| ML regime inference latency | <100ms per ticker |
| Neural surface R² improvement over spline | >5% on liquid chains |
| FRED macro series fetched | 8/8 series with <2s batch latency |
| Contract clustering populated | >60% of chains with 10+ contracts |
| Existing test suite passes | 100% (zero regressions) |
| New test count | ~200 tests across phases |
| Pipeline overhead (Phase 1 features) | <3s per ticker |

## Constraints & Assumptions

### Constraints
- `indicators/` module: pure math — pandas/numpy in, float/Series/NamedTuple out. No Pydantic models, no API calls.
- `pricing/` module: scalar float in/out for pricing functions. Neural models are the exception — they encapsulate PyTorch internals but expose the same interface.
- `scoring/` imports `pricing/dispatch` only — never `pricing/bsm` or `pricing/american` directly.
- `services/` module: all external API calls here. FRED expansion stays in `services/fred.py`.
- All models with Decimal fields need `field_serializer`. All float fields need `math.isfinite()` validators.
- Frozen models use `model_copy(update=...)` for field updates.
- ML training never runs in the live scan pipeline — inference only from pre-trained checkpoints.

### Assumptions
- 252+ trading days of history available for most scanned tickers (required for GARCH)
- `arch >=7.0` — standalone GARCH library (MIT, separate from statsmodels)
- PyTorch Lightning can run in CPU mode (GPU optional, not required)
- FRED API key already configured (existing `FredService` pattern)
- Historical scan outcome data available for offline training scripts (may need to accumulate)

## Out of Scope

- **Reinforcement learning for trade execution** — too complex for initial integration
- **Real-time model retraining** — all training is offline, scheduled
- **Multi-asset portfolio optimization** — single-ticker focus maintained
- **Alternative data sources** — news sentiment, social media (separate data PRD)
- **Model explainability UI** — SHAP/LIME visualization deferred to frontend epic
- **Backtesting framework** — historical replay of ML signals deferred
- **GPU cluster deployment** — single-machine CPU/GPU sufficient for current scale
- **AutoML / hyperparameter search** — manual architecture selection initially
- **Indicator weight validation via ML** — moved to ai-agency-evolution PRD (Self-Improvement Phase 1, Epic 5)

## Delivery Epics

### Epic A: Statistical Computation Foundation (arch + statsmodels + FRED)
**Dependencies**: `native-quant` Wave 1 (HV estimators) should be complete.
**New dependencies**: `arch >=7.0`, `statsmodels`

| Issue | FR | Description | New Files | Modified Files | Est. Tests |
|-------|-----|-------------|-----------|----------------|------------|
| A1 | FR-S11 | FRED service expansion + `MacroContext` model + batch fetch with per-series TTL | 1 (`models/macro.py`) | 2 (`services/fred.py`, `models/config.py`) | ~25 |
| A2 | FR-S12 | Macro regime derivation + agent prompt enrichment (fundamental + risk agents) | 1 (`indicators/macro.py`) | 4 (`agents/fundamental_agent.py`, `agents/risk.py`, `agents/_parsing.py`, `models/analysis.py`) | ~15 |
| A3 | FR-S1+S3 | GARCH/EGARCH vol forecasting via `arch` + ADF stationarity gate | 1 (`indicators/vol_forecast.py`) | 1 (`models/analysis.py`) | ~30 |
| A4 | FR-S2 | Markov-switching regime detection via `statsmodels` | 1 (`indicators/regime_ml.py`) | 1 (`indicators/regime.py`) | ~20 |
| A5 | — | Pipeline integration: wire GARCH + Markov + macro into Phase 2/3, config flags, volatility agent enrichment | 0 | 3 (`scan/phase_scoring.py`, `agents/volatility.py`, `models/config.py`) | ~15 |

### Epic B: ML Classification & Scoring (scikit-learn)
**Dependencies**: Epic A complete (indicators available for feature vectors).
**New dependency**: `scikit-learn`

| Issue | FR | Description | New Files | Modified Files | Est. Tests |
|-------|-----|-------------|-----------|----------------|------------|
| B1 | FR-S4a | Offline regime classifier training script (`tools/train_regime_classifier.py`) | 1 (`tools/train_regime_classifier.py`) | 0 | ~15 |
| B2 | FR-S4b | ML regime inference in pipeline + config flags | 0 | 2 (`indicators/regime_ml.py`, `models/config.py`) | ~15 |
| B3 | FR-S6 | Contract Greeks clustering (K-means in `scoring/clustering.py`) | 1 (`scoring/clustering.py`) | 1 (`scoring/contracts.py`) | ~15 |
| B4 | FR-S7 | Flow anomaly detection (Isolation Forest in `indicators/flow_analytics.py`) | 0 | 1 (`indicators/flow_analytics.py`) | ~10 |

### Epic C: Neural Models (PyTorch Lightning)
**Dependencies**: Epic A-B complete. `native-quant` Wave 2 (vol surface) complete.
**New dependencies**: `pytorch-lightning`, `torch` (optional extras)

| Issue | FR | Description | New Files | Modified Files | Est. Tests |
|-------|-----|-------------|-----------|----------------|------------|
| C1 | FR-S8a | Neural IV surface model + training harness (`pricing/neural_surface.py`) | 1 (`pricing/neural_surface.py`) | 1 (`models/config.py`) | ~20 |
| C2 | FR-S8b | Neural surface pipeline integration + spline fallback | 0 | 2 (`indicators/vol_surface.py`, `scan/phase_options.py`) | ~10 |
| C3 | FR-S9a | LSTM trajectory forecasting model (`pricing/trajectory.py`) | 1 (`pricing/trajectory.py`) | 1 (`models/analysis.py`) | ~20 |
| C4 | FR-S9b | Trajectory integration + `prob_profit_neural` + agent enrichment | 0 | 3 (`agents/volatility.py`, `agents/_parsing.py`, `models/config.py`) | ~10 |

### Epic Summary

| Epic | Focus | Issues | New Files | Est. Tests |
|------|-------|--------|-----------|------------|
| A | Statistical Computation (arch + statsmodels + FRED) | 5 | 4 | ~105 |
| B | ML Classification (scikit-learn) | 4 | 2 | ~55 |
| C | Neural Models (PyTorch Lightning) | 4 | 2 | ~60 |
| **Total** | | **13** | **8** | **~220** |

```
Epic A: Statistical Foundation (5 issues)
    │   FRED → macro regime → GARCH → Markov → pipeline wiring
    ▼
Epic B: ML Classification (4 issues)
    │   regime training → inference → clustering → anomaly detection
    ▼
Epic C: Neural Models (4 issues)
        surface model → surface integration → trajectory model → trajectory integration
```

Note: Issue A3 merges FR-S1 (GARCH) + FR-S3 (ADF stationarity) since ADF is a gate for GARCH fitting. This yields 13 issues from 12 unique FRs.

## Cross-PRD Coordination

This PRD and `ai-agency-evolution` are architecturally distinct (capabilities vs intelligence) but share integration points. These contracts prevent merge conflicts:

### Contract 1: WeightSnapshot Schema (owned by ai-agency)

- **scientific-ml** adds new ML indicators to `INDICATOR_WEIGHTS` with static weight redistribution (maintains `sum == 1.0`)
- **ai-agency** Epic 5 extends `WeightSnapshot` with `WeightType.INDICATOR` and builds the dynamic tuning loop
- **Rule**: scientific-ml does NOT modify `WeightSnapshot` or auto-tune infrastructure

### Contract 2: Agent Context Rendering (additive convention)

- Both PRDs append independent `render_*_context()` functions to `agents/_parsing.py`
- Each function is self-contained, returns `str | None`, called by orchestrator
- **scientific-ml**: `render_macro_context()`, vol forecast fields in `render_volatility_context()`
- **ai-agency**: `render_learned_patterns()` for strategy memory injection

### Contract 3: Volatility Agent Dual Modification (non-conflicting sections)

- **scientific-ml** modifies system prompt content + `DebateDeps` fields (vol forecast context)
- **ai-agency** modifies tool registration + adds `DeskDeps` for interactive mode
- Agent operates in one mode at a time (debate vs interactive) — no runtime conflict

### Dependency Graph (cross-PRD)

```
        scientific-ml                          ai-agency
        =============                          =========

     Epic A: Statistical         ···soft···>  Epic 1: Desk Foundation
     (FRED, GARCH, Markov)       (Vol desk gains garch_forecast tool)
           |
           v
     Epic B: ML Classification   ···soft···>  Epic 5: Weights (P1)
     (regime, clustering)        (more indicators to tune)
           |
           v
     Epic C: Neural Models
     (IV surface, trajectory)

No hard cross-PRD dependencies. All soft deps degrade gracefully to None.
```

## References

- Bollerslev (1986) "Generalized Autoregressive Conditional Heteroskedasticity" — GARCH foundation
- Nelson (1991) "Conditional Heteroskedasticity in Asset Returns" — EGARCH model
- Hamilton (1989) "A New Approach to the Economic Analysis of Nonstationary Time Series" — Markov-switching
- Dickey & Fuller (1979) "Distribution of the Estimators for Autoregressive Time Series" — ADF test
- Hochreiter & Schmetthuber (1997) "Long Short-Term Memory" — LSTM architecture
- Buehler et al. (2019) "Deep Hedging" — neural hedging framework
- `.claude/skills/statsmodels/` — statsmodels API reference and time series patterns
- `.claude/skills/scikit-learn/` — scikit-learn supervised/unsupervised learning reference
- `.claude/skills/pytorch-lightning/` — Lightning module, trainer, and data module templates
- `.claude/skills/fred-economic-data/` — FRED API reference and query patterns
