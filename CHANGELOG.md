# Changelog

All notable changes to Options Arena are documented in this file.

## [2.10.0] — 2026-03-17

### Release Hardening
- Full audit battery: 7 agents + math audit (54 formulas verified correct)
- Resolved all P1 findings: CVE remediation, path traversal guard, migration crash recovery, SQL guard
- Documented P2-P4 findings in `docs/known-limitations-v2.10.0.md`
- Version aligned across all 6 locations (pyproject.toml, package.json, progress.md, api/app.py, technical-reference)
- Dynamic API versioning via `importlib.metadata` (no more hardcoded version in FastAPI)
- Cleaned stale worktrees, archived completed epics, updated progress tracking

### Test Verification
- 26,516 Python tests passing (27K parametrized), 5 pre-existing failures documented
- 33 migrations verified from scratch on fresh database
- Optional `[ml]` extra verified (arch 8.0.0 + statsmodels 0.14.6)

## [2.8.0] — 2026-03-16

### Dead Code Audit
- Removed ~1,720 lines of dead code across 17 modules (119 files, 4,933 deletions)
- Deleted legacy bull/bear agents — replaced by 6-agent protocol (Trend, Volatility, Flow, Fundamental, Risk, Contrarian)
- Modernized `DebatePhase` enum to match 6-agent pipeline
- Wired 8 previously unused indicators into scan pipeline (hurst, skew_25d, smile_curvature, vol_forecast_garch, regime_transition_prob, chain_spread_pct, chain_oi_depth, multi_tf_alignment)
- Cleaned dead repository methods, config fields, re-exports

### Statistical ML Pipeline (`[ml]` optional extra)
- GARCH(1,1) volatility forecasting with ADF stationarity gate (Bollerslev 1986)
- Markov-switching regime detection — 3 regimes: low_vol/normal/high_vol (Hamilton 1989)
- FRED macro pipeline: GDP, unemployment, CPI, yield curve with rules-based regime classification
- Hurst exponent via rescaled range R/S analysis (Mandelbrot & Wallis 1969)
- Yang-Zhang historical volatility estimator (Yang & Zhang 2000)
- Scan pipeline integration: ML indicators in Phase 2, results in agent prompts

### Competitive Audit Features
- Composite valuation framework: DCF, DDM, residual income, Graham number
- Portfolio correlation matrix with cross-asset analysis
- Vol-regime position sizing (fractional Kelly with regime adjustment)
- Deterministic constraint pre-check for debate pipeline
- Agent constraints system for structured output validation

### Neural Models (`[neural]` optional extra)
- Neural IV surface MLP model (log-moneyness, DTE → IV)
- LSTM trajectory probabilistic price path forecasting
- ML regime classifier with offline training script
- Flow anomaly detection via Isolation Forest

### Complexity Reduction
- Removed OpenBB service, models, and integration points
- Removed dead indicator functions and pipeline references
- Consolidated redundant HV estimators (Yang-Zhang subsumes Parkinson, Rogers-Satchell)

## [2.5.0] — 2026-03-14

### DevOps & Audit Infrastructure
- 7 specialized audit agents: security, bug, code, architect, db, dep, oa-python
- `/full-audit` parallel orchestration (all 7 agents in one command)
- `/fix-loop` iterative audit-fix-verify with user approval
- `/release-prep` 6-phase release workflow
- `/compound` knowledge capture to `docs/solutions/`
- Scope boundary hardening across all modules

### Web UI (Vue 3 SPA)
- FastAPI REST + WebSocket backend with app factory pattern
- Vue 3 SPA: Dashboard, Scan, Scan Results, Debate, Universe, Health pages
- Real-time scan/debate progress via WebSocket
- S&P 500 heatmap with client-side treemap layout
- PrimeVue Aura dark theme with financial accent colors
- Score history charts, trending tickers, scan deltas
- Backtesting analytics: equity curve, drawdown, sector/DTE/IV performance

### Analytics & Outcomes
- Contract outcome tracking at T+1/T+5/T+10/T+20 holding periods
- 16 analytics API endpoints with 7 backtesting queries
- Win rate, score calibration, delta performance, indicator attribution
- CLI `outcomes` subcommand (collect, summary, backtest, equity-curve)

### Options Chain Abstraction
- ChainProvider protocol: CBOE (primary) + yfinance (fallback)
- Three-tier Greeks: CBOE native → local BAW/BSM → exclude contract
- Liquidity scoring: chain spread % (70%) + OI depth (30%)

### Scan Pipeline Decomposition
- Thin orchestrator delegating to 4 phase modules
- Auto-index: Phase 1 detects missing ticker metadata, indexes inline
- Metadata cache: SQLite `ticker_metadata` table with 30-day TTL

## [2.0.0] — 2026-03-10

### Core Engine
- Black-Scholes-Merton European pricing with continuous dividend yield (Merton 1973)
- Barone-Adesi-Whaley American option pricing with analytical approximation (1987)
- 18 technical indicators across 6 categories (oscillators, trend, volatility, volume, moving averages, options)
- Percentile-rank normalization with weighted geometric mean composite scoring
- Direction classification (ADX gate, RSI momentum, SMA alignment, supertrend, ROC)
- Contract selection: delta targeting (0.20-0.50), DTE filtering (30-365d), liquidity scoring

### AI Debate System
- PydanticAI agent framework with Groq (Llama 3.3 70B) + Anthropic (Claude) providers
- 6-agent debate: Trend, Volatility, Flow, Fundamental, Risk, Contrarian
- Log-odds confidence pooling (Bordley 1982), Shannon entropy diversity
- Data-driven fallback when LLM provider unreachable
- Batch debate with per-ticker error isolation

### CLI
- `scan` (--preset, --sector, --top-n), `debate` (--batch, --export md), `health`, `universe`, `serve`, `outcomes`
- Rich terminal output with colored tables, progress bars, agent panels
- Dual-handler logging (Rich stderr + rotating file)

### Data Layer
- SQLite with WAL mode, 33 sequential migrations
- Repository pattern with mixin decomposition (5 domain mixins)
- Typed boundaries: every method returns Pydantic models

### External Services
- Yahoo Finance: OHLCV, quotes, ticker info, option chains
- FRED: risk-free rate + macro series with fallback defaults
- CBOE: optionable universe + option chains (primary provider)
- S&P 500 constituents from Wikipedia with GICS sector mapping
