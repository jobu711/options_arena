---
name: service-layer-unification
status: backlog
created: 2026-03-10T14:30:02Z
progress: 0%
prd: .claude/prds/service-layer-unification.md
github: https://github.com/jobu711/options_arena/issues/437
---

# Epic: service-layer-unification

## Overview

Extract a `ServiceBase` ABC mixin into `services/base.py` that unifies cache-first fetch,
retry with rate limiting, yfinance thread bridging, DI constructor, and `close()` lifecycle
across 7 data-fetching services. Pure refactor — zero consumer impact on CLI, API, or scan
pipeline. ~350 lines of duplicated infrastructure consolidated into one ~120-line base class.

## Architecture Decisions

1. **Mixin, not contract** — `ServiceBase` has no `@abstractmethod`. Services opt into
   helpers they need (`_cached_fetch`, `_retried_fetch`, `_yf_call`). No forced migration.
2. **`Generic[ConfigT]`** — Handles heterogeneous config types (`ServiceConfig`, `OpenBBConfig`,
   `IntelligenceConfig`, `FinancialDatasetsConfig`) without duck typing.
3. **Explicit `timeout: float` on `_yf_call`** — Callers pass their config's timeout value
   directly. Type-safe across all config types. No `getattr` duck typing.
4. **`deserializer` callback on `_cached_fetch`** — Default handles single-model serde via
   `model_validate_json`/`model_dump_json`. Custom callback for batch lists, scalars, legacy
   formats. Covers ~25 of 29 cache blocks. FredService triple-tier + CBOE batch stay inline.
5. **Backward-compatible constructors** — `super().__init__(config, cache, limiter)` handles
   the common triple. Service-specific extras (pricing_config, provider, openbb_config) stay
   in the subclass. No consumer changes.
6. **Error contract preserved per-service** — Raise services raise, never-raise services
   return None. ServiceBase doesn't enforce either pattern.

## Technical Approach

### New File: `services/base.py` (~120 lines)

```
ServiceBase(Generic[ConfigT])
    __init__(config: ConfigT, cache: ServiceCache, limiter: RateLimiter | None = None)
    close() -> None                          # default no-op
    _cached_fetch[T: BaseModel](key, model_type, factory, ttl, deserializer?) -> T
    _retried_fetch[T](fn, *args, max_attempts=3, **kwargs) -> T
    _yf_call[T](fn, *args, timeout: float, **kwargs) -> T
```

### Migration Pattern (per service)

1. Add `(ServiceBase[ConfigType])` to class declaration
2. Replace `__init__` body with `super().__init__(config, cache, limiter)` + service-specific extras
3. Replace inline cache blocks with `self._cached_fetch(...)` calls
4. Replace standalone `_yf_call` with `self._yf_call(fn, *args, timeout=self._config.yfinance_timeout)`
5. Override `close()` only if service has httpx client or provider cleanup
6. Verify all existing tests pass unchanged

### Services In Scope

| Service | Config Type | `_cached_fetch` | `_yf_call` | `_retried_fetch` | Override `close()` |
|---------|------------|:-:|:-:|:-:|:-:|
| `MarketDataService` | `ServiceConfig` | 6 methods | Yes | Yes | No |
| `OptionsDataService` | `ServiceConfig` | 2 methods | Via providers | Yes | Yes |
| `FredService` | `ServiceConfig` | 1 method | No | No | Yes |
| `UniverseService` | `ServiceConfig` | 6 methods | No | Yes | Yes |
| `OpenBBService` | `OpenBBConfig` | 3 methods | No | No | No |
| `IntelligenceService` | `IntelligenceConfig` | 5 methods | Yes | Yes | No |
| `FinancialDatasetsService` | `FinancialDatasetsConfig` | 3 methods | No | Yes | Yes |

### Out of Scope

- `HealthService` (health checks, not data fetching)
- `OutcomeCollector` (composite orchestrator)
- `ChainProvider` implementations (separate protocol pattern)
- httpx client pooling (configs too different)
- Cache key standardization (too many formats to unify safely)

## Implementation Strategy

### Wave 1: Foundation
- Task 1: `ServiceBase` ABC + comprehensive unit tests + `__init__.py` re-export + `CLAUDE.md` update

### Wave 2: Simple Migrations (parallelizable)
- Task 2: `FredService` + `OpenBBService` (both simple, different patterns)
- Task 3: `IntelligenceService` + `FinancialDatasetsService` (both moderate)
- Task 4: `UniverseService` (moderate, 6 cache methods)

### Wave 3: Complex Migrations
- Task 5: `MarketDataService` (6 cached methods, yf_call, most used service)
- Task 6: `OptionsDataService` (provider delegation, pricing config, most intricate init)

### Wave 4: Verification
- Task 7: Integration test + dead code removal + final verification

**Risk mitigation**: Each migration is independently mergeable. Mixed state (some on
ServiceBase, some standalone) is valid. Full test suite runs after each task.

## Task Breakdown Preview

- [ ] Task 1: Create `services/base.py` with ServiceBase ABC + unit tests + docs
- [ ] Task 2: Migrate FredService + OpenBBService to ServiceBase
- [ ] Task 3: Migrate IntelligenceService + FinancialDatasetsService to ServiceBase
- [ ] Task 4: Migrate UniverseService to ServiceBase
- [ ] Task 5: Migrate MarketDataService to ServiceBase
- [ ] Task 6: Migrate OptionsDataService to ServiceBase
- [ ] Task 7: Integration test + dead code cleanup + verification

## Dependencies

### Internal (unchanged, reused)
- `services/helpers.py` — `fetch_with_limiter_retry()` (wrapped by `_retried_fetch`)
- `services/cache.py` — `ServiceCache` (passed via DI)
- `services/rate_limiter.py` — `RateLimiter` (passed via DI)
- `models/config.py` — All config types (`ServiceConfig`, `OpenBBConfig`, etc.)

### External
- None — pure internal refactor, no new dependencies

### Ordering
- Task 1 blocks all others (foundation must exist first)
- Tasks 2-4 are parallelizable after Task 1
- Tasks 5-6 can run after Task 1 but benefit from patterns established in Wave 2
- Task 7 requires all migrations complete

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Boilerplate reduction | -300+ lines across 7 services |
| Consumer changes | Zero (CLI, API, scan pipeline unchanged) |
| Existing test pass rate | 100% without modification |
| New tests for ServiceBase | 30+ tests in `test_base.py` |
| Cache-first dedup | ~25 of 29 blocks replaced by `_cached_fetch` |
| `_yf_call` dedup | 2 implementations → 1 in base |
| Migration completeness | 7/7 services inherit ServiceBase |

## Estimated Effort

**Total: L (3-5 days)**
- Wave 1 (Task 1): S — 3-4 hours
- Wave 2 (Tasks 2-4): M — 1-2 days
- Wave 3 (Tasks 5-6): M — 1 day
- Wave 4 (Task 7): S — 2-3 hours

## Tasks Created

- [ ] #439 - Create ServiceBase ABC with unit tests and docs (parallel: false)
- [ ] #441 - Migrate FredService and OpenBBService to ServiceBase (parallel: true)
- [ ] #444 - Migrate IntelligenceService and FinancialDatasetsService to ServiceBase (parallel: true)
- [ ] #440 - Migrate UniverseService to ServiceBase (parallel: true)
- [ ] #443 - Migrate MarketDataService to ServiceBase (parallel: true)
- [ ] #438 - Migrate OptionsDataService to ServiceBase (parallel: true)
- [ ] #442 - Integration test, dead code cleanup, and final verification (parallel: false)

Total tasks: 7
Parallel tasks: 5 (#438-#444, after #439 completes)
Sequential tasks: 2 (#439 foundation, #442 verification)
Estimated total effort: 18-24 hours

## Test Coverage Plan

Total test files planned: 2 (test_base.py + test_service_base_integration.py)
Total test cases planned: ~37 (30+ unit in test_base.py, 7 integration)
Existing test files verified: ~20 (all must pass unchanged)
