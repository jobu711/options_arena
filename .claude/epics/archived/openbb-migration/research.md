# Research: openbb-migration

## PRD Summary

Migrate option chain fetching from yfinance (sole provider) to CBOE via OpenBB Platform SDK as primary provider, retaining yfinance as automatic fallback. Introduces a `ChainProvider` protocol abstraction, native Greeks from CBOE (bypassing local BAW/BSM computation), bid/ask IV, and a validation phase before cutover. Applies to both scan pipeline Phase 3 and the debate path. Builds on Epic A (openbb-integration, PR #184) which established `OpenBBService`, guarded imports, `OpenBBConfig`, and the never-raises contract.

## Relevant Existing Modules

| Module | Relationship | Key Files | CLAUDE.md Constraints |
|--------|-------------|-----------|----------------------|
| `services/` | Primary target — `OptionsDataService` refactored with `ChainProvider` protocol, `CBOEChainProvider` added | `options_data.py`, `openbb_service.py`, `health.py`, `__init__.py` | Typed boundary (return Pydantic models only), async-first, DI constructor, explicit `close()`, batch fail-safe via `gather(return_exceptions=True)`, never-raises on fallback sources |
| `models/` | Extend `OptionContract` with `bid_iv`, `ask_iv`, `greeks_source`; extend `OpenBBConfig` with CBOE fields | `options.py`, `config.py`, `enums.py`, `__init__.py` | `frozen=True` on snapshots, `math.isfinite()` on all float validators, `field_serializer` on Decimal fields, no logic/I/O |
| `scoring/` | Update `contracts.py` to skip local Greeks when CBOE provides them | `contracts.py` | Imports `pricing/dispatch` only (never `bsm`/`american` directly), no API calls, no services imports |
| `pricing/` | No changes — `dispatch.py` called as Tier 2 fallback only | `dispatch.py` | Pure math, no APIs, no pandas, returns `OptionGreeks` model |
| `scan/` | Phase 3 (`_phase_options`) uses `OptionsDataService` — transparent to provider abstraction | `pipeline.py` | Cannot import `pricing/` directly, cannot import `httpx`/`yfinance`/`print()`. Receives injected services via constructor. |
| `cli/` | Passes `OpenBBConfig` when constructing `OptionsDataService` | `commands.py` | Thin layer, service lifecycle in try/finally, sync Typer + `asyncio.run()` |
| `api/` | Passes `OpenBBConfig` when constructing `OptionsDataService` in lifespan | `app.py`, `deps.py` | App-scoped services in lifespan, DI via `Depends()` |

## Existing Patterns to Reuse

### 1. Async Wrapping (`_yf_call` pattern in `options_data.py`)
```python
async def _yf_call[T](self, fn: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.wait_for(
        asyncio.to_thread(fn, *args, **kwargs),
        timeout=self._config.yfinance_timeout,
    )
```
**Apply to**: `CBOEChainProvider` wrapping `obb.equity.options.chains()` calls.
**CRITICAL**: `to_thread(fn, *args)` — pass callable + args separately, NOT `to_thread(fn())`.

### 2. Guarded Import (`openbb_service.py`)
```python
def _get_obb() -> Any:
    try:
        from openbb import obb
        return obb
    except ImportError:
        logger.info("OpenBB SDK not installed — OpenBB features disabled")
        return None
```
**Apply to**: `CBOEChainProvider` uses same `_get_obb()` pattern (or imports from `openbb_service.py`).

### 3. Never-Raises Contract (`fred.py`, `openbb_service.py`)
Every public method catches exceptions, returns fallback/None, logs warnings. OpenBB chain provider raises `DataSourceUnavailableError` (caught by orchestrating layer for fallback).

### 4. Batch Isolation (`options_data.py`)
```python
results = await asyncio.gather(*tasks, return_exceptions=True)
for exp, result in zip(expirations, results, strict=True):
    if isinstance(result, BaseException):
        logger.warning(...)  # Skip failed, continue rest
```

### 5. Class-Based DI (all services)
Constructor: `__init__(self, config, cache, limiter)`. Explicit `async def close()`. CLI/API creates and closes.

### 6. Two-Tier Caching (`market_data.py`, `options_data.py`)
In-memory LRU + SQLite WAL. Cache key format: `"cboe:chain:{ticker}:{expiration.isoformat()}"`. Market-hours-aware TTL.

### 7. Field Mapping + Safe Converters (`options_data.py`)
`safe_decimal()`, `safe_int()`, `safe_float()` from `helpers.py` for converting SDK response fields to typed model fields. All return fallback (0 or 0.0) on invalid input.

### 8. Frozen Model Copy (`scoring/contracts.py`)
```python
new_contract = contract.model_copy(update={"greeks": greeks, "market_iv": sigma})
```
Since `OptionContract` is frozen, mutations happen via `model_copy(update={...})`.

## Existing Code to Extend

### `src/options_arena/services/options_data.py`
**Current state**: Monolithic yfinance-only service with 4 public methods:
- `fetch_expirations(ticker) -> list[date]`
- `fetch_chain(ticker, expiration) -> list[OptionContract]`
- `fetch_chain_all_expirations(ticker) -> list[ExpirationChain]`
- `close() -> None`

**Constructor**: `__init__(self, config: ServiceConfig, pricing_config: PricingConfig, cache: ServiceCache, limiter: RateLimiter)`

**Change**: Extract yfinance logic into `YFinanceChainProvider`, add `ChainProvider` protocol, add provider list with fallback in `OptionsDataService`. Extend constructor with `openbb_config: OpenBBConfig | None = None`.

### `src/options_arena/models/options.py`
**Current `OptionContract` fields**: ticker, option_type, strike, expiration, bid, ask, last, volume, open_interest, exercise_style, market_iv, greeks (None default). Computed: mid, spread, dte.

**Change**: Add `bid_iv: float | None = None`, `ask_iv: float | None = None`, `greeks_source: GreeksSource | None = None`. Add validators: `math.isfinite() + >= 0` on bid_iv/ask_iv.

### `src/options_arena/models/enums.py`
**Existing**: `GreeksSource(StrEnum)` already defined with `COMPUTED = "computed"` and `MARKET = "market"`. Currently unused.

**Change**: Wire into `OptionContract.greeks_source` field.

### `src/options_arena/models/config.py`
**Current `OpenBBConfig`**: `enabled`, `fundamentals_enabled`, `unusual_flow_enabled`, `news_sentiment_enabled`, cache TTLs, `request_timeout`, `max_retries`. Already nested in `AppSettings.openbb`.

**Change**: Add `cboe_chains_enabled: bool = False`, `chains_cache_ttl: int = 60`, `chain_validation_mode: bool = False`.

### `src/options_arena/scoring/contracts.py`
**Current `recommend_contracts()` flow**: filter → select_expiration → `compute_greeks()` (always calls `pricing/dispatch.py`) → select_by_delta → return 0-1 contracts.

**Change**: `compute_greeks()` checks `if contract.greeks is not None` → skip dispatch, use existing Greeks. Set `greeks_source = GreeksSource.COMPUTED` when locally computed.

### `src/options_arena/cli/commands.py` (line ~149)
**Current**: `OptionsDataService(settings.service, settings.pricing, cache, limiter)`
**Change**: `OptionsDataService(settings.service, settings.pricing, cache, limiter, openbb_config=settings.openbb)`

### `src/options_arena/api/app.py` (line ~66)
**Current**: `OptionsDataService(settings.service, settings.pricing, cache, limiter)`
**Change**: Same — pass `openbb_config=settings.openbb`.

### `src/options_arena/services/health.py`
**Change**: Add `check_cboe_chains()` probe (test fetch with known ticker).

## Potential Conflicts

### 1. OptionContract Frozen + New Fields
Adding `bid_iv`, `ask_iv`, `greeks_source` to a frozen model is safe (they have `None` defaults). However, every test that constructs `OptionContract` with positional args will break if field order changes.
**Mitigation**: New fields placed at end with defaults. Existing tests use keyword args (verified in test patterns). No positional breakage.

### 2. OptionsDataService Constructor Change
Adding `openbb_config` parameter changes the constructor signature. Every call site (CLI, API, tests) needs updating.
**Mitigation**: Use `openbb_config: OpenBBConfig | None = None` default — backward compatible. Existing tests pass without it. Only CLI/API call sites add the new param.

### 3. compute_greeks() Behavioral Change
Currently unconditionally calls `pricing/dispatch.py`. Skipping when `greeks is not None` changes behavior for any contract that arrives with pre-populated Greeks.
**Mitigation**: No contract currently arrives with Greeks populated (yfinance always returns `None`). Only CBOE contracts will have Greeks. Existing code path unchanged when `cboe_chains_enabled=False`.

### 4. Cache Key Collision
yfinance uses `"yf:chain:{ticker}:{exp}"`. CBOE must use different prefix.
**Mitigation**: Use `"cboe:chain:{ticker}:{exp}"` — different namespace, no collision.

### 5. Greeks Value Differences (CBOE vs BAW/BSM)
CBOE native Greeks may differ from locally computed values. During validation phase, both run — discrepancies could confuse scoring.
**Mitigation**: Phase 4 validation mode compares explicitly. `greeks_source` field lets downstream code know which source was used. Cutover is config-driven.

### 6. Scan Pipeline Timing
CBOE chain fetching may be slower/faster than yfinance. Different latency profile could affect scan timeout (`options_per_ticker_timeout`).
**Mitigation**: Phase 4 benchmarking. Timeout is config-driven (`ScanConfig.options_per_ticker_timeout`). Fallback to yfinance on timeout.

## Open Questions

1. **CBOE field names via OpenBB**: The exact column names returned by `obb.equity.options.chains(provider="cboe")` must be verified via Context7 before implementing the field mapping. The PRD mapping is estimated.

2. **CBOE expiration listing**: Does `obb.equity.options.chains(provider="cboe")` return all expirations in one call, or does it require a separate expiration listing endpoint? This affects whether `fetch_expirations()` needs a CBOE implementation.

3. **CBOE Greeks completeness**: Does CBOE always return all 5 Greeks (delta, gamma, theta, vega, rho)? Or are some fields optional/missing for certain strikes? This determines whether Tier 2 fallback needs to handle partial Greeks.

4. **Rate limiting on CBOE via OpenBB**: What are CBOE's rate limits through OpenBB? The scan pipeline fetches chains for 50 tickers concurrently. Need to know if a per-provider rate limiter or concurrency semaphore is required.

5. **CBOE data coverage**: Does CBOE via OpenBB cover all U.S. equity options, or only a subset? If coverage is narrower than yfinance, fallback frequency increases.

6. **GreeksSource on OptionGreeks vs OptionContract**: Should `greeks_source` live on `OptionContract` (tracking the chain source) or on `OptionGreeks` (tracking the Greeks computation source)? The PRD puts it on `OptionContract`, but `OptionGreeks` already has `pricing_model`. Recommend: `greeks_source` on `OptionContract` (tracks chain origin), `pricing_model` on `OptionGreeks` (tracks computation method — set to `None` or a new `MARKET` value for CBOE Greeks).

## Recommended Architecture

### Provider Layer Design

```
ChainProvider (Protocol)
├── CBOEChainProvider        # Primary: obb.equity.options.chains(provider="cboe")
│   ├── _get_obb()           # Guarded import (reuse from openbb_service.py)
│   ├── _map_cboe_row()      # CBOE fields → OptionContract
│   └── _map_cboe_greeks()   # CBOE Greeks → OptionGreeks
└── YFinanceChainProvider    # Fallback: extracted from existing OptionsDataService
    ├── _yf_call()           # Existing async wrapping
    └── _row_to_contract()   # Existing field mapping
```

### OptionsDataService Orchestration

```python
class OptionsDataService:
    def __init__(self, config, pricing_config, cache, limiter, openbb_config=None):
        self._providers: list[ChainProvider] = []
        if openbb_config and openbb_config.cboe_chains_enabled:
            cboe = CBOEChainProvider(openbb_config, cache, limiter)
            if cboe.available:  # SDK importable
                self._providers.append(cboe)
        self._providers.append(YFinanceChainProvider(config, pricing_config, cache, limiter))

    async def fetch_chain(self, ticker, expiration) -> list[OptionContract]:
        for provider in self._providers:
            try:
                return await provider.fetch_chain(ticker, expiration)
            except DataSourceUnavailableError:
                logger.warning("Provider %s failed for %s, trying next", provider, ticker)
        raise DataSourceUnavailableError("all_providers", "All chain providers exhausted")
```

### Three-Tier Greeks Resolution (in scoring/contracts.py)

```
Tier 1: contract.greeks is not None (from CBOE)     → use as-is, skip dispatch
Tier 2: contract.greeks is None                       → compute via pricing/dispatch.py
Tier 3: dispatch fails (ValueError, OverflowError)   → greeks = None, exclude from delta selection
```

### Data Flow (CBOE Enabled)

```
CLI/API
  └── OptionsDataService(openbb_config=settings.openbb)
        └── CBOEChainProvider.fetch_chain()
              └── obb.equity.options.chains(provider="cboe") via asyncio.to_thread
              └── _map_cboe_row() → OptionContract(greeks=OptionGreeks(...), greeks_source=MARKET)
        └── [fallback] YFinanceChainProvider.fetch_chain()
              └── OptionContract(greeks=None, greeks_source=None)
  └── scoring/contracts.py recommend_contracts()
        └── compute_greeks() checks contract.greeks is not None → skip dispatch
        └── select_by_delta() uses native CBOE delta
```

## Test Strategy Preview

### Existing Test Patterns

| Area | Pattern | File |
|------|---------|------|
| Service mocking | `patch("options_arena.services.options_data.yf")` with `MagicMock` ticker | `tests/unit/services/test_options_data.py` |
| Field mapping | `_make_chain_df()` builds DataFrame mimicking yfinance columns | `tests/unit/services/test_options_data.py` |
| Contract construction | `make_contract(**kwargs)` fixture with sensible defaults | `tests/conftest.py` |
| Greeks construction | `_make_greeks(delta=0.35, ...)` helper | `tests/unit/scoring/test_contracts.py` |
| Assertions | `pytest.approx(rel=1e-4)` for floats, `Decimal("185.00")` for prices | Both test files |
| Error isolation | Test mixed success/failure in `asyncio.gather` batch | `test_options_data.py` |

### New Test Files

| File | ~Count | Coverage |
|------|--------|----------|
| `tests/unit/services/test_chain_providers.py` | 25 | Protocol conformance, CBOE field mapping, fallback logic, config toggle |
| `tests/unit/services/test_cboe_greeks.py` | 25 | CBOE Greeks mapping, three-tier resolution, sanity checks, greeks_source |
| `tests/unit/models/test_option_contract_ext.py` | 10 | bid_iv/ask_iv validators, greeks_source field, backward compat |
| `tests/unit/scoring/test_contracts_cboe.py` | 10 | Skip local Greeks when CBOE provides them, native delta selection |
| `tests/integration/test_chain_migration.py` | 15 | End-to-end provider fallback, scan pipeline with mocked CBOE |

### Mocking Strategy

- **CBOE provider**: `patch("options_arena.services.cboe_provider._get_obb")` returning mock with `.equity.options.chains()` method
- **SDK unavailable**: `_get_obb()` returns `None` → `CBOEChainProvider.available = False` → not registered
- **CBOE failure at runtime**: Mock raises exception → fallback to yfinance
- **Partial Greeks**: Mock returns CBOE data with some Greeks fields as `None` → Tier 2 fills gaps
- **Parallel validation**: Both providers mocked, compare output structure (not values)

## Estimated Complexity

**L (Large)**

Justification:
- **2-3 new files**: `cboe_provider.py` (or inline in `options_data.py`), 5 test files
- **6-7 modified files**: `options_data.py` (major refactor), `options.py`, `config.py`, `enums.py` (minor), `contracts.py`, `commands.py`, `app.py`
- **~85 new tests** across 5 test files
- **All patterns exist**: DI, async wrapping, guarded imports, frozen models, batch isolation — this follows established templates
- **Key risk**: CBOE field mapping requires Context7 verification. Unknown schema could change scope.
- **No new architectural patterns**: Provider protocol is the one new abstraction, but Protocol pattern is standard Python
- **Phase 4 (validation)** is the most uncertain — depends on CBOE data quality and coverage
