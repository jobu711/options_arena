# CLAUDE.md -- Services Layer (`services/`)

## Purpose

The **sole layer** that touches external APIs and data sources. Every public function
returns a typed Pydantic model from `models/` -- never a raw dict, DataFrame, or JSON blob.
All external I/O is async. Services hold shared state (rate limiters, caches, httpx clients)
and use class-based DI with explicit `close()` lifecycle.

Use Glob to discover files.

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Typed boundary** | Every public function returns a Pydantic model. No `dict`, `DataFrame`, `Any`, or `tuple` crosses the package boundary. |
| **Async-first** | All public methods are `async`. Sync yfinance wrapped via `asyncio.to_thread()`. |
| **Config-driven** | Every timeout, rate limit, TTL, and filter threshold comes from `ServiceConfig` or `PricingConfig`. Zero magic numbers. |
| **DI constructor** | Each service class receives `config`, `cache`, `limiter` via `__init__`. No global state, no singletons. |
| **Explicit close** | Every class with an httpx client or SQLite connection has `async def close()`. Caller responsible (`try/finally`). |
| **Fail-safe batch** | `asyncio.gather(*tasks, return_exceptions=True)`. One failed ticker never crashes a 500-ticker scan. |
| **Logging only** | `logging` module -- never `print()`. Log retries at WARNING, conversions at DEBUG, fallbacks at WARNING. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all enums, configs, typed models) | `indicators/` (wrong direction) |
| `utils/exceptions.py` (domain exceptions) | `pricing/` (services don't price) |
| `helpers.py`, `rate_limiter.py`, `cache.py` (internal infra) | `scoring/` (services don't score) |
| stdlib: `asyncio`, `logging`, `math`, `time`, `zoneinfo`, `decimal` | `agents/`, `reporting/`, `cli/` |
| External: `yfinance`, `httpx`, `aiosqlite`, `pandas` (CSV only) | |

---

## ServiceBase Mixin (`base.py`)

Generic `ServiceBase[ConfigT]` consolidates shared service infrastructure. Services subclass
it to get cache-first fetching, rate-limited retries, and yfinance wrapping.

Stores: `self._config`, `self._cache`, `self._limiter`, `self._log`.

| Method | Purpose |
|--------|---------|
| `close()` | Default no-op. Override in subclasses with httpx clients. |
| `_cached_fetch[T](key, model_type, factory, ttl)` | Cache-first: deserialize on hit, call factory on miss, store. Default serde via `model_validate_json`/`model_dump_json`. Optional custom `deserializer`. |
| `_retried_fetch[T](fn, *args)` | Delegates to `fetch_with_limiter_retry` with rate limiter. |
| `_yf_call[T](fn, *args)` | `to_thread` + `wait_for` + error mapping. Re-raises `DataFetchError` subclasses as-is (no double-wrapping). |

No `@abstractmethod` -- mixin pattern. Services opt in to helpers.
Generic `ConfigT` with NO bound -- config types are heterogeneous `BaseModel` subclasses.

---

## Key Async Patterns

- **yfinance wrapping**: `_yf_call` uses `to_thread(fn, *args)` + `wait_for(timeout)`.
  CRITICAL: `to_thread(fn, *args)` NOT `to_thread(fn())` (latter runs synchronously).
- **Batch**: `asyncio.gather(*tasks, return_exceptions=True)` mandatory. `zip(tickers, results, strict=True)`.
- **Rate limiting**: `RateLimiter` = token bucket (`time.monotonic()`) + Semaphore.
  `Semaphore.release()` is sync. Exponential backoff 1s->16s, max 5 retries.
- **httpx**: One `AsyncClient` per service. Close via `await client.aclose()` (not `close()`).

---

## yfinance Wrapping Rules

Wrap in `_yf_call`, check empty returns, convert to models immediately, catch `Exception` broadly.

### yfinance Field Names (camelCase)

**`Ticker.info` dict keys:**
`dividendYield`, `trailingAnnualDividendYield`, `dividendRate`, `trailingAnnualDividendRate`,
`marketCap`, `sector`, `shortName`, `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`, `currentPrice`,
`previousClose`

**`option_chain(date)` DataFrame columns:**
`contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`, `change`,
`percentChange`, `volume`, `openInterest`, `impliedVolatility`, `inTheMoney`,
`contractSize`, `currency`

**NOT in chain data:** delta, gamma, theta, vega, rho -- **yfinance provides NO Greeks**.
`pricing/dispatch.py` is the sole source.

### Options Chain Column Mapping

| yfinance Column | OptionContract Field | Conversion |
|----------------|---------------------|------------|
| `strike` | `strike` | `Decimal(str(value))` |
| `lastPrice` | `last` | `Decimal(str(value))` |
| `bid` | `bid` | `Decimal(str(value))` |
| `ask` | `ask` | `Decimal(str(value))` |
| `volume` | `volume` | `safe_int(value) or 0` |
| `openInterest` | `open_interest` | `safe_int(value) or 0` |
| `impliedVolatility` | `market_iv` | `float` (already annualized -- do NOT re-annualize) |

**Fields set by service, not yfinance:**
- `ticker` -- passed as argument
- `option_type` -- `OptionType.CALL` or `.PUT` based on `.calls` vs `.puts`
- `expiration` -- from the expiration date argument
- `exercise_style` -- `ExerciseStyle.AMERICAN` for all U.S. equity options
- `greeks` -- always `None` (populated later by `pricing/dispatch.py`)

---

## Dividend Waterfall

3-tier waterfall in `market_data.py`. Guarantees `float` output (never `None`).

| Tier | yfinance Key | Guard | Source Enum |
|------|-------------|-------|-------------|
| 1 | `info.get("dividendYield")` | `is not None` | `DividendSource.FORWARD` |
| 2 | `info.get("trailingAnnualDividendYield")` | `is not None` | `DividendSource.TRAILING` |
| 3 | `sum(get_dividends("1y")) / price` | `sum > 0` | `DividendSource.COMPUTED` |
| 4 | `0.0` (fallback) | always | `DividendSource.NONE` |

**CRITICAL**: Fall-through condition is `value is None`, NOT falsy. `0.0` is valid data
for growth stocks. Checking `if not value:` skips `0.0` and corrupts provenance.

Cross-validation: when both yield and dollar-rate available, warn if divergence > 20%.

---

## Caching

### TTL Constants (named, not magic numbers)

| Data | Market Hours | After Hours |
|------|-------------|-------------|
| OHLCV | permanent | permanent |
| Chain | 5 min | 1 hr |
| Quote | 1 min | 5 min |
| Fundamentals | 24 hrs | 24 hrs |
| Reference (FRED, universe) | 24 hrs | 24 hrs |
| Failure | 24 hrs | 24 hrs |

### Two-Tier Architecture

- **In-memory**: LRU dict (max 1000). Short-TTL data.
- **SQLite**: WAL mode. Persistent data (OHLCV, fundamentals).
- Key format: `{source}:{type}:{ticker}:{params}`
- Market hours: 9:30-16:00 ET via `zoneinfo.ZoneInfo("America/New_York")`.

---

## Liquidity Filtering (Service Layer)

Basic filters in `options_data.py`. Advanced filtering (spread, delta) is in
`scoring/contracts.py` -- not here.

- OI >= `config.min_oi`, volume >= `config.min_volume`
- Reject contracts where BOTH bid AND ask are zero (truly dead)
- **Zero-bid exemption**: bid=0 / ask>0 passes (contract may still be valid)

---

## Error Strategy

| Error Source | Exception | Behavior |
|-------------|-----------|----------|
| Ticker not found | `TickerNotFoundError(ticker)` | Raise immediately |
| Empty DataFrame | `InsufficientDataError(ticker, reason)` | Raise after validation |
| Timeout / network | `DataSourceUnavailableError(source, detail)` | Raise (retry in batch) |
| FRED / CBOE unreachable | `DataSourceUnavailableError(source, detail)` | Fallback + WARNING log |
| Rate limit after max retries | `RateLimitExceededError(source, detail)` | Raise |
| FRED any error | -- | **Never raises** -- returns fallback rate |

All from `utils/exceptions.py`. Never bare `except:`. Always specific types.

---

## Safe Type Converters (`helpers.py`)

`safe_decimal()`, `safe_int()`, `safe_float()` -- return None on failure.
`safe_float` rejects NaN/Inf via `math.isfinite()`. All log at DEBUG.

---

## What Claude Gets Wrong Here (Fix These)

1. **Returning raw dicts or DataFrames** -- Every service method returns a Pydantic model.
2. **`to_thread(fn())` not `to_thread(fn, *args)`** -- Former runs synchronously on current thread.
3. **Forgetting `return_exceptions=True`** -- One failure cancels entire batch.
4. **httpx clients per-request** -- One per service. Create in `__init__`, close in `close()`.
5. **Forgetting `await db.commit()`** -- aiosqlite does NOT auto-commit.
6. **`time.time()` for rate limiting** -- Use `time.monotonic()` (clock adjustment immune).
7. **Assuming yfinance provides Greeks** -- Only `impliedVolatility`. Greeks from `pricing/dispatch.py`.
8. **Re-annualizing `impliedVolatility`** -- Already annualized. Pass through as `market_iv`.
9. **Falsy check for dividend waterfall** -- `if not value:` skips `0.0`. Use `is None`.
10. **`await semaphore.release()`** -- `release()` is synchronous. Don't await.
11. **Forgetting `strict=True` on `zip`** -- Use with gather results.
