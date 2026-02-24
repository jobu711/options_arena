# System Patterns

## Architecture Style

**Layered architecture with strict module boundaries.** Each layer has a single responsibility and communicates through typed Pydantic v2 models. No layer may bypass its designated role.

## Module Boundary Rules

| Module | Responsibility | Can Access | Cannot Access |
|--------|---------------|------------|---------------|
| `models/` | Data shapes only | Nothing | APIs, logic, I/O |
| `services/` | External API access | `models/` | Business logic |
| `indicators/` | Pure math (pandas in/out) | pandas, numpy | APIs, models, I/O |
| `data/` | SQLite persistence | `models/` | APIs, business logic |
| `pricing/` | BSM + BAW pricing, Greeks, IV | `models/`, `scipy` | APIs, pandas, services |
| `scoring/` | Normalization, composite scoring, direction, contract selection | `models/`, `pricing/dispatch` | APIs, services, `pricing/bsm`, `pricing/american` directly |
| `scan/` | Pipeline orchestration (4 async phases) | `models/`, `services/`, `scoring/`, `indicators/`, `data/`, `asyncio`, `logging` | `pricing/` directly, `httpx`, `yfinance`, `print()` |
| `analysis/` | Scoring, signals | `models/`, `services/` output, indicator output, `pricing/` | APIs directly |
| `agents/` | PydanticAI debate orchestration (Phase 9) | `models/`, `data/repository`, `pydantic_ai` | Other agents, `services/`, indicators |
| `reporting/` | Output generation | `models/` | APIs, data fetching |
| `cli.py` | Terminal interface | Everything | N/A (top of stack) |

## Key Design Patterns

### Repository Pattern (Persistence)
- `Database` handles connection lifecycle, WAL mode, migrations
- `Repository` provides typed CRUD operations (`save_scan_run()`, `get_latest_scan()`, etc.)
- All queries return typed models, never raw dicts

### Immutable Models
- `frozen=True` on data models representing snapshots (quotes, contracts, verdicts)
- Computed fields (`mid`, `spread`, `dte`) derived at access time

### Validation Patterns (Enforced in Phase 1 Models)
- **UTC enforcement**: All `datetime` fields use `field_validator` that rejects naive (`tzinfo is None`) and non-UTC (`utcoffset() != timedelta(0)`) values
- **Confidence bounds**: Every `confidence: float` field validated to `[0.0, 1.0]` via `field_validator`
- **StrEnum for categories**: All categorical string fields (macd_signal, preset, etc.) use `StrEnum` subclasses — never raw `str`
- **Domain constraints**: `market_iv >= 0`, `quantity >= 1`, `legs` non-empty — validated at model construction

### NaN/Inf Defense Pattern (Added Post-MVP)
- **`math.isfinite()` at model boundaries**: Every Pydantic validator on numeric fields that use
  `v < 0` or range checks must ALSO check `math.isfinite(v)` first, because NaN comparisons
  always return False (NaN silently passes `v >= 0`).
- **`math.isfinite()` at computation entry**: Pricing functions (`bsm_price`, `american_price`)
  and scoring functions (`composite_score`, `determine_direction`) guard non-finite inputs at
  entry before any arithmetic.
- **NaN for undefined ratios**: Division-by-zero returns `float("nan")` (not `0.0`) when the
  result is mathematically undefined (e.g., put/call ratio with zero call volume).
- **Display guards**: CLI rendering checks `math.isfinite()` before formatting numeric values,
  falling back to `"--"` for non-finite values.

### Re-export Pattern
- Each package `__init__.py` re-exports its public API
- Consumers import from the package, not submodules: `from options_arena.models import OptionContract`

### Configuration Pattern (Options Arena — Planned, Context7-Verified)
- **Single `BaseSettings` root**: `AppSettings(BaseSettings)` is the only `BaseSettings` subclass
- **Nested `BaseModel` submodels**: `ScanConfig`, `PricingConfig`, `ServiceConfig` are plain `BaseModel` — NOT `BaseSettings`
- **`SettingsConfigDict`**: `env_prefix="ARENA_"`, `env_nested_delimiter="__"` — so `ARENA_SCAN__TOP_N=30` maps to `settings.scan.top_n`
- **Source priority** (pydantic-settings v2 default): init kwargs > env vars > field defaults
- **No `.env` file in MVP**: env vars + constructor args only; add `env_file=".env"` later without model changes
- **Dependency injection**: `cli.py` creates `AppSettings()`, passes `settings.scan` to scan pipeline, `settings.pricing` to pricing module, `settings.service` to services. Modules accept their config slice, not the full `AppSettings`.
- **All defaults are production-ready**: `AppSettings()` with no args is a valid config

### Service Layer Patterns (Implemented in Phase 5)
- **Class-based DI**: Each service receives `config`, `cache`, `limiter` via `__init__`. Explicit `close()` for cleanup.
- **Cache-first**: check cache → fetch if miss → store → return
- **Shared httpx client**: one `AsyncClient` per service instance in `__init__`, closed via `await client.aclose()`
- **Retry with backoff**: `fetch_with_retry()` accepts zero-arg async factory (not coroutine), exponential backoff (1s→16s, max 5 retries)
- **yfinance wrapping**: `_yf_call(fn, *args)` — `asyncio.to_thread(fn, *args)` + `asyncio.wait_for(timeout)` + error mapping. CRITICAL: pass callable + args separately, NOT `to_thread(fn())`.
- **Two-tier caching**: `ServiceCache` — in-memory LRU (dict + access-time tracking, configurable max 1000) for short-lived data (quotes, chains); SQLite WAL for persistent (OHLCV, fundamentals). 8 named TTL constants.
- **Market-hours-aware TTL**: `is_market_hours()` via `zoneinfo.ZoneInfo("America/New_York")`, 9:30-16:00 ET Mon-Fri. Shorter TTLs during market hours, longer after close.
- **Rate limiting**: `RateLimiter` with token bucket (`time.monotonic()`, NOT `time.time()`) + `asyncio.Semaphore`. `release()` is synchronous. Context manager: `async with limiter:`.
- **Typed returns**: all service methods return Pydantic models, never raw dicts or DataFrames
- **Batch isolation**: `asyncio.gather(*tasks, return_exceptions=True)` with `zip(tickers, results, strict=True)`. One failed ticker never crashes a batch.
- **FRED never raises**: `FredService.fetch_risk_free_rate()` always returns float, falls back to `PricingConfig.risk_free_rate_fallback` on any error.

### PydanticAI Agent Pattern (Implemented in Phase 9)
- Module-level `Agent[Deps, OutputType]` instances (bull, bear, risk) — no classes
- `model=None` at init, actual `OllamaModel` passed at `agent.run(model=...)` time (enables `TestModel` in tests)
- `@dataclass` deps (`DebateDeps`) injected at runtime via `agent.run(..., deps=deps, model=model)`
- `output_type=PydanticModel` enforces structured JSON output from LLM
- `retries=2` for automatic retry on validation failure with schema hints
- `model_settings=ModelSettings(extra_body={"num_ctx": 8192})` for Ollama context window
- `@agent.output_validator` rejects `<think>` tag remnants, triggers `ModelRetry`
- `@agent.system_prompt` decorator for static prompts (bull), `dynamic=True` for runtime-dependent prompts (bear, risk)
- `_resolve_host()` resolves host via explicit config > `OLLAMA_HOST` env var > default localhost
- Sequential execution: Bull → Bear → Risk (Ollama is single-threaded on CPU)
- Orchestrator never raises: catches `UnexpectedModelBehavior`, timeout, connection errors → data-driven fallback
- Token accumulation via `RunUsage` addition: `bull_usage + bear_usage + risk_usage`
- `DebateResult` dataclass (not Pydantic) because `RunUsage` is a plain dataclass

### Debate Orchestration Flow (Implemented in Phase 9)
```
1. CLI provides: TickerScore, OptionContract[], Quote, TickerInfo, DebateConfig
2. build_market_context() → MarketContext (flat model for agent consumption)
3. build_ollama_model() → OllamaModel (host resolution: config > env > default)
4. Bull agent: argue bullish case → AgentResponse
5. Bear agent: receive bull's argument + context → AgentResponse
6. Risk agent: receive both arguments + context → TradeThesis
7. Accumulate RunUsage, persist to ai_theses table
8. Return DebateResult (is_fallback=False)
On any error: return data-driven fallback (is_fallback=True, confidence=0.3)
```

### Error Handling
- Domain-specific exception hierarchy rooted at `DataFetchError`
- Specific types: `TickerNotFoundError`, `InsufficientDataError`, `DataSourceUnavailableError`, `RateLimitExceededError`
- Never bare `except:` — always specific types
- `logging` module only — never `print()` in library code

## Data Flow Patterns

### Financial Precision
- **Prices, P&L, cost basis**: `Decimal` (constructed from strings: `Decimal("1.05")`)
- **Greeks, IV, indicators**: `float` (speed over precision)
- **Volume, open interest**: `int` (always whole numbers)
- **Dates**: `datetime.date` for expiration, `datetime.datetime` with UTC for timestamps

### Async Convention
- Data fetching, debate loop, and agent calls are all `async`
- One client type per module (no sync/async mixing)
- `asyncio.wait_for(coro, timeout=N)` on every external call
- `asyncio.gather(*tasks, return_exceptions=True)` for batch operations

### Analysis & Scoring Patterns
- **BSM pricing** (Implemented): `bsm.py` — Merton 1973 with continuous dividend yield `q`. `scipy.stats.norm.cdf` for N(d1)/N(d2), `norm.pdf` for vega. BSM IV solver: Newton-Raphson (analytical vega as fprime, quadratic convergence, ~5-8 iterations). Bounded search [1e-6, 5.0]. Bracket pre-check rejects out-of-range market prices before iteration.
- **BAW pricing** (Implemented): `american.py` — Barone-Adesi-Whaley 1987 analytical approximation. Early exercise premium added to BSM base price. Critical price found via Newton-Raphson on boundary condition. BAW IV solver: `scipy.optimize.brentq` (NOT Newton-Raphson — BAW has no analytical vega w.r.t. IV). Bracket [1e-6, 5.0], ~15-40 function evaluations typical.
- **BAW Greeks** (Implemented): finite-difference bump-and-reprice (11 BAW evaluations per Greeks call). Bump sizes: `dS=1%`, `dT=1/365`, `dSigma=0.001`, `dR=0.001`. Sigma clamp prevents negative sigma in vega bump.
- **Dispatch** (Implemented): `dispatch.py` — `ExerciseStyle`-based routing via `match`. AMERICAN→BAW, EUROPEAN→BSM. Three functions: `option_price`, `option_greeks`, `option_iv`.
- **Shared helpers** (Implemented): `_common.py` — `validate_positive_inputs(S, K)`, `intrinsic_value`, `is_itm`, `boundary_greeks`. Input validation at all entry points.
- **Percentile-rank normalization** (Implemented): Raw indicator values ranked across universe, scaled 0-100. `math.isfinite()` guards reject NaN and ±inf.
- **Weighted geometric mean** (Implemented): Category weights (trend 0.20, momentum 0.20, volatility 0.15, volume 0.15, options 0.30) combined via geometric mean
- **Direction signal** (Implemented): 6-category aggregation of indicator signals into bullish/bearish/neutral score, with SMA alignment tiebreaker when scores tie
- **Contract ranking** (Implemented): Delta quality (distance from 0.35), spread quality (tighter = better), volume quality (higher OI = better)
- **No direct API calls**: analysis/ receives pre-fetched data from services/, never fetches its own

### S&P 500 Universe Fetch (Implemented in Phase 5)
- **Source**: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
- **Page structure**: 2 tables — constituents (`id="constituents"`, table 0) and historical changes (table 1)
- **Call**: `pd.read_html(url, attrs={"id": "constituents"})` — targets by HTML id, not positional index
- **Columns returned**: `Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Headquarters Location`, `Date added`, `CIK`, `Founded`
- **Columns needed**: `Symbol` (ticker), `GICS Sector` (sector classification)
- **Ticker translation**: Wikipedia uses `.` separator (`BRK.B`), yfinance uses `-` (`BRK-B`) — `symbol.replace(".", "-")`
- **Validation**: check `{"Symbol", "GICS Sector"} <= set(df.columns)` at parse time to catch schema drift
- **Caching**: cache result to SQLite; S&P 500 membership changes ~25 times/year, day-old data is acceptable

### Scan Pipeline Data Flow
```
Phase 1: Universe (~5,286 CBOE tickers) → OHLCV fetch → ~5,100+ with data
Phase 2: Indicators (isolated per-indicator try/except) → normalize → score → direction
Phase 3: Liquidity pre-filter ($10M avg dollar volume, $10 min price)
        → Top 50 by score → fetch option chains → filter contracts → recommend
Phase 4: Persist results to SQLite
```

### Dividend Yield Waterfall (Implemented in Phase 5)
- **Purpose**: BAW American options pricing requires continuous dividend yield `q` as input
- **Problem**: yfinance `Ticker.info` uses camelCase keys (`dividendYield`, not `dividend_yield`) and returns `None` or omits the key entirely for ~40% of optionable tickers (growth stocks, biotech, many ETFs)
- **yfinance fields confirmed** (Context7-verified):
  - `info["dividendYield"]` — forward annual yield as **decimal fraction** (0.005 = 0.5%), `float | None`
  - `info["trailingAnnualDividendYield"]` — trailing 12-month yield as decimal fraction, `float | None`
  - `info["dividendRate"]` — forward annual dividend in **dollars**, `float | None` (audit/cross-validation)
  - `info["trailingAnnualDividendRate"]` — trailing annual dividend in dollars, `float | None` (audit)
  - `Ticker.get_dividends(period="1y")` — `pd.Series` of per-payment dollar amounts, date-indexed
- **Solution**: 3-tier waterfall in service layer, guaranteed `float` output (never `None`):
  1. `info.get("dividendYield")` — if not `None`, accept (including `0.0` for growth stocks), source = `FORWARD`
  2. `info.get("trailingAnnualDividendYield")` — same `None` guard, source = `TRAILING`
  3. `Ticker.get_dividends(period="1y")` — sum payments / current price, source = `COMPUTED`
  4. `0.0` — source = `NONE`
- **Critical**: fall-through condition is `value is None`, NOT falsy — `0.0` is valid data for non-dividend stocks
- **Provenance**: `DividendSource` enum (`FORWARD`, `TRAILING`, `COMPUTED`, `NONE`) on `TickerInfo` tracks which tier produced the value
- **Audit fields**: `dividend_rate: float | None` and `trailing_dividend_rate: float | None` on `TickerInfo` for downstream cross-validation
- **Cross-validation**: when yield and dollar-rate are both available, warn if `abs(yield - rate/price) / max(yield, 1e-9) > 0.20` (catches stale Yahoo data post-special-dividend)

### yfinance Option Chain Columns (Context7-Verified)
- `option_chain(date)` returns `.calls` and `.puts` DataFrames with exactly these columns:
  `contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`, `change`,
  `percentChange`, `volume`, `openInterest`, `impliedVolatility`, `inTheMoney`,
  `contractSize`, `currency`
- **No Greeks**: delta, gamma, theta, vega, rho are NOT provided by yfinance — never have been
- **`impliedVolatility`**: Yahoo-computed IV (likely European BSM-based). Useful as:
  - Seed value for IV solver convergence (Newton-Raphson initial guess for BSM; not used by brentq which is bracket-based)
  - Sanity-check against locally computed BAW IV (flag divergence > 5%)
  - Quick-filter proxy before running full BAW computation on every contract
- **Implication**: `pricing/dispatch.py` is the sole source of Greeks for the entire pipeline

### Filter Architecture (Service vs Analysis Layer)
- **Service layer** (`options_data.py`): Basic liquidity filters — OI >= 100, volume >= 1.
  Rejects contracts where both bid AND ask are zero (truly dead). No spread or delta filtering.
- **Analysis layer** (`contracts.py`): OI/volume (defense in depth), spread filtering with
  zero-bid exemption (bid=0/ask>0 skips spread check), delta targeting (0.20-0.50) with
  closest-to-target fallback (0.10-0.80). Greeks computed for all contracts via
  `pricing/dispatch.py` (BAW for American, BSM for European) — yfinance provides no Greeks,
  so local computation is the sole source. Uses yfinance `impliedVolatility` as IV solver seed.
- This separation ensures zero-bid contracts reach the analysis layer for pricing computation.

### Indicator Convention
- Input: `pd.Series` or `pd.DataFrame`
- Output: `pd.Series` or `pd.DataFrame`
- Warmup period returns `NaN` — never fill, backfill, or drop
- `InsufficientDataError` if input too short
- Vectorized operations only (no Python loops for math)

### Scoring Pipeline (Implemented in Phase 4)
- **Normalization**: `percentile_rank_normalize()` converts raw indicator values to 0–100 percentile ranks with tie averaging. Single ticker → 50.0. `invert_indicators()` flips bb_width, atr_pct, relative_volume, keltner_width (higher raw = worse). `get_active_indicators()` detects universally-missing indicators for weight renormalization.
- **Composite scoring**: `composite_score()` computes weighted geometric mean: `exp(sum(w_i * ln(max(x_i, 1.0))) / sum(w_i))`. 18 indicators, 6 categories, weights sum to 1.0. Floor value 1.0 prevents log(0). Output clamped [0, 100].
- **Direction classification**: `determine_direction(adx, rsi, sma_alignment, config)` returns `SignalDirection`. ADX gate (< 15 → NEUTRAL), RSI scoring (strong +=2, mild +=1), SMA scoring (+=1 for >0.5 or <-0.5), SMA tiebreaker.
- **Contract selection**: `recommend_contracts()` pipeline: `filter_contracts()` (direction, OI, volume, spread ≤30% with zero-bid exemption) → `select_expiration()` (DTE [30,365], closest to midpoint 197.5) → `compute_greeks()` (via `pricing/dispatch.py`, IV re-solve for suspect market_iv with `math.isfinite` guard) → `select_by_delta()` (primary [0.20,0.50] + fallback [0.10,0.80], target 0.35).
- **Critical contract**: `score_universe()` returns percentile-ranked signals on `TickerScore.signals`. `determine_direction()` requires **raw** indicator values — callers must retain raw `IndicatorSignals` separately.
- All thresholds from `ScanConfig` (direction) / `PricingConfig` (contracts) — no hardcoded magic numbers.
- `scoring/` imports from `pricing/dispatch` only — never `pricing/bsm` or `pricing/american` directly.

## Per-Module CLAUDE.md Pattern

Every major module has a `CLAUDE.md` file that specifies:
- Module purpose and file listing
- Required patterns and conventions
- Common mistakes to avoid
- Integration rules with other modules

These files must be read before modifying any code in that module.
