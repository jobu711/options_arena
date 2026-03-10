---
name: service-layer-unification
description: ServiceBase ABC to unify caching, retry, rate limiting, and close() lifecycle across 7 data-fetching services
status: planned
created: 2026-03-09T22:00:00Z
---

# PRD: service-layer-unification

## Executive Summary

Extract a `ServiceBase` ABC into `services/base.py` that unifies the shared infrastructure
(cache-first fetch, retry with rate limiting, yfinance thread bridging, DI constructor,
`close()` lifecycle) repeated across 7 data-fetching services. Each service currently wires
~50 lines of identical boilerplate independently. The ABC is a **mixin** — no abstract
methods, no behavioral contract change — so migration is incremental and consumer-invisible.

The `ChainProvider` protocol already proves protocol-based abstraction works in this layer.
`ServiceBase` applies the same principle to the DI + caching + retry infrastructure.

## Problem Statement

The `services/` module has 7 data-fetching service classes that each independently implement:

1. **DI constructor** (9-21 lines) — `config`, `cache`, `limiter` assignment + logger creation
2. **`close()` lifecycle** (2-7 lines) — httpx `aclose()` or explicit no-op
3. **Cache-first fetch** (8-15 lines, repeated 29 times) — key format, cache get, deserialize,
   fetch on miss, serialize, cache set with TTL
4. **yfinance thread bridge** (17-24 lines, 2 nearly identical implementations) —
   `asyncio.to_thread()` + `wait_for()` + error mapping to `DataSourceUnavailableError`
5. **Retry with rate limiting** (5-8 lines per call, 18+ invocations) — delegation to
   `fetch_with_limiter_retry()` with per-service defaults

This produces:

- **~350 lines of duplicated infrastructure** across 7 files
- **Inconsistent cache key formats** (`yf:ohlcv:AAPL:1y` vs `cboe:chain:AAPL:2024-06-21`)
- **Inconsistent error handling** — some services catch `Exception`, others catch specific types
- **Friction adding new providers** — each new service requires copy-pasting the same 50-line
  init/cache/retry/close skeleton
- **Divergent `_yf_call` implementations** — `MarketDataService` and `YFinanceChainProvider`
  have nearly identical 24-line methods

## User Stories

### US1: Developer adds a new data service
**As** a developer adding a new external data provider,
**I want** to inherit shared caching, retry, and lifecycle infrastructure,
**So that** I only write the provider-specific fetch logic, not 50 lines of boilerplate.

**Acceptance criteria:**
- New service inherits `ServiceBase[MyConfig]` and gets cache, retry, close for free
- Only provider-specific methods need implementation
- Constructor signature is backward compatible with existing DI pattern
- Less than 15 lines of boilerplate per new service (down from ~50)

### US2: Maintainer fixes a caching bug
**As** a maintainer debugging a cache serialization issue,
**I want** cache-first fetch logic in one place,
**So that** a fix applies to all 7 services without editing 29 methods across 7 files.

**Acceptance criteria:**
- Cache-first fetch logic lives in `ServiceBase._cached_fetch()`
- All 7 services delegate to the shared method
- Cache key format is standardized via a consistent pattern
- Single point of change for serialization/deserialization

### US3: Developer migrates an existing service
**As** a developer migrating `FredService` to `ServiceBase`,
**I want** the migration to be a pure refactor with zero consumer impact,
**So that** CLI, API, scan pipeline, and tests require no changes.

**Acceptance criteria:**
- `FredService.__init__` signature unchanged (backward compatible)
- All public method signatures unchanged
- All existing tests pass without modification
- Consumer code (`commands.py`, `deps.py`, `pipeline.py`) unchanged

## Requirements

### Functional Requirements

#### FR1: ServiceBase ABC (`services/base.py`)

```python
class ServiceBase(Generic[ConfigT]):
    """Mixin ABC for data-fetching services with shared infrastructure."""

    def __init__(
        self,
        config: ConfigT,
        cache: ServiceCache,
        limiter: RateLimiter | None = None,
    ) -> None: ...

    async def close(self) -> None: ...  # default no-op

    async def _cached_fetch[T: BaseModel](
        self,
        key: str,
        model_type: type[T],
        factory: Callable[[], Awaitable[T]],
        ttl: int,
        deserializer: Callable[[bytes], T] | None = None,
    ) -> T: ...

    async def _retried_fetch[T](
        self,
        fn: Callable[..., Awaitable[T]],
        *args: object,
        max_attempts: int = 3,
        **kwargs: object,
    ) -> T: ...

    async def _yf_call[T](
        self,
        fn: Callable[..., T],
        *args: object,
        timeout: float,
        **kwargs: object,
    ) -> T: ...
```

**Design decisions:**
- `Generic[ConfigT]` where `ConfigT: BaseModel` — handles heterogeneous config types
  (`ServiceConfig`, `OpenBBConfig`, `IntelligenceConfig`, `FinancialDatasetsConfig`)
- **Mixin, not contract** — no `@abstractmethod`. Services opt into helpers they need.
- `__init__` stores `self._config`, `self._cache`, `self._limiter`, `self._log`
- `close()` is a default no-op. Services with httpx clients override it.
- `_cached_fetch()` eliminates ~25 of 29 cache-first blocks. Takes a zero-arg async factory,
  handles cache key lookup, deserialization via `model_type.model_validate_json()`,
  serialization via `model.model_dump_json().encode()`, and TTL-based cache set.
  Optional `deserializer` callback overrides default deserialization for custom patterns
  (batch list decode, scalar values, legacy formats). When provided, `deserializer(cached)`
  is called instead of `model_type.model_validate_json(cached)`.
- `_retried_fetch()` delegates to existing `fetch_with_limiter_retry()` from `helpers.py`.
  Passes `self._limiter` automatically.
- `_yf_call()` deduplicates the `asyncio.to_thread() + wait_for()` pattern. Takes an
  explicit `timeout: float` parameter (required, not optional). Callers pass their config's
  timeout value. Maps all exceptions to `DataSourceUnavailableError`.

#### FR2: `_cached_fetch()` — Unified Cache-First Pattern

Current pattern (repeated 29 times across 8 files):
```python
cache_key = f"yf:ohlcv:{ticker}:{period}"
cached = await self._cache.get(cache_key)
if cached is not None:
    return OHLCVData.model_validate_json(cached)
result = await self._fetch_ohlcv_raw(ticker, period)
await self._cache.set(cache_key, result.model_dump_json().encode(), ttl=TTL)
return result
```

Unified pattern (default model serde):
```python
return await self._cached_fetch(
    key=f"yf:ohlcv:{ticker}:{period}",
    model_type=OHLCVData,
    factory=lambda: self._fetch_ohlcv_raw(ticker, period),
    ttl=TTL,
)
```

Unified pattern (custom deserializer for batch/list/scalar):
```python
return await self._cached_fetch(
    key=f"yf:chain:{ticker}:{expiration.isoformat()}",
    model_type=OptionContract,  # used for serialization only
    factory=lambda: self._fetch_chain_raw(ticker, expiration),
    ttl=TTL,
    deserializer=lambda cached: _cache_bytes_to_contracts(cached),
)
```

**Serialization handling:**
- **Default** (no `deserializer`): `model_type.model_validate_json(cached)` /
  `model.model_dump_json().encode()` — covers ~15 blocks (direct single-model pattern)
- **Custom `deserializer`**: caller-provided `Callable[[bytes], T]` for batch list decode,
  scalar values, or legacy formats — covers ~10 additional blocks
- **Remaining inline** (~4 blocks): FredService triple-tier cache and CBOE batch pre-cache
  have unique enough patterns to stay inline

#### FR3: `_yf_call()` — Unified yfinance Thread Bridge

Current duplicated pattern (2 nearly identical implementations in `MarketDataService` and `YFinanceChainProvider`):
```python
async def _yf_call(self, fn, *args, timeout: float, **kwargs):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise DataSourceUnavailableError(...) from exc
    except Exception as exc:
        raise DataSourceUnavailableError(...) from exc
```

Unified: single implementation in `ServiceBase` with explicit `timeout: float` parameter
(required, not optional). Callers pass their config's timeout value directly, e.g.
`self._yf_call(fn, *args, timeout=self._config.yfinance_timeout)`. This is type-safe
across all config types — no duck-typed `getattr`. Services that don't use yfinance
simply don't call it. `IntelligenceService`'s raw `asyncio.to_thread()` calls will be
migrated to use `self._yf_call()` for consistent error mapping and timeout handling.

#### FR4: Constructor Backward Compatibility

All 7 services currently have different `__init__` signatures with varying parameter counts.
`ServiceBase.__init__` takes the common triple (`config`, `cache`, `limiter`). Services with
additional parameters (e.g., `OptionsDataService` needs `pricing_config`, `provider`,
`openbb_config`) call `super().__init__(config, cache, limiter)` and handle extras themselves.

**No consumer changes required** — constructors remain backward compatible because:
- Positional args stay in the same order
- Additional kwargs stay service-specific
- Default `limiter=None` matches `FredService` (no rate limiting needed)

#### FR5: Error Contract Preservation

Error behavior stays per-service, NOT enforced by ABC:
- **Raise services**: `MarketDataService`, `OptionsDataService`, `FredService`, `UniverseService`
  — raise `DataSourceUnavailableError`, `TickerNotFoundError`, etc.
- **Never-raise services**: `OpenBBService`, `IntelligenceService` — return `None` on any error
- `ServiceBase` does not mandate either pattern. Services override `_cached_fetch` error
  handling or wrap calls in try/except as they do today.

### Non-Functional Requirements

#### NFR1: Zero Consumer Impact
- CLI `commands.py` — no changes (constructors backward compatible)
- API `app.py` / `deps.py` — no changes
- Scan `pipeline.py` — no changes
- All existing tests pass without modification

#### NFR2: Incremental Migration
- Services migrate one at a time. Mixed state (some on ServiceBase, some standalone) is valid.
- No big-bang refactor. Each migration is a separate PR.

#### NFR3: Test Coverage
- `ServiceBase` itself gets dedicated unit tests (cache hit/miss, retry, yf_call timeout)
- Each migrated service retains its existing test suite unchanged
- Integration test verifies all 7 services work together post-migration

#### NFR4: Performance
- Zero runtime overhead — `_cached_fetch` replaces inline code, not adds a layer
- No additional async overhead (same `await` count per operation)

## Detailed Design

### ServiceBase ABC Specification

```
services/base.py (new file, ~120 lines)
    class ServiceBase(Generic[ConfigT])
        __init__(config, cache, limiter=None)
        close() -> None                          # default no-op
        _cached_fetch(key, model_type, factory, ttl) -> T
        _retried_fetch(fn, *args, **kwargs) -> T
        _yf_call(fn, *args, **kwargs) -> T
```

### 7 Services In Scope

| Service | Config Type | Uses `_cached_fetch` | Uses `_yf_call` | Uses `_retried_fetch` | Overrides `close()` |
|---------|------------|---------------------|-----------------|----------------------|-------------------|
| `MarketDataService` | `ServiceConfig` | Yes (6 methods) | Yes | Yes | No (log-only) |
| `OptionsDataService` | `ServiceConfig` | Yes (2 methods) | Via providers | Yes | Yes (provider cleanup) |
| `FredService` | `ServiceConfig` | Yes (1 method) | No (httpx) | No | Yes (httpx `aclose`) |
| `UniverseService` | `ServiceConfig` | Yes (6 methods) | No (httpx) | Yes | Yes (httpx `aclose`) |
| `OpenBBService` | `OpenBBConfig` | Yes (3 methods) | No (SDK) | No | No (no-op) |
| `IntelligenceService` | `IntelligenceConfig` | Yes (5 methods) | Yes | Yes | No (no-op) |
| `FinancialDatasetsService` | `FinancialDatasetsConfig` | Yes (3 methods) | No (httpx) | Yes | Yes (httpx `aclose`) |

### Out of Scope

| Class | Reason |
|-------|--------|
| `HealthService` | Different pattern — check methods (ping/verify), not data fetch methods |
| `OutcomeCollector` | Composite service that orchestrates other services, not a data fetcher |
| `YFinanceChainProvider` | Implements `ChainProvider` protocol, not a service. Owned by `OptionsDataService` |
| `CBOEChainProvider` | Implements `ChainProvider` protocol, not a service |

### Migration Example: FredService

**Before** (~96 lines):
```python
class FredService:
    def __init__(self, config: ServiceConfig, pricing_config: PricingConfig,
                 cache: ServiceCache) -> None:
        self._config = config
        self._pricing_config = pricing_config
        self._cache = cache
        self._log = logging.getLogger(__name__)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(config.request_timeout))

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_risk_free_rate(self) -> float:
        cache_key = "fred:risk_free_rate"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return float(cached.decode())
        # ... fetch from FRED API ...
        await self._cache.set(cache_key, str(rate).encode(), ttl=TTL_FRED)
        return rate
```

**After** (~70 lines, ~27% reduction):
```python
class FredService(ServiceBase[ServiceConfig]):
    def __init__(self, config: ServiceConfig, pricing_config: PricingConfig,
                 cache: ServiceCache) -> None:
        super().__init__(config, cache, limiter=None)
        self._pricing_config = pricing_config
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(config.request_timeout))

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_risk_free_rate(self) -> float:
        # FredService caches a scalar, not a model — keeps inline caching
        # (or uses _cached_fetch with a wrapper model)
        ...
```

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Boilerplate reduction | -300+ lines across 7 services | `wc -l` before/after diff |
| Consumer changes | Zero | `git diff` on `commands.py`, `deps.py`, `pipeline.py` = empty |
| Test pass rate | 100% existing tests pass without modification | `pytest tests/ -q` |
| New test coverage | 30+ tests for `ServiceBase` itself | `pytest tests/unit/services/test_base.py` |
| Cache-first dedup | ~25 of 29 cache blocks replaced by `_cached_fetch` calls | Grep count |
| `_yf_call` dedup | 2 implementations → 1 in base | Grep count |
| Migration completeness | 7/7 services inherit `ServiceBase` | `grep "ServiceBase" services/*.py` |

## Constraints & Assumptions

- **Python 3.13+**: Can use `type` aliases, `Generic` with modern syntax, PEP 695 generics
- **No `__aenter__`/`__aexit__`**: Explicit `close()` pattern preserved (project convention)
- **httpx client stays per-service**: Client configs are too different (timeouts, limits, base URLs)
  to centralize. Only `close()` lifecycle and DI pattern are unified.
- **Custom serde via callback**: `_cached_fetch` default handles single-model serialization.
  Services with custom patterns (list decode, scalar, legacy) pass a `deserializer` callback.
  No separate `_cached_fetch_list()` needed.
- **`helpers.py` unchanged**: `fetch_with_limiter_retry()` stays in `helpers.py`. `_retried_fetch`
  is a thin wrapper that passes `self._limiter` automatically.
- **No behavioral changes**: This is a pure refactor. Every service method produces identical
  output before and after migration.

## Out of Scope

- **HealthService migration** — different pattern (health checks, not data fetching)
- **OutcomeCollector migration** — composite service, orchestrates services
- **ChainProvider unification** — already has its own protocol pattern
- **httpx client pooling** — configs too different across services
- **`__aenter__`/`__aexit__` context manager** — project uses explicit `close()`
- **List-model caching** — handled via `deserializer` callback, no separate method needed
- **Cache key standardization** — keys stay service-defined (too many formats to unify safely)

## Dependencies

### Internal
- **`helpers.py`** — `fetch_with_limiter_retry()`, `safe_*` converters (unchanged, reused)
- **`cache.py`** — `ServiceCache` (unchanged, passed via DI)
- **`rate_limiter.py`** — `RateLimiter` (unchanged, passed via DI)
- **`models/`** — All Pydantic models (unchanged, used in `_cached_fetch` type params)
- **All 7 service classes** — migrated incrementally

### External
- None — pure internal refactor, no new dependencies

## Implementation Phases

### Wave 1: Foundation (4 issues)
1. **Create `services/base.py`** — `ServiceBase` ABC with `__init__`, `close()`,
   `_cached_fetch()`, `_retried_fetch()`, `_yf_call()`
2. **Unit tests for `ServiceBase`** — cache hit/miss, retry success/failure, yf_call
   timeout/error mapping, close lifecycle
3. **Update `services/CLAUDE.md`** — document new base class, migration pattern
4. **Update `services/__init__.py`** — re-export `ServiceBase`

### Wave 2: Simple Migrations (5 issues, parallelizable)
5. **Migrate `FredService`** — simplest (no limiter, httpx only)
6. **Migrate `OpenBBService`** — simple (no httpx, no yf_call)
7. **Migrate `IntelligenceService`** — moderate (yf_call + never-raises)
8. **Migrate `FinancialDatasetsService`** — moderate (httpx + cache)
9. **Migrate `UniverseService`** — moderate (httpx + cache + limiter)

### Wave 3: Complex Migrations (2 issues)
10. **Migrate `MarketDataService`** — complex (5 cached methods, yf_call, most used service)
11. **Migrate `OptionsDataService`** — complex (provider delegation, pricing config, most
    intricate init)

### Wave 4: Cleanup & Verification (2-3 issues)
12. **Integration test** — all 7 services instantiated together, verifying DI and close lifecycle
13. **Remove dead code** — delete standalone `_yf_call` methods, inline cache blocks that
    were replaced
14. *(Optional)* **Migrate remaining inline cache blocks** — FredService triple-tier + CBOE batch

## Effort Estimate

**Total: L (3-5 days)**
- Wave 1: S (3-4 hours) — ABC + tests
- Wave 2: M (1-2 days) — 5 parallel simple migrations
- Wave 3: M (1 day) — 2 complex migrations
- Wave 4: S (2-3 hours) — cleanup + integration test
