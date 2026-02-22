# CLAUDE.md — Data Services

## Purpose
The ONLY layer that touches external APIs and data sources. Everything else receives
typed models — never raw dicts, DataFrames, or JSON.

## Files

## Architecture Rule
Analysis, indicator, agent, and reporting code **never imports data source libraries**.
Only `services/` imports `yfinance`, `httpx`, or API clients.

## yfinance Wrapping
yfinance is convenient but unreliable. Every call must be wrapped:
1. Validate ticker exists.
2. Check returned DataFrame is not empty.
3. Normalize column names to known schema.
4. Convert to typed models (`Quote`, `OHLCV`) before returning.
5. Catch `Exception` broadly (yfinance raises inconsistent types) → re-raise as `DataFetchError`.
6. Verify date range coverage — yfinance silently returns less than requested.

### Options Chain Fetching
- yfinance `option_chain()` returns separate calls/puts DataFrames.
- Normalize to `list[OptionContract]` immediately.
- Greek values from yfinance are often missing or stale — flag when absent.
- Bid/ask of 0.00 means no market — filter these out or flag as illiquid.
- Implied volatility from yfinance is already annualized — don't annualize again.

## httpx Configuration
```python
client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
```
- One shared `AsyncClient` per service. Don't create per-request.
- Always close via context manager or `finally`.

## Caching
| Data Type | TTL | Storage |
|---|---|---|
| Historical daily OHLCV | Permanent (immutable) | SQLite |
| Option chains | 5-15 min (market hours), 1 hr (after hours) | In-memory |
| Intraday quotes | 1-5 min | In-memory |
| IV rank / IV percentile | 1 hour | SQLite |
| Company fundamentals | 24 hours | SQLite |
| Earnings dates | 24 hours | SQLite |

Cache key format: `{source}:{type}:{ticker}:{params}` — e.g., `yf:chain:AAPL:2025-04-18`.
Cache-first pattern: check cache → fetch if miss → store → return.

## Rate Limiting
- `asyncio.Semaphore` for concurrency + token bucket for rate.
- yfinance: ~2 req/s (conservative). Free APIs: respect documented daily limits.
- On 429: read `Retry-After` header if present. Otherwise backoff: 1s → 2s → 4s → 8s → 16s, max 5 retries.
- Batch fetches: `asyncio.gather(*tasks, return_exceptions=True)`. Collect failures separately:
  ```python
  successes = {t: r for t, r in zip(tickers, results) if not isinstance(r, Exception)}
  failures = {t: r for t, r in zip(tickers, results) if isinstance(r, Exception)}
  ```

## Market Hours
- US options: 9:30 AM - 4:00 PM ET, Monday-Friday.
- Use `zoneinfo.ZoneInfo("America/New_York")` — never naive datetimes.
- Longer cache TTLs outside market hours.
- Don't request real-time quotes after close — use previous close.
- Handle market holidays (maintain calendar or fetch from source).

## Health Checks (`health.py`)
Pre-flight at startup:
- Ollama: hit `/api/tags` endpoint.
- Anthropic: minimal auth check.
- Data source: fetch known ticker (SPY).
Return a typed `HealthStatus` model. Fail fast with clear error if anything is down.

## Custom Exceptions

## What Claude Gets Wrong Here (Fix These)
- Don't return raw dicts or JSON from service functions — always convert to typed Pydantic models (`Quote`, `OHLCV`, `OptionContract`, etc.) before returning. No `dict[str, Any]`, no `dict[str, float]`, no raw DataFrames crossing the service boundary.
- Don't call yfinance from analysis/indicator code — services only.
- Don't trust yfinance returns — validate shape, columns, date range.
- Don't create new httpx clients per request — share.
- Don't cache option chains with long TTLs during market hours.
- Don't assume yfinance IV needs annualizing — it's already annualized.
- Don't filter out zero-bid options silently — flag them as illiquid.
- Don't let one failed ticker crash a batch fetch.
- Don't use naive datetimes for market hours.

