# Research: service-layer-unification

## PRD Summary

Extract a `ServiceBase` ABC into `services/base.py` that unifies shared infrastructure
(cache-first fetch, retry with rate limiting, yfinance thread bridging, DI constructor,
`close()` lifecycle) across 7 data-fetching services. Pure refactor — zero consumer impact.

## Relevant Existing Modules

- `services/` — All 7 target services live here. No existing ABC. `ChainProvider` Protocol
  is the only abstraction precedent. 19 public re-exports in `__init__.py`.
- `services/cache.py` — `ServiceCache` with dual-tier (in-memory LRU + SQLite WAL).
  Interface: `get(key: str) -> bytes | None`, `set(key: str, value: bytes, ttl: int | None)`,
  `invalidate(key)`, `clear()`, `close()`, `ttl_for(data_type: str) -> int`.
- `services/rate_limiter.py` — `RateLimiter(rate, max_concurrent)`. Token bucket + semaphore.
  Async context manager. `acquire()` / `release()`.
- `services/helpers.py` — `fetch_with_limiter_retry[T](fn, *args, limiter, max_attempts=3,
  base_delay=1.0, max_delay=16.0, retryable=(DataSourceUnavailableError,), **kwargs) -> T`.
  Per-attempt limiter acquire, exponential backoff with jitter.
- `models/config.py` — Config types: `ServiceConfig`, `OpenBBConfig`, `IntelligenceConfig`,
  `FinancialDatasetsConfig`, `PricingConfig`. All are `BaseModel` subclasses.
- `cli/commands.py` — Creates services with explicit DI, closes in `finally` block.
- `api/app.py` — Creates services in `lifespan()`, stores on `app.state`, closes on shutdown.
- `api/deps.py` — `Depends()` providers that cast from `app.state`.

## Existing Patterns to Reuse

### 1. DI Constructor Pattern (all 7 services)
Every service takes `(config, cache, limiter)` via `__init__`. No global state.
`ServiceBase.__init__` standardizes this with `limiter: RateLimiter | None = None`
for FredService (the only service without a limiter).

### 2. ChainProvider Protocol (options_data.py)
`@runtime_checkable` Protocol with `fetch_expirations()` + `fetch_chain()`.
Proves protocol-based abstraction works in this layer. ServiceBase uses
inheritance (ABC mixin) instead — appropriate since it provides shared implementation,
not just a contract.

### 3. Cache-First Fetch (29 blocks across 8 files)
Five serialization variations found:

| Pattern | Services | Count |
|---------|----------|-------|
| Direct `model_validate_json(cached)` | OpenBB, Intelligence, FinancialDatasets | ~11 |
| Custom `_deserialize_*()` helper | MarketData (quote, ticker_info) | ~4 |
| `json.loads()` + loop `model_validate()` | OptionsData, MarketData (OHLCV) | ~4 |
| Scalar float with JSON/legacy decode | Fred (only) | 1 |
| CBOE batch pre-cache | CBOEChainProvider | ~3 |

**Implication**: `_cached_fetch[T: BaseModel]` covers ~15 of 29 blocks (direct model pattern).
Services with custom serialization (batch lists, scalar floats) keep inline caching initially.

### 4. yfinance Thread Bridge (2 implementations)
`MarketDataService._yf_call` and `YFinanceChainProvider._yf_call` are functionally
identical: `asyncio.to_thread(fn, *args, **kwargs)` + `wait_for(timeout)` +
`DataSourceUnavailableError` mapping. Both re-raise `DataFetchError` without wrapping.
Cosmetic difference only (`exc` vs `e` variable names).

### 5. Test Fixture Pattern
```python
@pytest.fixture
def cache(config: ServiceConfig) -> ServiceCache:
    return ServiceCache(config, db_path=None, max_size=100)  # in-memory only

@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(rate=1000.0, max_concurrent=100)  # fast for tests
```

## Service-by-Service Analysis

### Constructor Signatures

| Service | Config Type | Extra Params | Has Limiter |
|---------|------------|-------------|:-----------:|
| `MarketDataService` | `ServiceConfig` | — | Yes |
| `OptionsDataService` | `ServiceConfig` | `pricing_config: PricingConfig`, `*, provider: ChainProvider \| None`, `openbb_config: OpenBBConfig \| None` | Yes |
| `FredService` | `ServiceConfig` | `pricing_config: PricingConfig` | **No** |
| `UniverseService` | `ServiceConfig` | — | Yes |
| `OpenBBService` | `OpenBBConfig` | — | Yes |
| `IntelligenceService` | `IntelligenceConfig` | — | Yes |
| `FinancialDatasetsService` | `FinancialDatasetsConfig` | — | Yes |

### close() Implementations

| Service | Implementation | Substantive |
|---------|---------------|:-----------:|
| `MarketDataService` | `logger.debug(...)` only | No |
| `OptionsDataService` | Iterates `self._providers`, duck-type `getattr("close")` | **Yes** |
| `FredService` | `await self._client.aclose()` | **Yes** |
| `UniverseService` | `await self._client.aclose()` | **Yes** |
| `OpenBBService` | Docstring-only no-op | No |
| `IntelligenceService` | Docstring-only no-op | No |
| `FinancialDatasetsService` | `await self._client.aclose()` | **Yes** |

### Config `yfinance_timeout` Availability

| Config Type | Has `yfinance_timeout` | Timeout Field |
|-------------|:----------------------:|---------------|
| `ServiceConfig` | Yes (15.0) | `yfinance_timeout` |
| `OpenBBConfig` | No | `request_timeout: int = 15` |
| `IntelligenceConfig` | No | `request_timeout: float = 15.0` |
| `FinancialDatasetsConfig` | No | `request_timeout: float = 10.0` |

**Implication for `_yf_call()`**: Only services using `ServiceConfig` (MarketData, OptionsData,
Fred, Universe) can access `self._config.yfinance_timeout`. The PRD's duck-typed `getattr`
approach works but is not type-safe. Alternative: accept explicit `timeout` parameter,
let callers pass their config's timeout value.

## Potential Conflicts

### 1. FredService Triple-Tier Cache
FredService has a unique `CachedRate` NamedTuple for in-memory staleness-aware caching
of a scalar float, plus legacy plain-float deserialization support. This does NOT fit
`_cached_fetch[T: BaseModel]`. **Mitigation**: FredService keeps inline caching (PRD
already acknowledges this at line 303).

### 2. OptionsDataService Complex Init
Takes 6 parameters including keyword-only `provider` and `openbb_config`. Builds provider
list internally, may create extra YFinanceChainProvider for validation mode. `super().__init__`
handles the common 3; extras stay in the subclass. No conflict.

### 3. Batch/List Serialization
~8 cache blocks use `json.loads()` + loop `model_validate()` for lists. `_cached_fetch`
handles single models only. **Mitigation**: Deferred to `_cached_fetch_list()` follow-up.
These blocks keep inline caching.

### 4. CBOEChainProvider Not In Scope
CBOEChainProvider has 3 cache blocks but implements `ChainProvider` protocol, not
`ServiceBase`. Its cache blocks won't be deduplicated. This is intentional per the PRD's
out-of-scope section.

### 5. MarketDataService Has No Real close()
Only logs a debug message. ServiceBase's default no-op `close()` is sufficient.
No conflict — MarketDataService simply won't override `close()`.

## Resolved Design Decisions

1. **`_yf_call` timeout — explicit parameter (type-safe)**: `_yf_call()` requires an explicit
   `timeout: float` parameter. Callers pass their config's timeout value. No duck-typed
   `getattr`. This keeps the method type-safe across all config types.

2. **`_cached_fetch` — add `deserializer` callback**: `_cached_fetch` accepts an optional
   `deserializer: Callable[[bytes], T]` callback. Default behavior uses
   `model_type.model_validate_json(cached)` for standard single-model serde. Services with
   custom patterns (batch list decode, scalar float, legacy format) pass a custom deserializer.
   This raises coverage from ~15/29 to ~25/29 blocks (FredService triple-tier and CBOE
   batch pre-cache remain inline).

3. **IntelligenceService — migrate to `ServiceBase._yf_call()`**: IntelligenceService's raw
   `asyncio.to_thread()` calls will be migrated to use `self._yf_call(fn, *args, timeout=...)`.
   This gives it consistent error mapping to `DataSourceUnavailableError` and timeout handling.

## Recommended Architecture

```
ServiceBase(Generic[ConfigT])           # New ABC in services/base.py
    __init__(config, cache, limiter=None)
    close() -> None                      # default no-op
    _cached_fetch[T: BaseModel]()        # cache-first with model serde
    _retried_fetch[T]()                  # delegates to fetch_with_limiter_retry
    _yf_call[T]()                        # asyncio.to_thread + wait_for

MarketDataService(ServiceBase[ServiceConfig])
OptionsDataService(ServiceBase[ServiceConfig])
FredService(ServiceBase[ServiceConfig])
UniverseService(ServiceBase[ServiceConfig])
OpenBBService(ServiceBase[OpenBBConfig])
IntelligenceService(ServiceBase[IntelligenceConfig])
FinancialDatasetsService(ServiceBase[FinancialDatasetsConfig])
```

**Key design choices**:
- `Generic[ConfigT]` with no bound — config types are heterogeneous `BaseModel` subclasses
- Mixin with no `@abstractmethod` — services opt into helpers they need
- `_yf_call` takes explicit `timeout: float` parameter (no duck typing)
- `_cached_fetch` accepts optional `deserializer` callback for custom serde (~25/29 blocks)
- `close()` default no-op; 4 services override (Fred, Universe, FinancialDatasets, OptionsData)

## Test Strategy Preview

- **Existing tests**: ~20 test files in `tests/unit/services/` covering all 7 services
- **Mocking**: `ServiceCache(config, db_path=None)` for in-memory; `RateLimiter(1000.0, 100)` for fast tests
- **New tests**: `tests/unit/services/test_base.py` — cache hit/miss, retry success/failure,
  `_yf_call` timeout/error mapping, close lifecycle, generic type parameter validation
- **Migration tests**: Each migrated service's existing test suite must pass unchanged
- **Integration test**: All 7 services instantiated together, verify DI + close lifecycle

## Service Instantiation Points (Must Not Change)

### CLI (`cli/commands.py`)
```python
market_data = MarketDataService(settings.service, cache, limiter)
options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter, openbb_config=settings.openbb)
fred = FredService(settings.service, settings.pricing, cache)
universe_svc = UniverseService(settings.service, cache, limiter)
```

### API (`api/app.py` lifespan)
```python
market_data = MarketDataService(settings.service, cache, limiter)
options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter, openbb_config=settings.openbb)
fred = FredService(settings.service, settings.pricing, cache)
universe = UniverseService(settings.service, cache, limiter)
# Conditional:
openbb_svc = OpenBBService(settings.openbb, cache, limiter)
intelligence_svc = IntelligenceService(settings.intelligence, cache, limiter)
fd_svc = FinancialDatasetsService(config=settings.financial_datasets, cache=cache, limiter=limiter)
```

**These constructor calls must NOT change** — backward compatibility is a hard requirement.

## Estimated Complexity

**L (3-5 days)** — justified by:
- 7 services to migrate incrementally (each is a separate PR)
- 29 cache blocks to evaluate (15 directly convertible, 14 keep inline)
- 2 `_yf_call` implementations to consolidate
- ~30 new tests for ServiceBase itself
- Existing test suite (~20 files) must remain green throughout
- Zero consumer changes required (CLI, API, scan pipeline)
