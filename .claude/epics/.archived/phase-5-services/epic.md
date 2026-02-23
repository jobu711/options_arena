---
name: phase-5-services
status: completed
created: 2026-02-22T08:50:13Z
updated: 2026-02-23T17:45:27Z
completed: 2026-02-23T17:45:27Z
progress: 100%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: https://github.com/jobu711/options_arena/issues/29
---

# Epic 5: Services Layer — Complete Rewrite

## Overview

Build the entire `services/` package from scratch. This is the **sole layer** that
touches external APIs (yfinance, FRED, CBOE, Wikipedia, Ollama). Every function returns
a typed Pydantic model — never a raw dict, DataFrame, or JSON blob. All external I/O
is async via `asyncio.to_thread()` (for sync yfinance) or native `httpx.AsyncClient`
(for HTTP APIs).

**Approach**: Complete rewrite — no cherry-picking from Option_Alpha v3. The v3 services
layer has architectural debt (mixed sync/async, raw dict returns, incorrect Greek
assumptions, regex scraping). This rewrite applies lessons learned from 4 completed phases
and designs the services layer to cleanly integrate with the typed model layer (Phase 1),
pricing engine (Phase 2), indicator pipeline (Phase 3), and scoring module (Phase 4).

**PRD Requirements**: FR-SV1, FR-SV2, FR-SV3, FR-SV4, FR-SV5, FR-SV6, FR-SV7,
FR-M7.1 (implementation)

---

## Architecture

### Design Principles

1. **Typed boundary**: Every public function returns a Pydantic model from `models/`.
   No `dict`, `DataFrame`, `Any`, or `tuple` return types cross the package boundary.

2. **Async-first**: All public functions are `async`. Sync yfinance calls are wrapped
   in `asyncio.to_thread()` with `asyncio.wait_for(timeout=N)`. No unbounded waits.

3. **Fail-safe isolation**: Batch operations use `asyncio.gather(*tasks, return_exceptions=True)`.
   One failed ticker never crashes a 500-ticker scan.

4. **Config-driven thresholds**: Every timeout, rate limit, TTL, and filter threshold
   comes from `ServiceConfig` or `PricingConfig` — zero magic numbers.

5. **Provenance tracking**: Dividend yield carries `DividendSource` enum. Market cap
   carries `MarketCapTier` enum. `HealthStatus` records latency and error details.

6. **Cache-first**: `check cache → fetch if miss → store → return`. Two tiers:
   in-memory (LRU, TTL) for hot data (quotes, chains), SQLite for cold data (OHLCV,
   fundamentals). Market-hours-aware TTL selection.

### Module Dependency Graph

```
                    ┌──────────────┐
                    │ ServiceConfig │  (from models/config.py)
                    └──────┬───────┘
                           │ injected into all services
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌──────────────┐ ┌──────────┐
    │ rate_limiter │ │    cache     │ │ helpers  │
    │   .py       │ │    .py       │ │   .py    │
    └──────┬──────┘ └──────┬───────┘ └────┬─────┘
           │               │              │
           │   ┌───────────┴──────────────┘
           │   │   (shared infrastructure)
           ▼   ▼
    ┌──────────────┐  ┌───────────────┐  ┌──────────┐  ┌────────────┐
    │ market_data  │  │ options_data  │  │  fred    │  │  universe  │
    │    .py       │  │     .py       │  │   .py    │  │    .py     │
    └──────────────┘  └───────────────┘  └──────────┘  └────────────┘
           │                │                 │               │
           └────────────────┴─────────────────┴───────────────┘
                                    │
                              ┌─────▼─────┐
                              │  health   │
                              │   .py     │
                              └───────────┘
```

### Class-Based Services (Stateful Pattern)

Services hold shared state: rate limiters, caches, httpx clients. Each service is a
class with constructor injection, async methods, and an explicit `close()` for cleanup.

```python
class MarketDataService:
    def __init__(
        self,
        config: ServiceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None: ...

    async def fetch_ohlcv(self, ticker: str, period: str = "1y") -> list[OHLCV]: ...
    async def fetch_quote(self, ticker: str) -> Quote: ...
    async def fetch_ticker_info(self, ticker: str) -> TickerInfo: ...
    async def close(self) -> None: ...
```

This matches the project pattern: stateful objects use classes (like PydanticAI `Agent`),
stateless computations use module-level functions (like `pricing/dispatch.py`).

### Error Strategy

| Error Source | Handling |
|---|---|
| Ticker not found | Raise `TickerNotFoundError(ticker)` |
| yfinance returns empty DataFrame | Raise `InsufficientDataError(ticker, reason)` |
| yfinance timeout / network error | Raise `DataSourceUnavailableError(source, detail)` |
| FRED / CBOE unreachable | `DataSourceUnavailableError` with fallback value |
| Rate limit exceeded | `RateLimitExceededError` after max retries exhausted |
| Wikipedia schema drift | `InsufficientDataError` with column mismatch detail |
| Broad yfinance `Exception` | Catch, log, re-raise as `DataSourceUnavailableError` |

All exceptions from `utils/exceptions.py`. Never bare `except:`. Log via `logging`
module — never `print()`.

---

## Context7 Verification Log

All external library interfaces verified before design. Findings:

### yfinance (Context7: `/websites/ranaroussi_github_io`, score 87.5)

- **`Ticker.get_info()`** → `dict[str, Any]`. Keys are **camelCase**:
  `dividendYield`, `trailingAnnualDividendYield`, `dividendRate`,
  `trailingAnnualDividendRate`, `marketCap`, `sector`, `shortName`.
  Values can be `None` or missing.

- **`Ticker.get_dividends(period="1y")`** → `pd.Series` with date index,
  float values (dollar amounts per payment).

- **`Ticker.option_chain(date)`** → object with `.calls` and `.puts` DataFrames.
  Columns (Context7-verified + PRD-verified):
  `contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`,
  `change`, `percentChange`, `volume`, `openInterest`, `impliedVolatility`,
  `inTheMoney`, `contractSize`, `currency`.
  **No Greeks** (no delta/gamma/theta/vega/rho).

- **`Ticker.options`** → `tuple[str, ...]` of available expiration dates as strings.

- **`yf.download(tickers, period, interval)`** → DataFrame with OHLCV columns.
  Multi-ticker download returns MultiIndex columns.

### httpx (Context7: `/encode/httpx`, score 90.9)

- **Fine-grained timeout**: `httpx.Timeout(10.0, connect=5.0, read=30.0, write=10.0, pool=5.0)`
- **Connection limits**: `httpx.Limits(max_connections=10, max_keepalive_connections=5)`
- **Async client**: `async with httpx.AsyncClient(timeout=timeout) as client: ...`
- **Transport-level retries**: `httpx.AsyncHTTPTransport(retries=1)` — connection retries only,
  not application-level retry. We need our own retry-with-backoff for HTTP errors.
- **Concurrent requests**: `asyncio.gather(*[client.get(url) for url in urls])`

### pandas (Context7: `/websites/pandas_pydata`, score 91.5)

- **`pd.read_html(url, attrs={"id": "table"})`** → `list[DataFrame]`.
  The `attrs` parameter accepts a dict of HTML element attributes for stable table
  targeting. This is safer than positional `[0]` which breaks if page structure changes.
- **Confirmed**: `attrs={"id": "constituents"}` will target the S&P 500 table by its
  HTML `id` attribute.

---

## Module Specifications

### 1. `helpers.py` — Retry & Type Conversion Utilities

**Purpose**: Shared infrastructure for retry-with-backoff and safe type conversions.
Used internally by `market_data.py`, `options_data.py`, `fred.py`, `universe.py`.

**Public API**:
```python
async def fetch_with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    retryable: tuple[type[Exception], ...] = (DataSourceUnavailableError,),
) -> T:
    """Execute async callable with exponential backoff.

    Delays: 1s → 2s → 4s → 8s → 16s (capped at max_delay).
    Raises the last exception after max_retries exhausted.
    Logs each retry at WARNING level.
    """

def safe_decimal(value: object) -> Decimal | None:
    """Convert value to Decimal safely. Returns None on failure."""

def safe_int(value: object) -> int | None:
    """Convert value to int safely. Returns None on failure."""

def safe_float(value: object) -> float | None:
    """Convert value to float safely. Returns None on failure (including NaN/inf)."""
```

**Implementation notes**:
- `fetch_with_retry` accepts a zero-arg async factory (not a coroutine) so it can
  re-invoke on each retry. Pattern: `await fetch_with_retry(lambda: client.get(url))`.
- `safe_float` rejects `NaN` and `±inf` via `math.isfinite()` — non-finite values
  propagate as `None`, forcing callers to handle the absence explicitly.
- All safe converters log conversion failures at DEBUG level.

**Lines estimate**: ~80

---

### 2. `rate_limiter.py` — Token Bucket + Semaphore

**Purpose**: Dual-layer rate control. Token bucket limits requests-per-second.
Semaphore limits concurrent in-flight requests. Both configurable via `ServiceConfig`.

**Public API**:
```python
class RateLimiter:
    def __init__(
        self,
        rate: float = 2.0,             # requests per second (from ServiceConfig.rate_limit_rps)
        max_concurrent: int = 5,        # from ServiceConfig.max_concurrent_requests
    ) -> None: ...

    async def acquire(self) -> None:
        """Wait until both a token and a semaphore slot are available."""

    def release(self) -> None:
        """Release the semaphore slot. Tokens refill automatically."""

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...
```

**Implementation notes**:
- Token bucket uses `asyncio.Event` + monotonic clock for refill scheduling.
  Tokens refill at `rate` per second up to bucket capacity (burst = `max_concurrent`).
- Semaphore is a standard `asyncio.Semaphore(max_concurrent)`.
- Context manager pattern: `async with limiter: await do_work()`.
- Thread-safe within a single event loop (standard asyncio guarantee).

**Lines estimate**: ~120

---

### 3. `cache.py` — Two-Tier Caching with Market-Hours-Aware TTL

**Purpose**: Minimize redundant external API calls. In-memory LRU for hot data
(quotes, chains), persistent SQLite for cold data (OHLCV, fundamentals). TTLs
adjust based on whether US options markets are open.

**Public API**:
```python
class ServiceCache:
    def __init__(self, config: ServiceConfig, db_path: Path | None = None) -> None: ...

    async def get(self, key: str) -> bytes | None:
        """Retrieve cached value. Returns None if expired or missing."""

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        """Store value with TTL in seconds. None TTL = permanent."""

    async def invalidate(self, key: str) -> None:
        """Remove a specific key from both tiers."""

    async def clear(self) -> None:
        """Clear all cached data from both tiers."""

    async def close(self) -> None:
        """Close SQLite connection and release resources."""

    def ttl_for(self, data_type: str) -> int:
        """Get appropriate TTL based on data type and current market hours."""
```

**Cache key format**: `{source}:{type}:{ticker}:{params}`
  - `yf:ohlcv:AAPL:1y` — permanent (historical data is immutable)
  - `yf:chain:AAPL:2026-04-18` — 5 min (market hours) / 60 min (after hours)
  - `yf:quote:AAPL` — 1 min (market hours) / 5 min (after hours)
  - `yf:info:AAPL` — 24 hours (fundamentals change rarely)
  - `fred:rate:DGS10` — 24 hours
  - `cboe:universe` — 24 hours
  - `wiki:sp500` — 24 hours
  - `failure:{source}:{ticker}` — 24 hours (cache failures to avoid hammering dead APIs)

**TTL constants** (defined as module-level named constants, not magic numbers):
```python
TTL_OHLCV = 0                       # permanent — historical data is immutable
TTL_CHAIN_MARKET = 5 * 60           # 5 min during market hours
TTL_CHAIN_AFTER = 60 * 60           # 1 hr after hours
TTL_QUOTE_MARKET = 1 * 60           # 1 min during market hours
TTL_QUOTE_AFTER = 5 * 60            # 5 min after hours
TTL_FUNDAMENTALS = 24 * 60 * 60     # 24 hrs
TTL_REFERENCE = 24 * 60 * 60        # 24 hrs (FRED rate, universe)
TTL_FAILURE = 24 * 60 * 60          # 24 hrs (cached failures)
```

**Market hours detection**:
```python
def is_market_hours() -> bool:
    """Check if US options markets are currently open (9:30-16:00 ET, Mon-Fri)."""
    # Uses zoneinfo.ZoneInfo("America/New_York") — never naive datetimes
```

**Implementation notes**:
- In-memory tier: `dict[str, tuple[bytes, float]]` with (value, expiry_monotonic).
  LRU eviction when entry count exceeds configurable max (default 1000).
  Lazy cleanup: check expiry on `get()`, periodic sweep every 100 `get()` calls.
- SQLite tier: `aiosqlite` with WAL mode. Table `service_cache(key TEXT PRIMARY KEY,
  value BLOB, expires_at REAL)`. Lazy deletion of expired rows.
- `set()` writes to in-memory first, then to SQLite for persistent data types.
  Short-TTL data (quotes, chains) stays in-memory only.
- Serialization: callers serialize to `bytes` (via `model.model_dump_json().encode()`).
  Cache is agnostic to content type.

**Lines estimate**: ~250

---

### 4. `market_data.py` — OHLCV, Quotes, Ticker Info & Dividend Waterfall

**Purpose**: Fetch and normalize all yfinance market data into typed models.
The most complex service module — includes the 3-tier dividend yield extraction
waterfall (FR-M7.1) and `MarketCapTier` classification.

**Public API**:
```python
class MarketDataService:
    def __init__(
        self,
        config: ServiceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None: ...

    async def fetch_ohlcv(
        self, ticker: str, period: str = "1y",
    ) -> list[OHLCV]:
        """Fetch historical daily OHLCV bars.

        Returns list[OHLCV] sorted by date ascending.
        Raises TickerNotFoundError if ticker invalid.
        Raises InsufficientDataError if yfinance returns empty data.
        """

    async def fetch_quote(self, ticker: str) -> Quote:
        """Fetch current price snapshot with bid/ask."""

    async def fetch_ticker_info(self, ticker: str) -> TickerInfo:
        """Fetch fundamental data including dividend yield with provenance.

        Implements the 3-tier dividend waterfall (FR-M7.1):
          1. info["dividendYield"] → FORWARD
          2. info["trailingAnnualDividendYield"] → TRAILING
          3. sum(get_dividends("1y")) / price → COMPUTED
          4. 0.0 → NONE
        Includes MarketCapTier classification and cross-validation.
        """

    async def fetch_batch_ohlcv(
        self, tickers: list[str], period: str = "1y",
    ) -> dict[str, list[OHLCV] | DataFetchError]:
        """Batch OHLCV fetch with per-ticker error isolation.

        Returns dict mapping ticker to result or exception.
        Uses asyncio.gather(return_exceptions=True) internally.
        """

    async def close(self) -> None: ...
```

**Dividend Waterfall Implementation (FR-M7.1)**:
```python
def _extract_dividend_yield(
    info: dict[str, Any],
    dividends_series: pd.Series,   # type: ignore[type-arg]
    current_price: Decimal,
) -> tuple[float, DividendSource, float | None, float | None]:
    """3-tier waterfall: returns (yield, source, dividend_rate, trailing_rate).

    CRITICAL: Fall-through condition is `value is None`, NOT falsy.
    0.0 is valid data for non-dividend-paying stocks (growth, biotech).

    Cross-validation: when yield and dollar-rate are both available,
    log WARNING if abs(yield - rate/price) / max(yield, 1e-9) > 0.20.
    """
```

| Tier | yfinance Key (camelCase) | Guard | Source Enum |
|---|---|---|---|
| 1 | `info.get("dividendYield")` | `is not None` | `DividendSource.FORWARD` |
| 2 | `info.get("trailingAnnualDividendYield")` | `is not None` | `DividendSource.TRAILING` |
| 3 | `Ticker.get_dividends(period="1y")` sum / price | sum > 0 | `DividendSource.COMPUTED` |
| 4 | `0.0` (fallback) | always | `DividendSource.NONE` |

**Audit fields extracted alongside waterfall**:
- `info.get("dividendRate")` → `TickerInfo.dividend_rate` (forward annual $)
- `info.get("trailingAnnualDividendRate")` → `TickerInfo.trailing_dividend_rate` (trailing $)

**Cross-validation rule**: When both yield and dollar-rate are available:
```python
if yield_val is not None and rate_val is not None and price > 0:
    implied_yield = float(rate_val) / float(price)
    divergence = abs(yield_val - implied_yield) / max(yield_val, 1e-9)
    if divergence > 0.20:
        logger.warning("Dividend divergence %.1f%% for %s", divergence * 100, ticker)
```

**MarketCapTier classification**:
```python
def _classify_market_cap(market_cap: int | None) -> MarketCapTier | None:
    if market_cap is None:
        return None
    if market_cap >= 200_000_000_000:      return MarketCapTier.MEGA
    if market_cap >= 10_000_000_000:       return MarketCapTier.LARGE
    if market_cap >= 2_000_000_000:        return MarketCapTier.MID
    if market_cap >= 300_000_000:          return MarketCapTier.SMALL
    return MarketCapTier.MICRO
```

**yfinance wrapping pattern** (applies to all yfinance calls in this module):
```python
async def _yf_call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Wrap sync yfinance call: to_thread + wait_for + error mapping."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=self._config.yfinance_timeout,
        )
    except TimeoutError as e:
        raise DataSourceUnavailableError("yfinance", f"timeout after {self._config.yfinance_timeout}s") from e
    except Exception as e:
        raise DataSourceUnavailableError("yfinance", str(e)) from e
```

**Lines estimate**: ~350

---

### 5. `options_data.py` — Option Chain Fetching & Liquidity Filtering

**Purpose**: Fetch option chains from yfinance, apply basic liquidity filters, and
convert to `list[OptionContract]`. Passes `impliedVolatility` through as `market_iv`.
**Does NOT compute Greeks** — that is `pricing/dispatch.py`'s job.

**Public API**:
```python
class OptionsDataService:
    def __init__(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None: ...

    async def fetch_expirations(self, ticker: str) -> list[date]:
        """Fetch available option expiration dates for a ticker."""

    async def fetch_chain(
        self,
        ticker: str,
        expiration: date,
    ) -> list[OptionContract]:
        """Fetch option chain for a specific expiration.

        Applies basic liquidity filters:
          - OI >= PricingConfig.min_oi (default 100)
          - volume >= PricingConfig.min_volume (default 1)
          - Reject contracts where BOTH bid AND ask are zero (truly dead)
        Contracts with bid=0/ask>0 pass through (zero-bid exemption).
        """

    async def fetch_chain_all_expirations(
        self, ticker: str,
    ) -> dict[date, list[OptionContract]]:
        """Fetch chains for all available expirations."""

    async def close(self) -> None: ...
```

**yfinance column mapping to OptionContract**:

| yfinance Column | OptionContract Field | Type Conversion |
|---|---|---|
| `contractSymbol` | (used for logging only) | — |
| `strike` | `strike` | `Decimal(str(value))` |
| `lastPrice` | `last` | `Decimal(str(value))` |
| `bid` | `bid` | `Decimal(str(value))` |
| `ask` | `ask` | `Decimal(str(value))` |
| `volume` | `volume` | `safe_int(value) or 0` |
| `openInterest` | `open_interest` | `safe_int(value) or 0` |
| `impliedVolatility` | `market_iv` | `float` (already annualized — do NOT re-annualize) |
| `inTheMoney` | (used for validation, not stored) | `bool` |

**Fields set by service, not from yfinance**:
- `ticker` — passed as argument
- `option_type` — `OptionType.CALL` or `OptionType.PUT` based on which DataFrame
- `expiration` — parsed from the expiration date argument
- `exercise_style` — `ExerciseStyle.AMERICAN` for all US equity options
- `greeks` — always `None` (populated later by `pricing/dispatch.py`)

**Liquidity filter logic**:
```python
def _passes_liquidity_filter(row: pd.Series, config: PricingConfig) -> bool:  # type: ignore[type-arg]
    oi = safe_int(row.get("openInterest")) or 0
    vol = safe_int(row.get("volume")) or 0
    bid = safe_float(row.get("bid")) or 0.0
    ask = safe_float(row.get("ask")) or 0.0
    # Reject truly dead contracts (both zero)
    if bid == 0.0 and ask == 0.0:
        return False
    # Basic liquidity minimums
    return oi >= config.min_oi and vol >= config.min_volume
```

**Lines estimate**: ~250

---

### 6. `fred.py` — Risk-Free Rate from FRED

**Purpose**: Fetch 10-year Treasury yield from FRED API as proxy for risk-free rate.
Falls back to `PricingConfig.risk_free_rate_fallback` (default 5%) on failure.

**Public API**:
```python
class FredService:
    def __init__(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
    ) -> None: ...

    async def fetch_risk_free_rate(self) -> float:
        """Fetch 10yr Treasury yield as decimal (0.045 = 4.5%).

        Falls back to PricingConfig.risk_free_rate_fallback on any error.
        Caches successful responses for 24 hours.
        """

    async def close(self) -> None:
        """Close httpx client."""
```

**Implementation notes**:
- FRED API: `https://api.stlouisfed.org/fred/series/observations`
  with `series_id=DGS10`, `sort_order=desc`, `limit=1`, `file_type=json`.
- Requires `FRED_API_KEY` environment variable (or `ServiceConfig.fred_api_key`).
  If key is missing, fall back immediately to `risk_free_rate_fallback`.
- Uses `httpx.AsyncClient` with `httpx.Timeout(connect=5.0, read=config.fred_timeout)`.
- Parses the most recent non-null observation value, converts to decimal fraction
  (FRED returns percentage: `4.5` → `0.045`).
- On any error (network, parse, missing API key), logs WARNING and returns fallback.
  Never raises — the risk-free rate should never block the pipeline.

**Lines estimate**: ~130

---

### 7. `universe.py` — Ticker Universe & S&P 500 Classification

**Purpose**: Build the optionable ticker universe from CBOE, classify tickers by
S&P 500 membership and GICS sector (via Wikipedia), and assign `MarketCapTier`.

**Public API**:
```python
class UniverseService:
    def __init__(
        self,
        config: ServiceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None: ...

    async def fetch_optionable_tickers(self) -> list[str]:
        """Fetch CBOE optionable ticker universe.

        Downloads CBOE directory CSV, extracts ticker symbols,
        filters out index symbols (^, $, /).
        Caches for 24 hours.
        """

    async def fetch_sp500_constituents(self) -> dict[str, str]:
        """Fetch S&P 500 constituents with GICS sector.

        Returns dict mapping ticker -> sector.
        Uses pd.read_html(url, attrs={"id": "constituents"}).
        Translates tickers: '.' -> '-' (BRK.B -> BRK-B).
        Validates expected columns at parse time.
        Caches for 24 hours.
        """

    def classify_market_cap(self, market_cap: int | None) -> MarketCapTier | None:
        """Classify market cap into tier (mega/large/mid/small/micro)."""

    async def close(self) -> None: ...
```

**S&P 500 Wikipedia parsing (FR-SV3, Context7-verified)**:
```python
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_REQUIRED_COLUMNS = {"Symbol", "GICS Sector"}

async def _fetch_sp500_table(self) -> pd.DataFrame:
    """Parse S&P 500 table from Wikipedia.

    Uses attrs={"id": "constituents"} for stable targeting (not positional [0]).
    Validates SP500_REQUIRED_COLUMNS exist at parse time.
    Translates ticker '.' -> '-' for yfinance compatibility.
    Raises InsufficientDataError if schema drifts.
    """
    df_list = await asyncio.to_thread(
        pd.read_html, SP500_URL, attrs={"id": "constituents"}
    )
    df = df_list[0]
    if not SP500_REQUIRED_COLUMNS <= set(df.columns):
        missing = SP500_REQUIRED_COLUMNS - set(df.columns)
        raise InsufficientDataError(
            f"Wikipedia S&P 500 table missing columns: {missing}"
        )
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
    return df[["Symbol", "GICS Sector"]]
```

**CBOE optionable universe**:
- Download URL: `https://www.cboe.com/available_weeklys/` (or the full directory CSV)
- Parse CSV, extract `Symbol` column
- Filter out index symbols containing `^`, `$`, `/`
- Strip whitespace, deduplicate

**Lines estimate**: ~220

---

### 8. `health.py` — Service Health Checks

**Purpose**: Pre-flight checks for all external dependencies. Returns typed
`HealthStatus` models with latency measurements and error details.

**Public API**:
```python
class HealthService:
    def __init__(self, config: ServiceConfig) -> None: ...

    async def check_yfinance(self) -> HealthStatus:
        """Check yfinance by fetching a known ticker (SPY)."""

    async def check_fred(self) -> HealthStatus:
        """Check FRED API reachability."""

    async def check_ollama(self) -> HealthStatus:
        """Check Ollama by hitting /api/tags endpoint."""

    async def check_cboe(self) -> HealthStatus:
        """Check CBOE CSV download endpoint."""

    async def check_all(self) -> list[HealthStatus]:
        """Run all health checks concurrently."""

    async def close(self) -> None: ...
```

**Implementation notes**:
- Each check measures wall-clock latency via `time.monotonic()`.
- Each check returns `HealthStatus(available=True/False, latency_ms=..., error=...)`.
- `check_all()` uses `asyncio.gather(return_exceptions=True)` — one failed check
  doesn't block the others.
- Ollama check: `GET {config.ollama_host}/api/tags` — verifies server is running and
  the configured model (`config.ollama_model`) is available.
- yfinance check: fetch SPY quote — if this fails, yfinance is down.
- FRED check: simple HTTP HEAD to API endpoint.

**Lines estimate**: ~170

---

### 9. `__init__.py` — Package Re-Exports

```python
"""Options Arena — Data fetching, caching, and rate limiting.

The services package is the sole layer that touches external APIs.
All public functions return typed Pydantic models.
"""

from options_arena.services.cache import ServiceCache
from options_arena.services.fred import FredService
from options_arena.services.health import HealthService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

__all__ = [
    "FredService",
    "HealthService",
    "MarketDataService",
    "OptionsDataService",
    "RateLimiter",
    "ServiceCache",
    "UniverseService",
]
```

Consumers import from the package: `from options_arena.services import MarketDataService`.
`helpers.py` is NOT exported — it is internal to the package.

---

## Model Updates Required

`ServiceConfig` in `models/config.py` needs one additional field for FRED:

```python
class ServiceConfig(BaseModel):
    # ... existing fields ...
    fred_api_key: str | None = None  # FRED API key; None = skip FRED, use fallback rate
```

This is a backward-compatible addition (default `None`). Env override:
`ARENA_SERVICE__FRED_API_KEY=abc123`.

---

## Issue Decomposition (8 Issues)

### Issue 1: Retry & Rate Limiting Infrastructure
**Files**: `helpers.py`, `rate_limiter.py`
**Tests**: `test_helpers.py` (~12 tests), `test_rate_limiter.py` (~12 tests)
**Depends on**: Nothing (foundation)
**Blocked by**: None

Deliverables:
- `fetch_with_retry()` with exponential backoff (1s→16s, max 5)
- `safe_decimal()`, `safe_int()`, `safe_float()` with NaN/inf rejection
- `RateLimiter` class with token bucket + semaphore
- Async context manager support
- Tests: retry success on 2nd attempt, retry exhaustion, backoff timing,
  token depletion, semaphore limiting, concurrent access

---

### Issue 2: Cache Layer
**Files**: `cache.py`
**Tests**: `test_cache.py` (~15 tests)
**Depends on**: Nothing (foundation)
**Blocked by**: None

Deliverables:
- `ServiceCache` with in-memory LRU + SQLite tiers
- Market-hours-aware TTL selection (`is_market_hours()`)
- Named TTL constants (no magic numbers)
- Cache key format enforcement
- Tests: set/get round-trip, TTL expiry, LRU eviction, market-hours TTL
  selection, SQLite persistence across restarts, invalidation, `failure:` caching

---

### Issue 3: Market Data Service
**Files**: `market_data.py`
**Tests**: `test_market_data.py` (~22 tests)
**Depends on**: Issue 1 (helpers, rate_limiter), Issue 2 (cache)

Deliverables:
- `MarketDataService` class with DI constructor
- `fetch_ohlcv()`: yfinance history → `list[OHLCV]`, cache-first, sorted by date
- `fetch_quote()`: yfinance fast_info → `Quote` with UTC timestamp
- `fetch_ticker_info()`: yfinance info → `TickerInfo` with:
  - 3-tier dividend waterfall (all 4 `DividendSource` outcomes)
  - Cross-validation warning (yield vs dollar-rate > 20% divergence)
  - `MarketCapTier` classification
  - Audit fields (`dividend_rate`, `trailing_dividend_rate`)
- `fetch_batch_ohlcv()`: concurrent fetch with error isolation
- All yfinance calls via `asyncio.to_thread()` + `asyncio.wait_for(timeout)`
- Tests: happy path for each method, dividend waterfall all 4 tiers, cross-validation
  warning triggered, cross-validation no warning when consistent, empty DataFrame
  handling, ticker not found, timeout, batch with mixed success/failure,
  market cap tier boundaries, cache hit avoids yfinance call

---

### Issue 4: Options Data Service
**Files**: `options_data.py`
**Tests**: `test_options_data.py` (~15 tests)
**Depends on**: Issue 1 (helpers, rate_limiter), Issue 2 (cache)

Deliverables:
- `OptionsDataService` class with DI constructor
- `fetch_expirations()`: available dates → `list[date]`
- `fetch_chain()`: chain → `list[OptionContract]` with:
  - Column mapping (yfinance camelCase → model fields)
  - `impliedVolatility` → `market_iv` passthrough (no re-annualization)
  - `exercise_style = ExerciseStyle.AMERICAN` for all US equity options
  - `greeks = None` (yfinance provides NO Greeks)
  - Liquidity filter: OI >= min_oi, volume >= min_volume
  - Both-zero bid/ask rejection, zero-bid exemption (bid=0/ask>0 passes)
- `fetch_chain_all_expirations()`: all dates concurrently
- Tests: happy path, liquidity filter rejects low OI, both-zero rejection,
  zero-bid exemption passes, market_iv passthrough verified, column mapping
  correctness, empty chain, timeout, `Decimal` precision preserved

---

### Issue 5: FRED Service
**Files**: `fred.py`
**Tests**: `test_fred.py` (~8 tests)
**Depends on**: Issue 2 (cache)

Deliverables:
- `FredService` class with httpx AsyncClient
- `fetch_risk_free_rate()`: FRED API → `float` (decimal fraction)
- Graceful fallback to `PricingConfig.risk_free_rate_fallback` on any error
- FRED API key from `ServiceConfig.fred_api_key`
- Percentage-to-decimal conversion (FRED `4.5` → `0.045`)
- Tests: successful fetch, missing API key fallback, network error fallback,
  malformed response fallback, cache hit, percentage conversion, timeout

---

### Issue 6: Universe Service
**Files**: `universe.py`
**Tests**: `test_universe.py` (~15 tests)
**Depends on**: Issue 1 (helpers, rate_limiter), Issue 2 (cache)

Deliverables:
- `UniverseService` class
- `fetch_optionable_tickers()`: CBOE CSV → `list[str]`, index symbol filtering
- `fetch_sp500_constituents()`: Wikipedia → `dict[str, str]` (ticker → sector)
  - `pd.read_html(url, attrs={"id": "constituents"})` (Context7-verified)
  - Column validation at parse time (`SP500_REQUIRED_COLUMNS`)
  - Ticker translation: `.` → `-` (BRK.B → BRK-B)
- `classify_market_cap()`: `int | None` → `MarketCapTier | None`
- Tests: S&P 500 parsing happy path, ticker translation, column validation
  failure, CBOE CSV parsing, index symbol filtering, market cap classification
  boundaries (mega/large/mid/small/micro/None), empty DataFrame, cache hit

---

### Issue 7: Health Service
**Files**: `health.py`
**Tests**: `test_health.py` (~10 tests)
**Depends on**: None (standalone — uses httpx and yfinance directly)

Deliverables:
- `HealthService` class
- Individual checks: `check_yfinance()`, `check_fred()`, `check_ollama()`, `check_cboe()`
- `check_all()`: concurrent health checks
- Latency measurement via `time.monotonic()`
- Error detail capture in `HealthStatus.error`
- Tests: each service available, each service down, latency recorded,
  `check_all()` concurrent execution, partial failures

---

### Issue 8: Package Integration & Verification Gate
**Files**: `__init__.py`, `ServiceConfig` update, `services/CLAUDE.md` update
**Tests**: (verification only — no new test files)
**Depends on**: Issues 1–7

Deliverables:
- Update `__init__.py` with all public re-exports and `__all__`
- Add `fred_api_key: str | None = None` to `ServiceConfig`
- Update `services/CLAUDE.md` with module listing and patterns
- Verification gate: all three checks pass:
  ```bash
  uv run ruff check . --fix && uv run ruff format .
  uv run pytest tests/ -v
  uv run mypy src/ --strict
  ```
- Total test count target: ~810 (708 existing + ~100 new services tests)

---

## Test Plan (~103 Tests)

| Test File | Module Under Test | Test Count | Key Scenarios |
|---|---|---|---|
| `test_helpers.py` | `helpers.py` | ~12 | Retry success, retry exhaustion, backoff delays, safe_decimal/int/float conversions, NaN/inf rejection |
| `test_rate_limiter.py` | `rate_limiter.py` | ~12 | Token bucket fill/drain, semaphore concurrency limit, context manager, burst behavior |
| `test_cache.py` | `cache.py` | ~15 | Set/get, TTL expiry, market-hours TTL selection, LRU eviction, SQLite persistence, invalidation, failure caching |
| `test_market_data.py` | `market_data.py` | ~22 | OHLCV happy path, quote fetch, ticker info, dividend waterfall (4 tiers), cross-validation, MarketCapTier, batch fetch, timeout, cache hit |
| `test_options_data.py` | `options_data.py` | ~15 | Chain fetch, liquidity filter, both-zero rejection, zero-bid exemption, market_iv passthrough, Decimal precision, empty chain |
| `test_fred.py` | `fred.py` | ~8 | Success, missing key fallback, network error, malformed response, percentage conversion, cache hit |
| `test_universe.py` | `universe.py` | ~15 | S&P 500 parse, ticker translation, column validation, CBOE parse, index filter, market cap classification, cache |
| `test_health.py` | `health.py` | ~10 | Each service up/down, latency recording, check_all concurrent, partial failure |
| **Total** | | **~109** | |

**Testing rules** (from `tests/CLAUDE.md`):
- Never hit real APIs — mock yfinance, httpx, CBOE, Wikipedia
- Never `==` for floats — always `pytest.approx()`
- Never hardcode dates dependent on `today()` — mock `date.today()` or `datetime.now()`
- Use `monkeypatch` for env vars, `unittest.mock.patch` for yfinance/httpx
- Tolerances: prices `abs=Decimal("0.01")`, rates `rel=1e-3`

---

## Dependencies

- **Blocked by**: Epic 1 models — `TickerInfo`, `OptionContract`, `ServiceConfig`,
  `DividendSource`, `MarketCapTier`, `HealthStatus`, `OHLCV`, `Quote` (all complete)
- **Blocks**: Epic 7 (scan pipeline needs OHLCV, option chains, universe)
- **Parallelizable**: Issues 1+2 can run in parallel. Issues 3+4+5+6 can run in
  parallel after 1+2 complete. Issue 7 is standalone. Issue 8 waits for all.

---

## Verification Gate

```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest tests/ -v                              # all tests (~810 target)
uv run mypy src/ --strict                            # type checking
```

All three must pass. A task is not done until all pass.

---

## Key Decisions

| Decision | Rationale |
|---|---|
| Complete rewrite (no v3 cherry-pick) | v3 has architectural debt: mixed sync/async, raw dict returns, incorrect Greek assumptions, regex scraping. Clean rewrite is faster than fixing v3 patterns. |
| Class-based services | Services hold state (rate limiters, caches, httpx clients). Classes provide clean DI and lifecycle management. |
| `asyncio.to_thread()` for all yfinance | yfinance is synchronous. Wrapping in `to_thread` + `wait_for` keeps the event loop non-blocking with timeout enforcement. |
| Dividend waterfall: `is None` not falsy | `0.0` is valid data for growth stocks. Falsy check would skip `0.0` and fall through to `COMPUTED` or `NONE`, corrupting provenance. |
| Wikipedia `attrs={"id": "constituents"}` | Positional `[0]` breaks if Wikipedia adds tables before the target. HTML id targeting is stable. (Context7-verified) |
| FRED never raises | Risk-free rate should never block the scan pipeline. Graceful fallback to configurable default. |
| `exercise_style = AMERICAN` for all US equities | Standard. European-style options on US equities are exotic and out of MVP scope. |
| `greeks = None` from services | yfinance provides NO Greeks. `pricing/dispatch.py` is the sole source. This is a pipeline fact, not a design choice. |
| `market_iv` passthrough (no re-annualization) | yfinance `impliedVolatility` is already annualized. Re-annualizing would corrupt the value. |
| Cache failures for 24h | Prevents hammering dead APIs. If OHLCV fetch fails for ticker X, don't retry for 24h. |

---

## Estimated Tests: ~109

---

## Tasks Created
- [ ] #30 - Retry & Rate Limiting Infrastructure (parallel: true)
- [ ] #35 - Cache Layer (parallel: true)
- [ ] #36 - Market Data Service (parallel: true, depends: #30, #35)
- [ ] #37 - Options Data Service (parallel: true, depends: #30, #35)
- [ ] #31 - FRED Service (parallel: true, depends: #35)
- [ ] #32 - Universe Service (parallel: true, depends: #30, #35)
- [ ] #33 - Health Service (parallel: true, standalone)
- [ ] #34 - Package Integration & Verification Gate (parallel: false, depends: all)

Total tasks: 8
Parallel tasks: 7
Sequential tasks: 1
Estimated total effort: 52 hours
