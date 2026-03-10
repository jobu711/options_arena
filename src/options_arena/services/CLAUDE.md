# CLAUDE.md — Services Layer (`services/`)

## Purpose

The **sole layer** that touches external APIs and data sources. Every public function
returns a typed Pydantic model from `models/` — never a raw dict, DataFrame, or JSON blob.
All external I/O is async. Services hold shared state (rate limiters, caches, httpx clients)
and use class-based DI with explicit `close()` lifecycle.

## Files

| File | Class / Purpose | Public? |
|------|----------------|---------|
| `base.py` | `ServiceBase[ConfigT]` — generic mixin with cache, retry, yfinance helpers | Yes |
| `helpers.py` | `fetch_with_retry()`, `safe_decimal()`, `safe_int()`, `safe_float()` | **No** — internal |
| `rate_limiter.py` | `RateLimiter` — token bucket + `asyncio.Semaphore` dual-layer | Yes |
| `cache.py` | `ServiceCache` — in-memory LRU + SQLite two-tier cache | Yes |
| `market_data.py` | `MarketDataService` — OHLCV, quotes, ticker info, dividend waterfall | Yes |
| `options_data.py` | `OptionsDataService` — option chains, liquidity filtering | Yes |
| `fred.py` | `FredService` — risk-free rate from FRED API | Yes |
| `universe.py` | `UniverseService` — CBOE optionable tickers, S&P 500 constituents | Yes |
| `health.py` | `HealthService` — pre-flight checks for all external dependencies | Yes |
| `__init__.py` | Re-exports all public classes with `__all__` | Yes |

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Typed boundary** | Every public function returns a Pydantic model. No `dict`, `DataFrame`, `Any`, or `tuple` crosses the package boundary. |
| **Async-first** | All public methods are `async`. Sync yfinance wrapped via `asyncio.to_thread()`. |
| **Config-driven** | Every timeout, rate limit, TTL, and filter threshold comes from `ServiceConfig` or `PricingConfig`. Zero magic numbers in function bodies. |
| **DI constructor** | Each service class receives its dependencies (`config`, `cache`, `limiter`) via `__init__`. No global state, no module-level singletons. |
| **Explicit close** | Every class with an httpx client or SQLite connection has `async def close()`. Caller is responsible for calling it (typically `cli.py` in a `try/finally`). |
| **Fail-safe batch** | Batch operations use `asyncio.gather(*tasks, return_exceptions=True)`. One failed ticker never crashes a 500-ticker scan. |
| **Logging only** | `logging` module — never `print()`. Log retries at WARNING, conversions at DEBUG, fallbacks at WARNING. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all enums, configs, typed models) | `indicators/` (wrong direction) |
| `utils/exceptions.py` (domain exceptions) | `pricing/` (services don't price) |
| `helpers.py`, `rate_limiter.py`, `cache.py` (internal infra) | `scoring/` (services don't score) |
| stdlib: `asyncio`, `logging`, `math`, `time`, `zoneinfo`, `decimal` | `agents/`, `reporting/`, `cli` |
| External: `yfinance`, `httpx`, `aiosqlite`, `pandas` (read_csv for CSV sources) | |

---

## ServiceBase Mixin (`base.py`)

`ServiceBase[ConfigT]` is a generic mixin that consolidates shared service infrastructure.
Services subclass it to get cache-first fetching, rate-limited retries, and yfinance wrapping
without duplicating boilerplate.

### Constructor

```python
ServiceBase.__init__(config: ConfigT, cache: ServiceCache, limiter: RateLimiter | None = None)
```
Stores `self._config`, `self._cache`, `self._limiter`, `self._log`.

### Helpers (opt-in, not abstract)

| Method | Purpose |
|--------|---------|
| `close()` | Default no-op. Override in subclasses with httpx clients etc. |
| `_cached_fetch[T: BaseModel](key, model_type, factory, ttl, *, deserializer?)` | Cache-first: deserializes on hit, calls factory on miss, stores result. |
| `_retried_fetch[T](fn, *args, *, max_attempts=3)` | Delegates to `fetch_with_limiter_retry` with `self._limiter`. Raises `RuntimeError` if no limiter. |
| `_yf_call[T](fn, *args, *, timeout, **kwargs)` | `to_thread` + `wait_for` + error mapping. Re-raises `DataFetchError` subclasses as-is. |

### Key Design Decisions

- **No `@abstractmethod`** — mixin pattern, not an interface. Services opt into helpers.
- **Generic `ConfigT` with NO bound** — config types are heterogeneous `BaseModel` subclasses.
- **`_cached_fetch` default serde** — `model_type.model_validate_json(cached)` / `model.model_dump_json().encode()`.
- **`_cached_fetch` custom serde** — optional `deserializer: Callable[[bytes], T]` for non-standard deserialization.
- **`_yf_call` does NOT double-wrap** — `DataFetchError` subclasses are re-raised as-is to avoid wrapping `TickerNotFoundError` in `DataSourceUnavailableError`.

---

## Async Patterns — Context7-Verified (Python 3.13, httpx, aiosqlite)

### 1. Wrapping Sync yfinance — `asyncio.to_thread` + `asyncio.wait_for`

yfinance is synchronous. Every call must be offloaded to a thread and bounded by timeout.
(Context7-verified: `asyncio.to_thread` runs blocking functions in a separate thread
without blocking the event loop.)

```python
async def _yf_call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Wrap sync yfinance: to_thread + wait_for + error mapping."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=self._config.yfinance_timeout,
        )
    except TimeoutError as e:
        raise DataSourceUnavailableError(
            "yfinance", f"timeout after {self._config.yfinance_timeout}s"
        ) from e
    except Exception as e:
        raise DataSourceUnavailableError("yfinance", str(e)) from e
```

**Critical**: `asyncio.wait_for` raises `TimeoutError` (not `asyncio.TimeoutError` — they
are the same since Python 3.11, but use `TimeoutError` for forward compatibility).
The `timeout` parameter is in **seconds** (float). Always source from `ServiceConfig`.

**Pattern**: `asyncio.to_thread(fn, *args, **kwargs)` — positional and keyword args are
forwarded to `fn`. Do NOT pre-call the function: `to_thread(fn())` is WRONG (runs
synchronously). Pass the callable and its args separately.

### 2. Batch Operations — `asyncio.gather` with Error Isolation

(Context7-verified: `asyncio.gather` schedules awaitables concurrently and returns results
in the same order as the input.)

```python
async def fetch_batch_ohlcv(
    self, tickers: list[str], period: str = "1y",
) -> dict[str, list[OHLCV] | DataFetchError]:
    tasks = [self.fetch_ohlcv(ticker, period) for ticker in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        ticker: result
        for ticker, result in zip(tickers, results, strict=True)
    }
```

**Critical rules for `gather`**:
- `return_exceptions=True` — exceptions become values in the result list instead of
  propagating. This is mandatory for batch operations.
- Results preserve input order — `zip(tickers, results, strict=True)` is safe.
- Without `return_exceptions=True`, the first exception cancels all remaining tasks.
  Never omit this for batch fetches.
- Callers must check `isinstance(result, Exception)` before using each value.

### 3. Concurrency Control — `asyncio.Semaphore`

(Context7-verified: `asyncio.Semaphore` limits concurrent access. Use `try/finally` or
context manager to guarantee release.)

```python
class RateLimiter:
    def __init__(self, rate: float = 2.0, max_concurrent: int = 5) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate = rate
        # ... token bucket state

    async def acquire(self) -> None:
        await self._semaphore.acquire()
        await self._wait_for_token()

    def release(self) -> None:
        self._semaphore.release()

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()
```

**Critical**: `Semaphore.release()` is synchronous (not `async`). The `__aexit__` method
is async but the release call inside it is sync. Don't `await self.release()`.

**Token bucket**: Use `time.monotonic()` for timing (not `time.time()` — monotonic is
immune to clock adjustments). Track `_last_refill: float` and `_tokens: float`.
Refill tokens on each `acquire()` based on elapsed time.

### 4. Token Bucket Timing — `asyncio.Event` + `time.monotonic`

(Context7-verified: `asyncio.Event` coordinates between tasks. `event.wait()` blocks
until `event.set()` is called.)

```python
async def _wait_for_token(self) -> None:
    """Block until a token is available in the bucket."""
    while True:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._max_tokens,
            self._tokens + elapsed * self._rate,
        )
        self._last_refill = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return
        # Sleep until next token is available
        wait_time = (1.0 - self._tokens) / self._rate
        await asyncio.sleep(wait_time)
```

**Why `asyncio.sleep` not `Event`**: For a simple token bucket, `asyncio.sleep(wait_time)`
is simpler and sufficient. `Event` is better when one task signals another (e.g., producer/
consumer). Don't over-engineer — sleep-based refill is the standard pattern.

### 5. httpx AsyncClient Lifecycle

(Context7-verified: `httpx.AsyncClient` supports both context manager and explicit `aclose()`.)

```python
class FredService:
    def __init__(self, config: ServiceConfig, ...) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                10.0,                          # default for all operations
                connect=5.0,                   # TCP connection timeout
                read=config.fred_timeout,      # response read timeout
            ),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )

    async def close(self) -> None:
        await self._client.aclose()
```

**Critical rules** (Context7-verified):
- `httpx.Timeout(default, connect=, read=, write=, pool=)` — first positional arg is the
  default. Named args override specific phases.
- `httpx.Limits(max_connections=, max_keepalive_connections=)` — connection pooling.
- `httpx.AsyncHTTPTransport(retries=1)` — **connection-level retries only** (TCP failures).
  Does NOT retry on HTTP 429/500. Our `fetch_with_retry()` handles application-level retry.
- Close with `await client.aclose()` — NOT `client.close()` (that's sync-only).
- One `AsyncClient` per service instance. Create in `__init__`, close in `close()`.
  Never create per-request.

### 6. aiosqlite — Async SQLite with WAL

(Context7-verified: `aiosqlite.connect()` returns an async context manager. Supports
`execute`, `fetchone`, `fetchall`, `commit`.)

```python
async def _init_db(self) -> None:
    self._db = await aiosqlite.connect(self._db_path)
    await self._db.execute("PRAGMA journal_mode=WAL")
    await self._db.execute(
        "CREATE TABLE IF NOT EXISTS service_cache "
        "(key TEXT PRIMARY KEY, value BLOB, expires_at REAL)"
    )
    await self._db.commit()

async def get(self, key: str) -> bytes | None:
    async with self._db.execute(
        "SELECT value, expires_at FROM service_cache WHERE key = ?", (key,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    value, expires_at = row
    if expires_at and expires_at < time.monotonic():
        await self.invalidate(key)
        return None
    return value  # type: ignore[return-value]

async def close(self) -> None:
    if self._db is not None:
        await self._db.close()
```

**Critical**: Use `await db.commit()` after writes — aiosqlite does NOT auto-commit.
Cursor as async context manager (`async with db.execute(...) as cursor:`) is the
recommended pattern for queries.

---

## yfinance Wrapping Rules

yfinance is convenient but unreliable. Every call must be wrapped with validation.

### Validation Checklist
1. **Wrap in `_yf_call`** — `asyncio.to_thread` + `asyncio.wait_for` + error mapping
2. **Check empty returns** — yfinance silently returns empty DataFrames for invalid tickers
3. **Normalize column names** — yfinance uses camelCase (Context7-verified)
4. **Convert to typed models** immediately — no DataFrames cross the service boundary
5. **Catch `Exception` broadly** — yfinance raises inconsistent exception types
6. **Verify date range** — yfinance silently returns less data than requested

### yfinance Field Names (Context7-Verified, camelCase)

**`Ticker.info` dict keys:**
`dividendYield`, `trailingAnnualDividendYield`, `dividendRate`,
`trailingAnnualDividendRate`, `marketCap`, `sector`, `shortName`,
`fiftyTwoWeekHigh`, `fiftyTwoWeekLow`, `currentPrice`, `previousClose`

**`option_chain(date)` DataFrame columns (Context7-verified):**
`contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`,
`change`, `percentChange`, `volume`, `openInterest`, `impliedVolatility`,
`inTheMoney`, `contractSize`, `currency`

**NOT in chain data:** delta, gamma, theta, vega, rho — **yfinance provides NO Greeks**.
`pricing/dispatch.py` is the sole source of Greeks.

### Options Chain Column Mapping

| yfinance Column | OptionContract Field | Conversion |
|----------------|---------------------|------------|
| `strike` | `strike` | `Decimal(str(value))` |
| `lastPrice` | `last` | `Decimal(str(value))` |
| `bid` | `bid` | `Decimal(str(value))` |
| `ask` | `ask` | `Decimal(str(value))` |
| `volume` | `volume` | `safe_int(value) or 0` |
| `openInterest` | `open_interest` | `safe_int(value) or 0` |
| `impliedVolatility` | `market_iv` | `float` (already annualized — do NOT re-annualize) |

**Fields set by service, not yfinance:**
- `ticker` — passed as argument
- `option_type` — `OptionType.CALL` or `.PUT` based on `.calls` vs `.puts`
- `expiration` — from the expiration date argument
- `exercise_style` — `ExerciseStyle.AMERICAN` for all U.S. equity options
- `greeks` — always `None` (populated later by `pricing/dispatch.py`)

---

## Dividend Waterfall (FR-M7.1)

3-tier waterfall in `market_data.py`. Guarantees `float` output (never `None`).

| Tier | yfinance Key | Guard | Source Enum |
|------|-------------|-------|-------------|
| 1 | `info.get("dividendYield")` | `is not None` | `DividendSource.FORWARD` |
| 2 | `info.get("trailingAnnualDividendYield")` | `is not None` | `DividendSource.TRAILING` |
| 3 | `sum(get_dividends("1y")) / price` | `sum > 0` | `DividendSource.COMPUTED` |
| 4 | `0.0` (fallback) | always | `DividendSource.NONE` |

**CRITICAL**: Fall-through condition is `value is None`, NOT falsy. `0.0` is valid data
for non-dividend-paying growth stocks. Checking `if not value:` skips `0.0` and corrupts
provenance tracking.

**Cross-validation**: When both yield and dollar-rate are available, warn if divergence > 20%.

---

## Caching

### TTL Constants (named, not magic numbers)

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

### Cache Key Format
`{source}:{type}:{ticker}:{params}` — e.g., `yf:chain:AAPL:2026-04-18`

### Two-Tier Architecture
- **In-memory**: `dict[str, tuple[bytes, float]]` — (value, expiry_monotonic). LRU eviction
  at configurable max (default 1000). Short-TTL data (quotes, chains) stays here only.
- **SQLite**: `aiosqlite` with WAL mode. Persistent data (OHLCV, fundamentals, failures).
  Table: `service_cache(key TEXT PRIMARY KEY, value BLOB, expires_at REAL)`.

### Market Hours
- US options: 9:30 AM – 4:00 PM ET, Monday–Friday.
- `zoneinfo.ZoneInfo("America/New_York")` — never naive datetimes.
- Shorter TTLs during market hours, longer after close.

---

## Rate Limiting

Dual-layer: token bucket (requests-per-second) + semaphore (max concurrent).

- yfinance: ~2 req/s (conservative default from `ServiceConfig.rate_limit_rps`).
- Exponential backoff: 1s → 2s → 4s → 8s → 16s, max 5 retries.
- `fetch_with_retry()` accepts a **zero-arg async factory** (not a coroutine) so it can
  re-invoke on each retry: `await fetch_with_retry(lambda: self._yf_call(fn, *args))`.

---

## Error Strategy

| Error Source | Exception | Behavior |
|-------------|-----------|----------|
| Ticker not found | `TickerNotFoundError(ticker)` | Raise immediately |
| Empty DataFrame from yfinance | `InsufficientDataError(ticker, reason)` | Raise after validation |
| yfinance timeout / network | `DataSourceUnavailableError("yfinance", detail)` | Raise (retry in batch) |
| FRED / CBOE unreachable | `DataSourceUnavailableError(source, detail)` | Fallback + WARNING log |
| Rate limit after max retries | `RateLimitExceededError(source, detail)` | Raise |
| GitHub CSV schema drift | `InsufficientDataError(detail)` | Raise with column mismatch |
| FRED any error | — | **Never raises** — returns `PricingConfig.risk_free_rate_fallback` |

All exceptions from `utils/exceptions.py`. Never bare `except:`. Always catch specific types.

---

## Liquidity Filtering (Service Layer)

Basic filters applied in `options_data.py`. Advanced filtering (spread, delta) is in
`scoring/contracts.py` — not here.

```python
def _passes_liquidity_filter(row: pd.Series, config: PricingConfig) -> bool:  # type: ignore[type-arg]
    oi = safe_int(row.get("openInterest")) or 0
    vol = safe_int(row.get("volume")) or 0
    bid = safe_float(row.get("bid")) or 0.0
    ask = safe_float(row.get("ask")) or 0.0
    if bid == 0.0 and ask == 0.0:   # truly dead — reject
        return False
    # bid=0/ask>0 passes (zero-bid exemption)
    return oi >= config.min_oi and vol >= config.min_volume
```

---

## Health Checks

Pre-flight checks return `HealthStatus` with latency measurement:
- **yfinance**: fetch SPY quote
- **FRED**: HTTP HEAD to API endpoint
- **Groq**: `GET https://api.groq.com/openai/v1/models` with Bearer token
- **CBOE**: check CSV download endpoint

`check_all()` runs all concurrently via `asyncio.gather(return_exceptions=True)`.
Latency via `time.monotonic()`.

---

## Safe Type Converters (`helpers.py`)

```python
def safe_decimal(value: object) -> Decimal | None:
    """Convert to Decimal safely. Returns None on failure."""

def safe_int(value: object) -> int | None:
    """Convert to int safely. Returns None on failure."""

def safe_float(value: object) -> float | None:
    """Convert to float safely. Returns None on failure (including NaN/inf)."""
```

- `safe_float` rejects `NaN` and `±inf` via `math.isfinite()`.
- All converters log failures at DEBUG level.
- Used throughout `market_data.py` and `options_data.py` for yfinance data conversion.

---

## Test Rules (see also `tests/CLAUDE.md`)

- **Never hit real APIs** — mock yfinance (`monkeypatch` / `unittest.mock.patch`), httpx
  (`respx` or manual mock), aiosqlite (in-memory `:memory:` DB)
- **Never `==` for floats** — always `pytest.approx()`
- **Never hardcode dates** — mock `datetime.now()` / `date.today()` for TTL and DTE tests
- **Tolerances**: prices `abs=Decimal("0.01")`, rates `rel=1e-3`
- **Async tests**: use `pytest-asyncio` with `@pytest.mark.asyncio`
- **Test dividend waterfall all 4 tiers** independently
- **Test zero-bid exemption** explicitly in options chain tests
- **Test batch with mixed success/failure** — verify isolated error handling

---

## What Claude Gets Wrong Here (Fix These)

1. **Returning raw dicts or DataFrames** — Every service method returns a Pydantic model. No `dict[str, Any]`, no `pd.DataFrame`, no JSON strings crossing the boundary.
2. **Calling `to_thread(fn())` instead of `to_thread(fn, *args)`** — The first form calls `fn()` synchronously on the current thread, then passes the result to `to_thread`. Pass the callable and args separately.
3. **Forgetting `return_exceptions=True` in batch gather** — Without it, one failed ticker cancels all remaining tasks and crashes the entire batch.
4. **Using `asyncio.TimeoutError` instead of `TimeoutError`** — Since Python 3.11 they are the same, but `TimeoutError` is the canonical name. `asyncio.TimeoutError` is deprecated.
5. **Creating httpx clients per-request** — One `AsyncClient` per service instance. Create in `__init__`, close in `close()` via `await client.aclose()`.
6. **Forgetting `await db.commit()` after aiosqlite writes** — aiosqlite does NOT auto-commit.
7. **Using `time.time()` for rate limiting** — Use `time.monotonic()` which is immune to clock adjustments.
8. **Assuming yfinance provides Greeks** — It provides `impliedVolatility` only. No delta, gamma, theta, vega, rho. All Greeks come from `pricing/dispatch.py`.
9. **Re-annualizing yfinance `impliedVolatility`** — It's already annualized. Passing through as `market_iv` directly.
10. **Using falsy check for dividend waterfall** — `if not value:` skips `0.0`. Use `if value is None:` for fall-through.
11. **Mixing sync and async in the same module** — All public methods are async. Internal helpers may be sync (pure functions like `_classify_market_cap`). Never call sync I/O without `to_thread`.
12. **Bare `except:`** — Always catch specific exception types. Use `except Exception as e:` at most, and re-raise as a domain exception.
13. **`print()` in service code** — Use `logging` module. `logger = logging.getLogger(__name__)`.
14. **Magic numbers** — All timeouts, TTLs, thresholds from `ServiceConfig` or `PricingConfig`. Named constants for TTLs.
15. **`await semaphore.release()`** — `Semaphore.release()` is synchronous. Don't await it.
16. **Forgetting `strict=True` on `zip`** — When zipping tickers with gather results, use `zip(tickers, results, strict=True)` to catch length mismatches.
