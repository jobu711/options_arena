---
name: options-arena
description: From-scratch rewrite of Option Alpha as Options Arena with correct American options pricing
status: backlog
created: 2026-02-21T21:42:00Z
updated: 2026-02-22T08:35:20Z
---

# Options Arena — Product Requirements Document

## 1. Executive Summary

Options Arena is a from-scratch rewrite of Option Alpha v3 (`option_alpha3`), an AI-powered American-style options analysis tool. The rewrite fixes a critical pricing error (European BSM applied to American-style options), simplifies the architecture, and cherry-picks proven components from v3 — including mathematically verified technical indicators, the PydanticAI agent pattern, and robust service layer patterns.

The MVP scope is deliberately narrow: **pricing + scan pipeline only**. AI debate, reporting, and web UI are deferred until the core foundation is battle-tested. The project renames from `Option_Alpha` to `options_arena` (PEP 8 compliant), splits the monolithic `analysis/` module into focused `pricing/` and `scoring/` packages, replaces 14 copy-paste indicator blocks with a data-driven registry, and centralizes scattered constants into a single `AppSettings` model.

Key addition: Barone-Adesi-Whaley (BAW) analytical approximation for American-style options pricing, with BSM retained as the European pricing foundation.

## 2. Problem Statement

Four root issues in `option_alpha3` motivate the rewrite:

1. **European pricing applied to American options** — The BSM (Black-Scholes-Merton) model prices European options that cannot be exercised early. All U.S. equity options are American-style, where early exercise has real value — especially for puts and dividend-paying stocks. The tool must use BAW (Barone-Adesi-Whaley) for American options, retaining BSM only as the European pricing foundation.

2. **Monolithic scan pipeline** — The scan function in `cli.py` grew to 430 lines, mixing data fetching, indicator computation, scoring, contract filtering, persistence, and rendering in a single function. This is untestable, unreusable, and impossible to extend cleanly (e.g., adding a web UI would require duplicating the entire function).

3. **Scattered configuration** — Threshold constants (ADX cutoff, delta range, DTE target, min OI, max spread, etc.) are scattered across 10+ files with no single source of truth. Changing a filter requires hunting through multiple modules.

4. **Untyped data structures** — `TickerScore.signals` is stored as `dict[str, float]` instead of a typed model, violating the project's core "no raw dicts" principle. This makes it impossible to validate indicator names at compile time or refactor safely.

Additionally, two web UI attempts (React SPA, then Jinja2+HTMX) were built and rolled back, causing scope creep before the core pricing and pipeline were solid. The rewrite deliberately defers UI work.

## 3. User Stories

As a **solo options trader using this tool for personal analysis**:

- **US-1**: I want to scan a universe of optionable tickers so that I can identify the highest-scoring opportunities across the market.
- **US-2**: I want options priced with a model that accounts for early exercise (American-style) so that put valuations and Greeks are accurate for U.S. equities.
- **US-3**: I want tickers scored and ranked by 18 technical indicators so that I can focus on the most technically favorable setups.
- **US-4**: I want specific contract recommendations with correctly computed Greeks (delta, gamma, theta, vega, rho) so that I can evaluate risk/reward before trading.
- **US-5**: I want to filter the universe by preset (full, S&P 500, ETFs), sector, and minimum score so that scans are focused on my area of interest.
- **US-6**: I want to check service health (yfinance, FRED, Ollama, CBOE) so that I know which data sources are available before running a scan.
- **US-7**: I want universe management commands (refresh, list, stats) so that I can inspect and update the optionable ticker universe.
- **US-8**: I want scan results persisted to SQLite so that I can review historical scans without re-running.

## 4. Functional Requirements

### 4.1 Models (`models/`)

| Requirement | Description |
|-------------|-------------|
| FR-M1 | `ExerciseStyle` enum: `AMERICAN`, `EUROPEAN` — on every `OptionContract` |
| FR-M2 | `PricingModel` enum: `BSM`, `BAW` — on `OptionGreeks` to track which model produced them |
| FR-M3 | `MarketCapTier` enum: `MEGA`, `LARGE`, `MID`, `SMALL`, `MICRO` — replaces raw string "mid_cap" default |
| FR-M3.1 | `DividendSource` enum: `FORWARD`, `TRAILING`, `COMPUTED`, `NONE` — tracks provenance of dividend yield value |
| FR-M4 | `IndicatorSignals` typed model with 18 named `float \| None` fields — replaces `dict[str, float]` on `TickerScore` |
| FR-M5 | `AppSettings` (via `pydantic-settings` `BaseSettings`): root settings class that owns all configuration. Uses `SettingsConfigDict(env_prefix="ARENA_", env_nested_delimiter="__")` so env vars like `ARENA_SCAN__TOP_N=30` override nested fields. `ScanConfig` and `PricingConfig` are nested as plain `BaseModel` submodels (not `BaseSettings`) — this is the pydantic-settings v2 pattern for nested config. No `.env` file loading in MVP (env vars + constructor args only); `.env` support can be added later via `env_file=".env"` without changing the model. Source priority (Context7-verified default): init kwargs > env vars > defaults. See FR-M5.1 for field inventory. |
| FR-M5.1 | **AppSettings field inventory** — `scan: ScanConfig` (nested: `top_n: int = 50`, `min_score: float = 0.0`, `min_price: float = 10.0`, `min_dollar_volume: float = 10_000_000.0`, `ohlcv_min_bars: int = 200`, `adx_trend_threshold: float = 15.0`, `rsi_overbought: float = 70.0`, `rsi_oversold: float = 30.0`), `pricing: PricingConfig` (nested: `risk_free_rate_fallback: float = 0.05`, `delta_primary_min: float = 0.20`, `delta_primary_max: float = 0.50`, `delta_fallback_min: float = 0.10`, `delta_fallback_max: float = 0.80`, `delta_target: float = 0.35`, `dte_min: int = 30`, `dte_max: int = 60`, `min_oi: int = 100`, `min_volume: int = 1`, `max_spread_pct: float = 0.10`, `iv_solver_tol: float = 1e-6`, `iv_solver_max_iter: int = 50`), `service: ServiceConfig` (nested: `yfinance_timeout: float = 15.0`, `fred_timeout: float = 10.0`, `ollama_timeout: float = 60.0`, `rate_limit_rps: float = 2.0`, `max_concurrent_requests: int = 5`, `cache_ttl_market_hours: int = 300`, `cache_ttl_after_hours: int = 3600`, `ollama_host: str = "http://localhost:11434"`, `ollama_model: str = "llama3.1:8b"`). All fields have sensible defaults — `AppSettings()` with no args is a valid production config. |
| FR-M6 | `ScanConfig`, `PricingConfig`, `ServiceConfig` are plain `pydantic.BaseModel` subclasses (NOT `BaseSettings`) — they are nested inside `AppSettings` which is the sole `BaseSettings` subclass. CLI creates `AppSettings()` then passes `settings.scan`, `settings.pricing`, `settings.service` to the modules that need them. Env override examples: `ARENA_SCAN__TOP_N=30`, `ARENA_PRICING__DELTA_TARGET=0.40`, `ARENA_SERVICE__OLLAMA_HOST=http://gpu-server:11434`. |
| FR-M7 | **Dividend yield on `TickerInfo` and `MarketContext`** — fields: `dividend_yield: float` (default `0.0`, never `None`), `dividend_source: DividendSource`, `dividend_rate: float \| None` (forward annual dividend in dollars, audit field), `trailing_dividend_rate: float \| None` (trailing annual dividend in dollars, audit field). Extracted via 3-tier waterfall with cross-validation (see FR-M7 detail below). Pricing engine receives a guaranteed `float` for `dividend_yield` — no `None` handling required. All yfinance yield values are **decimal fractions** (0.005 = 0.5%), not percentages. |
| FR-M7.1 | **Dividend waterfall detail**: (1) `info.get("dividendYield")` — if value is not `None`, accept it (including `0.0` for non-dividend stocks), source = `FORWARD`. (2) `info.get("trailingAnnualDividendYield")` — same `None` guard, source = `TRAILING`. (3) `Ticker.get_dividends(period="1y")` — sum payments / current price, source = `COMPUTED`. (4) `0.0`, source = `NONE`. **Critical**: fall-through condition is `value is None` (key missing or explicit `None`), NOT falsy — `0.0` is valid data for growth stocks and must not trigger fallthrough. Cross-validation: when tier 1 or 2 succeeds AND `dividendRate` is available, compute `rate / price` and warn if divergence > 20% from the yield value (catches stale Yahoo data post-special-dividend). Note: yfinance `Ticker.info` uses **camelCase** keys (`dividendYield`, `trailingAnnualDividendYield`, `dividendRate`, `trailingAnnualDividendRate`); service layer translates to snake_case model fields. |
| FR-M8 | All existing models (OHLCV, Quote, OptionContract, OptionGreeks, ScanRun, TickerScore, HealthStatus, etc.) carried forward with frozen=True where appropriate |

### 4.2 Pricing (`pricing/`)

| Requirement | Description |
|-------------|-------------|
| FR-P1 | `bsm.py`: Cherry-pick European BSM from v3, extend with dividend yield (Merton 1973 continuous dividend model). Uses `scipy.stats.norm.cdf` for N(d1)/N(d2) and `norm.pdf` for vega. BSM IV solver: manual Newton-Raphson loop (analytical vega available as `fprime`, quadratic convergence, ~5-8 iterations typical). Bounded search `[1e-6, 5.0]`, tolerance `PricingConfig.iv_solver_tol`, max iterations `PricingConfig.iv_solver_max_iter`. Uses yfinance `market_iv` as initial guess when available; defaults to 0.30 otherwise. |
| FR-P2 | `american.py`: BAW analytical approximation — `american_price()`, `american_greeks()` (finite-difference bump-and-reprice), `american_iv()`. **IV solver: `scipy.optimize.brentq`** (NOT Newton-Raphson) — BAW has no analytical vega w.r.t. IV, making Newton-Raphson require expensive numerical differentiation (2 BAW evaluations per iteration). `brentq` is bracket-based (guaranteed convergence on monotonic functions), needs no derivative, and naturally fits the IV problem: bracket `[1e-6, 5.0]` is always valid since option price is monotonically increasing in IV. Typical convergence: ~15-40 function evaluations. Uses `xtol=PricingConfig.iv_solver_tol`, `maxiter=PricingConfig.iv_solver_max_iter`. The objective function is `f(sigma) = baw_price(sigma, ...) - market_price`. |
| FR-P3 | `dispatch.py`: Unified routing — `option_price(exercise_style)`, `option_greeks(exercise_style)`, `option_iv(exercise_style)` dispatches to BSM or BAW based on exercise style. IV solver dispatch: BSM uses manual Newton-Raphson (analytical vega), BAW uses `scipy.optimize.brentq` (no analytical vega). |
| FR-P4 | BAW call price = BSM call price for non-dividend-paying stocks (mathematical identity) |
| FR-P5 | BAW put price >= BSM put price always (early exercise premium is non-negative) |

### 4.3 Indicators (`indicators/`)

| Requirement | Description |
|-------------|-------------|
| FR-I1 | Cherry-pick all 6 indicator files from v3 (18 indicators total): oscillators (RSI, Stochastic RSI, Williams %R), trend (ADX, ROC, Supertrend), volatility (BB Width, ATR%, Keltner Width), volume (OBV, A/D, Relative Volume), moving averages (SMA Alignment, VWAP Deviation), options-specific (IV Rank, IV Percentile, Put/Call Ratio, Max Pain Distance) |
| FR-I2 | All indicators: pandas Series in, pandas Series out; NaN for warmup period; InsufficientDataError if input too short; vectorized operations only |

### 4.4 Scoring (`scoring/`)

| Requirement | Description |
|-------------|-------------|
| FR-S1 | `normalization.py`: Percentile-rank normalization with proper tie handling; inversion for indicators where lower = better |
| FR-S2 | `composite.py`: Weighted geometric mean across indicator categories (Oscillators 0.27, Trend 0.20, Volatility 0.15, Volume 0.15, MA 0.10, Options 0.13) |
| FR-S3 | `direction.py`: Direction classification (BULLISH/BEARISH/NEUTRAL) using ADX/RSI/SMA signals with SMA alignment tiebreaker |
| FR-S4 | `contracts.py`: Contract filtering with delta targeting [0.20, 0.50] primary / [0.10, 0.80] fallback, DTE [30, 60], spread check with zero-bid exemption. Computes Greeks for **all** contracts via `pricing/dispatch.py` (BAW for American, BSM for European) — this is the sole source of Greeks, not a fallback (yfinance provides no Greeks). Uses `market_iv` from yfinance as IV solver seed when available; falls back to ATM IV estimate otherwise. Accepts `exercise_style` and `dividend_yield`. |

### 4.5 Scan Pipeline (`scan/`)

| Requirement | Description |
|-------------|-------------|
| FR-SP1 | `CancellationToken` class: instance-scoped cancellation (replaces global `_scan_cancelled` variable) |
| FR-SP2 | `ProgressCallback` protocol: framework-agnostic progress reporting (decoupled from Rich) |
| FR-SP3 | `IndicatorSpec` registry: data-driven list of (name, func, input_shape) entries; `compute_indicators()` generic loop with isolated per-indicator try/except |
| FR-SP4 | `ScanPipeline` class with 4 async phases: (1) Universe fetch + OHLCV, (2) Indicators + scoring + direction, (3) Liquidity pre-filter + options chain + contract selection, (4) Persist to SQLite |
| FR-SP5 | Cancellation checks between phases; ProgressCallback invoked at each phase transition |

### 4.6 Services (`services/`)

| Requirement | Description |
|-------------|-------------|
| FR-SV1 | `market_data.py`: yfinance OHLCV, quotes, ticker info — cherry-pick from v3, add dividend yield extraction per FR-M7.1 waterfall. Implementation: `info.get("dividendYield")` (forward, not falsy — `None` check only) > `info.get("trailingAnnualDividendYield")` (trailing, same guard) > `Ticker.get_dividends(period="1y")` summed / current price (computed) > `0.0`. Returns `(dividend_yield: float, source: DividendSource)` tuple. Also extracts `info.get("dividendRate")` and `info.get("trailingAnnualDividendRate")` as audit fields on `TickerInfo`. Cross-validation: when yield and dollar-rate are both available, warn if `abs(yield - rate/price) / max(yield, 1e-9) > 0.20` (detects stale Yahoo data). All `.info` keys are **camelCase** per yfinance convention. |
| FR-SV2 | `options_data.py`: Option chain fetching with basic liquidity filters (OI >= 100, volume >= 1, reject both-zero bid/ask). yfinance chain columns: `contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`, `change`, `percentChange`, `volume`, `openInterest`, `impliedVolatility`, `inTheMoney`, `contractSize`, `currency`. **No Greeks are returned** — delta/gamma/theta/vega/rho must be computed by `pricing/dispatch.py`. Passes `impliedVolatility` through as `market_iv` on `OptionContract` for downstream use as IV solver seed and cross-check. |
| FR-SV3 | `universe.py`: CBOE optionable ticker universe — **rewrite**: use `pd.read_html()` for S&P 500 constituents (replace regex scraper), proper `MarketCapTier` classification via yfinance `marketCap`. Wikipedia table details: URL `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies` has 2 tables — constituents (table 0, `id="constituents"`) and historical changes (table 1). **Must use `attrs={"id": "constituents"}`** for stable targeting (not positional `[0]` which breaks if Wikipedia adds tables). Columns: `Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Headquarters Location`, `Date added`, `CIK`, `Founded`. We need `Symbol` (ticker) and `GICS Sector` (sector classification). Ticker translation required: Wikipedia uses `.` separator (`BRK.B`), yfinance uses `-` (`BRK-B`). |
| FR-SV4 | `fred.py`: FRED 10yr Treasury for risk-free rate; fallback to `PricingConfig.risk_free_rate_fallback` (default 5%) |
| FR-SV5 | `cache.py`: Two-tier caching (in-memory for quotes/chains, SQLite for OHLCV/fundamentals) with market-hours-aware TTL |
| FR-SV6 | `rate_limiter.py`: Token bucket + asyncio.Semaphore for concurrent request management |
| FR-SV7 | `health.py`: Service health checks with configurable Ollama model ID |

### 4.7 Data Layer (`data/`)

| Requirement | Description |
|-------------|-------------|
| FR-D1 | `database.py`: Async SQLite with WAL mode, sequential migration runner |
| FR-D2 | `repository.py`: Typed CRUD operations returning Pydantic models (updated for `IndicatorSignals` serialization) |
| FR-D3 | `001_initial.sql`: Schema for scan_runs, ticker_scores, ai_theses, watchlists, watchlist_tickers, service_cache, schema_version |

### 4.8 CLI (`cli.py`)

| Requirement | Description |
|-------------|-------------|
| FR-C1 | `scan` command: `--preset full\|sp500\|etfs`, `--sectors`, `--top-n`, `--min-score` — creates ScanConfig, runs ScanPipeline, renders Rich table |
| FR-C2 | `health` command: checks all services, renders status table |
| FR-C3 | `universe` subcommands: `refresh`, `list` (with `--sector`, `--preset`), `stats` |
| FR-C4 | `RichProgressCallback`: maps ProgressCallback protocol to console.print |
| FR-C5 | SIGINT handler: sets CancellationToken for graceful shutdown |
| FR-C6 | Logging: rotating file handler for DEBUG + console handler for user-facing output |

## 5. Non-Functional Requirements

| ID | Requirement | Verification |
|----|-------------|--------------|
| NFR-1 | `mypy --strict` passes on all source code | `uv run mypy src/ --strict` |
| NFR-2 | `ruff` linting + formatting passes with zero violations | `uv run ruff check . --fix && uv run ruff format .` |
| NFR-3 | All tests pass | `uv run pytest tests/ -v` |
| NFR-4 | ~810 tests across all modules | pytest count |
| NFR-5 | Typed Pydantic models at all module boundaries — no `dict[str, Any]`, `dict[str, float]`, or raw dict variants anywhere | Code review + mypy |
| NFR-6 | Financial precision: `Decimal` for prices/P&L/cost basis, `float` for Greeks/IV/indicators, `int` for volume/OI, `datetime.date` for expiration, `datetime.datetime` (UTC) for timestamps | Code review |
| NFR-7 | All external calls use `asyncio.wait_for(timeout=N)` — no unbounded waits | Code review |
| NFR-8 | `asyncio.gather(*tasks, return_exceptions=True)` for batch operations | Code review |
| NFR-9 | `logging` module only in library code — `print()` reserved for `cli.py` | Code review + grep |
| NFR-10 | Custom domain exceptions (never bare `except:`) | Code review |
| NFR-11 | Python 3.13+ modern syntax: `match`, `type X = ...`, `X \| None`, `StrEnum` | ruff UP rules |

## 6. Architecture

### Package Structure

```
src/options_arena/
    __init__.py
    cli.py                  # Thin: arg parsing + Rich rendering (~300 lines)
    models/                 # Data shapes only — no logic, no I/O
    pricing/                # NEW: BAW (American) + BSM (European) + unified dispatch
    indicators/             # Cherry-picked: 18 indicators, pandas in/out
    scoring/                # Extracted from analysis/: normalization, composite, direction, contracts
    scan/                   # NEW: ScanPipeline class with 4 async phases
    services/               # External API access (yfinance, CBOE, FRED, Ollama)
    data/                   # SQLite persistence (async, WAL mode, migrations)
    utils/                  # Exceptions, formatters, helpers
tests/
    unit/{models,pricing,indicators,scoring,scan,services,data,cli}/
data/
    migrations/001_initial.sql
```

### Key Architecture Changes from v3

| Aspect | Old (`option_alpha3`) | New (`options_arena`) |
|--------|----------------------|----------------------|
| Pricing | European BSM only | BAW (American) + BSM (European), unified dispatch |
| Scan pipeline | 430 lines in `cli.py` | `scan/` module with `ScanPipeline` class |
| Indicator loop | 14 copy-paste blocks (168 lines) | Data-driven `IndicatorSpec` registry (~40 lines) |
| Configuration | Constants scattered in 10+ files | `AppSettings` model, single source of truth |
| `TickerScore.signals` | `dict[str, float]` | Typed `IndicatorSignals` model (18 named fields) |
| Exercise style | Not modeled | `ExerciseStyle` enum on `OptionContract` |
| Dividend yield | Not modeled | `float` on `TickerInfo` + `MarketContext`, with `DividendSource` provenance, dollar-rate audit fields, and cross-validation |
| Market cap tier | Raw `str`, defaults to `"mid_cap"` | `MarketCapTier` enum with yfinance classification |
| Pricing model tracking | Not tracked | `PricingModel` enum on `OptionGreeks` |
| Cancellation | Global `_scan_cancelled` variable | `CancellationToken` class (instance-scoped) |
| Progress reporting | CLI-coupled Rich spinner | `ProgressCallback` protocol (framework-agnostic) |
| Module: `analysis/` | Mixed concerns (BSM + scoring + contracts) | Split into `pricing/` + `scoring/` |
| Package name | `Option_Alpha` | `options_arena` (PEP 8 lowercase) |

### Module Boundary Rules

| Module | Responsibility | Can Access | Cannot Access |
|--------|---------------|------------|---------------|
| `models/` | Data shapes only | Nothing | APIs, logic, I/O |
| `pricing/` | Options pricing math | `models/`, scipy | APIs, I/O |
| `indicators/` | Technical indicator math | pandas, numpy | APIs, models, I/O |
| `scoring/` | Normalization, ranking, filtering | `models/`, `pricing/` output | APIs directly |
| `scan/` | Pipeline orchestration | `models/`, `services/`, `scoring/`, `indicators/` | Direct API calls |
| `services/` | External API access | `models/` | Business logic |
| `data/` | SQLite persistence | `models/` | APIs, business logic |
| `cli.py` | Terminal interface | Everything | N/A (top of stack) |

### Cherry-Pick Rationale

**Keep (mathematically verified, architecturally sound):**

| Source | Component | Why Keep |
|--------|-----------|----------|
| `indicators/oscillators.py` | RSI, Stochastic RSI, Williams %R | Mathematically verified, edge cases handled |
| `indicators/trend.py` | ADX, ROC, Supertrend | Complex Wilder's smoothing correct |
| `indicators/volatility.py` | BB Width, ATR%, Keltner Width | Proper ddof=0, EMA seeding |
| `indicators/volume.py` | OBV, A/D, Relative Volume | Vectorized linear regression |
| `indicators/moving_averages.py` | SMA Alignment, VWAP Deviation | Division guards correct |
| `indicators/options_specific.py` | IV Rank, IV Percentile, Put/Call, Max Pain | Domain-correct implementations |
| `analysis/bsm.py` | BSM pricing, Greeks, IV solver | Hull-verified, put-call parity tested. Foundation for BAW. |
| `analysis/normalization.py` | Percentile-rank normalize, invert | Correct tie handling |
| `analysis/scoring.py` | Weighted geometric mean | Math is right |
| `analysis/direction.py` | Direction classification | Sound ADX/RSI/SMA logic |
| `agents/` pattern | PydanticAI Agent[Deps, Output] | Recently migrated, clean pattern |
| `data/database.py` | Migration runner, WAL mode | Robust async SQLite pattern |
| `tests/conftest.py` | 14 domain fixtures | Realistic AAPL test data |

**Discard (architectural debt, incorrect approaches):**

| Source | Why Discard |
|--------|-------------|
| `cli.py` scan function (430 lines) | Rewrite as `scan/` module with proper pipeline |
| `services/universe.py` S&P 500 regex | Replace with `pd.read_html()` |
| `services/universe.py` market cap tier | Wrong default ("mid_cap" for all non-S&P 500) |
| `analysis/contracts.py` spot estimation | Median strike as proxy — pass real spot instead |
| 14 copy-paste indicator blocks | Replace with data-driven registry |
| Global `_scan_cancelled` variable | Replace with `CancellationToken` class |
| Scattered timeout/threshold constants | Centralize in `AppSettings` |

## 7. Success Criteria

| ID | Criterion | How to Verify |
|----|-----------|---------------|
| SC-1 | All 3 verification checks pass (ruff, pytest, mypy) | `uv run ruff check . && uv run pytest tests/ -v && uv run mypy src/ --strict` |
| SC-2 | Scan produces 8+ contract recommendations on S&P 500 preset | `uv run options-arena scan --preset sp500 --top-n 20` |
| SC-3 | BAW pricing matches Hull textbook reference values | Automated tests against known values |
| SC-4 | BAW put >= BSM put for all test cases (early exercise premium validated) | `test_baw_put_geq_bsm_put` parametrized test |
| SC-5 | BAW call = BSM call for non-dividend stocks (mathematical identity) | `test_baw_call_eq_bsm_call_no_dividend` parametrized test |
| SC-6 | ~810 tests across all modules | `uv run pytest tests/ -v --tb=short \| tail -1` |
| SC-7 | Zero `dict[str, Any]` or `dict[str, float]` in function signatures or model fields | `rg "dict\[str," src/` returns zero results |
| SC-8 | All external calls have explicit timeouts | Code review of `asyncio.wait_for` usage |

## 8. Constraints & Assumptions

### Constraints

- **yfinance is the sole free market data source** — rate limited to ~2 req/s. Polygon.io free tier (5 req/min) and Alpha Vantage (25 req/day) are too slow for 5,000+ ticker universe scans.
- **Local-only deployment** — CLI + SQLite, no server, no cloud. Designed for a single user on one machine.
- **Python 3.13+ required** — uses `match` statements, `type` aliases, `X | None` unions, `StrEnum`.
- **Ollama required for AI features** — but AI debate is deferred to v2. MVP runs without Ollama.

### Assumptions

- The CBOE optionable universe CSV remains publicly accessible at its current URL.
- yfinance options chain data includes `impliedVolatility` but **does not return Greeks** (no delta, gamma, theta, vega, rho). All Greeks must be computed locally via `pricing/dispatch.py` (BAW for American, BSM for European). Yahoo's `impliedVolatility` (likely European BSM-based) serves as an initial guess for BSM Newton-Raphson IV convergence and a sanity-check against locally computed BAW IV (brentq is bracket-based and does not need a seed).
- Wikipedia S&P 500 constituent table retains `id="constituents"` HTML attribute and column set (`Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Headquarters Location`, `Date added`, `CIK`, `Founded`). Using `pd.read_html(url, attrs={"id": "constituents"})` targets the table by id rather than positional index, which is resilient to Wikipedia adding/removing other tables on the page. Column name validation at parse time will catch schema drift.
- The user runs scans outside market hours or accepts that in-flight data may be stale during trading.

## 9. Version 2 / Future Considerations

The following are explicitly **deferred** from the MVP and will only be considered after the core pricing + scan pipeline is production-quality:

- **AI Debate System** — `agents/` module with bull, bear, risk PydanticAI agents; `agents/prompts/` with system prompts; debate orchestrator with data-driven fallback; `UnexpectedModelBehavior` error handling
- **Report Generation** — `reporting/` module with formatted output, disclaimers, export formats
- **Watchlist Management** — CRUD for user-defined watchlists, scan filtering by watchlist
- **CLI Commands** — `debate` (single-ticker AI analysis) and `report` (generate formatted output)
- **Web UI** — Only after core is battle-tested. Previous two attempts (React SPA, Jinja2+HTMX) were both rolled back. Any future attempt must build on a stable, decoupled backend.

## 10. Dependencies

### Runtime

| Package | Min Version | Purpose |
|---------|-------------|---------|
| pydantic | 2.12 | Typed data models at all boundaries |
| pandas | 3.0 | Technical indicator computation |
| numpy | 2.4 | Numeric operations for indicators |
| scipy | 1.17 | BSM pricing (`scipy.stats.norm.cdf`, `norm.pdf`), BAW IV solver (`scipy.optimize.brentq`) |
| aiosqlite | 0.22 | Async SQLite persistence |
| yfinance | 1.2 | Market data: OHLCV, options chains, quotes |
| httpx | 0.28 | Async HTTP client for FRED, Ollama, health checks |
| pydantic-ai | 1.62 | Type-safe agent framework (deferred to v2 but installed) |
| ollama | 0.6 | Local LLM server access (deferred to v2 but installed) |
| typer | 0.24 | CLI framework with subcommands |
| rich | 14.3 | Terminal output formatting (tables, colors, progress) |
| pydantic-settings | 2.13 | Centralized `AppSettings` configuration |

### Development

| Package | Min Version | Purpose |
|---------|-------------|---------|
| ruff | 0.15 | Linter + formatter |
| mypy | 1.19 | Type checker (`--strict` mode) |
| pytest | 9.0 | Test framework |
| pytest-asyncio | 1.3 | Async test support |
| pytest-cov | 7.0 | Coverage reporting |
| pandas-stubs | 3.0 | Type stubs for pandas |
| scipy-stubs | 1.17 | Type stubs for scipy |

## 11. Implementation Phases

### Phase 1: Project Bootstrap & Models (~2 sessions)

- Initialize project with `uv init`, configure `pyproject.toml` with all dependencies
- Configure ruff, mypy, pytest in `pyproject.toml`
- Write root `CLAUDE.md` (updated for Options Arena)
- Create `src/options_arena/models/` with all models: `enums.py`, `market_data.py`, `options.py`, `analysis.py`, `scan.py`, `config.py`, `health.py`
- Create `src/options_arena/utils/exceptions.py` — DataFetchError hierarchy
- Write tests for all models (~150 tests)
- Verify: ruff, mypy, pytest

### Phase 2: Pricing Module (~2 sessions)

- Cherry-pick `bsm.py` from v3, extend with dividend yield (Merton 1973)
- Write `american.py` — BAW analytical approximation with finite-difference Greeks and American IV solver
- Write `dispatch.py` — unified routing by `ExerciseStyle`
- Write tests (~100 tests): Hull reference values, BAW=BSM identity (no dividend), BAW put >= BSM put, Greeks ranges, IV round-trip
- Verify

### Phase 3: Indicators (Cherry-Pick) (~1 session)

- Copy all 6 indicator files from v3 (mathematically verified)
- Update imports to `options_arena.*`
- Copy and update indicator tests from v3
- Verify

### Phase 4: Scoring Module (~1 session)

- Cherry-pick normalization, composite, direction from v3
- Rewrite `contracts.py`: use `pricing/dispatch.py`, accept `exercise_style` + `dividend_yield`, remove spot estimation hack, accept `ScanConfig` for thresholds
- Write/adapt tests (~80 tests)
- Verify

### Phase 5: Services Layer (~2 sessions)

- Cherry-pick with improvements: cache, rate limiter, helpers, market data (+dividend_yield), options data, FRED (+PricingConfig fallback), health (+configurable model ID)
- Rewrite `universe.py`: `pd.read_html()` for S&P 500, proper `MarketCapTier` classification
- Write/adapt tests (~100 tests)
- Verify

### Phase 6: Data Layer (~1 session)

- Cherry-pick `database.py` (async SQLite, WAL, migration runner)
- Update `repository.py` for new models (IndicatorSignals serialization)
- Write `001_initial.sql` migration
- Write tests (~30 tests)
- Verify

### Phase 7: Scan Pipeline (~2 sessions)

- Write `progress.py`: CancellationToken + ProgressCallback protocol
- Write `indicators.py`: IndicatorSpec registry + compute_indicators()
- Write `models.py`: UniverseResult, ScoringResult, OptionsResult, ScanResult
- Write `pipeline.py`: ScanPipeline with 4 async phases
- Write tests (~80 tests): registry, dispatch, failure isolation, pipeline phases, cancellation, progress ordering
- Verify

### Phase 8: CLI (~1 session)

- Write thin `cli.py`: scan, health, universe subcommands
- RichProgressCallback, SIGINT handler, logging configuration
- Write CLI tests (~20 tests)
- End-to-end verification: `uv run options-arena scan --preset sp500`
- Verify all three checks pass

### Estimated Test Counts

| Module | Tests |
|--------|-------|
| models/ | ~150 |
| pricing/ | ~100 |
| indicators/ | ~250 (cherry-picked from v3) |
| scoring/ | ~80 |
| services/ | ~100 |
| data/ | ~30 |
| scan/ | ~80 |
| cli/ | ~20 |
| **Total MVP** | **~810** |
