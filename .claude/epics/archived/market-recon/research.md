# Research: market-recon

## PRD Summary

**Arena Recon** adds an `IntelligenceService` that fetches 6 unused yfinance methods (analyst targets, recommendations, upgrades/downgrades, insider transactions, institutional holders, news) and wires 30 new fields through `MarketContext` to all 7 debate agents. Phase 1 requires zero new dependencies and $0/month. Separately, 22 DSE indicator fields (8 dimensional scores + 10 high-signal indicators + 3 second-order Greeks + 1 direction confidence) already computed during scan are passed through to agents.

## Relevant Existing Modules

- `services/` — New `IntelligenceService` lives here. Mirrors `OpenBBService` exactly (guarded imports, config-gated, never-raises, cache-first, typed models). CAN import `models/`. CANNOT import `agents/`, `pricing/`, `indicators/`, `scoring/`.
- `models/analysis.py` — `MarketContext` gets 30 new fields (8 intelligence + 8 dimensional + 10 DSE individual + 3 second-order Greeks + 1 confidence). Currently has 26+ fields with OpenBB enrichment pattern.
- `models/config.py` — New `IntelligenceConfig(BaseModel)` nested under `AppSettings`. Follows `OpenBBConfig` pattern exactly.
- `models/intelligence.py` — NEW file. 7 Pydantic models: `AnalystSnapshot`, `UpgradeDowngrade`, `AnalystActivitySnapshot`, `InsiderTransaction`, `InsiderSnapshot`, `InstitutionalSnapshot`, `IntelligencePackage`.
- `agents/orchestrator.py` — `build_market_context()` gets new `intelligence` param + DSE field mapping from `TickerScore.signals` and `.dimensional_scores`.
- `agents/_parsing.py` — `render_context_block()` gets 7 new sections appended after OpenBB sections.
- `cli/commands.py` — Debate command gets `--no-recon` flag (mirrors existing `--no-openbb`), creates `IntelligenceService` conditionally.
- `api/app.py` — Lifespan creates `IntelligenceService` on `app.state.intelligence` (mirrors OpenBB pattern).
- `api/deps.py` — New `get_intelligence()` dependency provider.
- `api/routes/debate.py` — Fetches intelligence before debate, passes to orchestrator.
- `services/health.py` — New `check_intelligence()` method in `HealthService.check_all()`.
- `models/scan.py` — `TickerScore.signals: IndicatorSignals` (all 10 target fields exist, all `float | None`) and `TickerScore.dimensional_scores: DimensionalScores | None` (8 family scores).
- `models/scoring.py` — `DimensionalScores` model (frozen, 8 `float | None` fields: trend, iv_vol, hv_vol, flow, microstructure, fundamental, regime, risk).

## Existing Patterns to Reuse

### 1. OpenBB Service Pattern (mirror exactly)
- **Location**: `services/openbb_service.py`
- **Pattern**: Class-based DI (`config`, `cache`, `limiter` via `__init__`), 6-step method pattern (config gate → cache check → rate-limited fetch → map to typed model → cache result → outer except returns None), explicit `close()`.
- **Apply**: `IntelligenceService.__init__(config, cache, limiter)` with identical structure.

### 2. Safe Converters
- **Location**: `services/openbb_service.py` lines 375-393
- `_safe_float(value: object) -> float | None` — rejects NaN/Inf via `math.isfinite()`
- `_safe_int(value: object) -> int | None` — safe int conversion
- **Apply**: Extract to `services/helpers.py` or duplicate in `intelligence.py` (PRD suggests helpers.py).

### 3. yfinance Wrapping (`_yf_call` pattern)
- **Location**: `services/market_data.py`
- **Pattern**: `asyncio.to_thread(fn, *args, **kwargs)` + `asyncio.wait_for(timeout)`. CRITICAL: pass callable + args separately, NOT `to_thread(fn())`.
- **Apply**: Replicate in `IntelligenceService` for all 6 yfinance method calls.

### 4. Cache-First Strategy
- **Location**: `services/cache.py` — `ServiceCache`
- **Pattern**: `cached = await cache.get(key)` → on miss: fetch, `await cache.set(key, serialized, ttl)`. Keys: `{source}:{type}:{ticker}`. TTLs via named constants.
- **Apply**: Keys like `intel:analyst:{ticker}`, `intel:insider:{ticker}`, etc.

### 5. Rate Limiter
- **Location**: `services/rate_limiter.py` — `RateLimiter`
- **Pattern**: `async with self._limiter:` context manager. `release()` is synchronous.
- **Apply**: Wrap all yfinance calls in rate limiter.

### 6. Context Block Section Pattern
- **Location**: `agents/_parsing.py` — `render_context_block()`
- **Pattern**: Empty line separator → `## Heading` → filtered content lines via `_render_optional()`. Section only appears if at least one non-None field.
- **Apply**: 7 new sections: Analyst Intelligence, Insider Activity, Institutional Ownership, Signal Dimensions, Volatility Regime, Market & Flow Signals, Second-Order Greeks.

### 7. `_render_optional` Helper
- **Location**: `agents/_parsing.py` line 347-351
- **Signature**: `_render_optional(label: str, value: float | None, fmt: str = ".1f") -> str | None`
- **Apply**: Use for all new context block fields.

### 8. Config Nesting Pattern
- **Location**: `models/config.py` — `OpenBBConfig(BaseModel)` nested in `AppSettings`
- **Pattern**: `BaseModel` for sub-config, `AppSettings(BaseSettings)` root. Env override: `ARENA_OPENBB__ENABLED=false`.
- **Apply**: `IntelligenceConfig(BaseModel)` nested as `intelligence: IntelligenceConfig = IntelligenceConfig()`.

### 9. CLI Flag Pattern
- **Location**: `cli/commands.py` — `no_openbb: bool = typer.Option(False, "--no-openbb", ...)`
- **Apply**: `no_recon: bool = typer.Option(False, "--no-recon", help="Skip intelligence fetching")`.

### 10. API Lifespan Pattern
- **Location**: `api/app.py` — conditional creation in `lifespan()`, stored on `app.state`, closed in shutdown.
- **Apply**: `app.state.intelligence = IntelligenceService(...)` if config enabled.

### 11. Health Check Pattern
- **Location**: `services/health.py`
- **Pattern**: `time.monotonic()` for latency, catch broadly, return `HealthStatus`. `check_all()` runs via `asyncio.gather(return_exceptions=True)`.
- **Apply**: New `check_intelligence()` method doing a lightweight yfinance smoke test.

## Existing Code to Extend

| File | What Exists | What Changes |
|------|-------------|-------------|
| `models/analysis.py` | MarketContext with 26+ fields, `completeness_ratio()`, `enrichment_ratio()`, validators | Add 30 fields (8 intelligence + 22 DSE), `intelligence_ratio()`, `dse_ratio()`, new validators |
| `models/config.py` | AppSettings with 7 nested configs | Add `IntelligenceConfig(BaseModel)` + `intelligence: IntelligenceConfig` |
| `models/__init__.py` | Re-exports all models + `__all__` | Add intelligence model imports + exports |
| `agents/orchestrator.py` | `build_market_context()` with OpenBB params, `run_debate_v2()` | Add `intelligence` param + map fields; map DSE from TickerScore |
| `agents/_parsing.py` | `render_context_block()` with 8 sections | Add 7 new sections after OpenBB sections |
| `services/__init__.py` | Re-exports OpenBBService + all services | Add `IntelligenceService` |
| `services/health.py` | `HealthService.check_all()` with 5 checks | Add `check_intelligence()` |
| `cli/commands.py` | Debate command with `--no-openbb` | Add `--no-recon`, create IntelligenceService, pass to orchestrator |
| `api/app.py` | Lifespan creates OpenBBService | Add IntelligenceService creation + shutdown |
| `api/deps.py` | `get_openbb()` provider | Add `get_intelligence()` |
| `api/routes/debate.py` | Fetches OpenBB enrichment before debate | Add intelligence fetch + pass to orchestrator |

## Potential Conflicts

- **MarketContext field validators**: Adding 30 fields requires extending the `validate_optional_finite` validator list — must match exact field names or it silently skips validation. Use the same grouped validator pattern.
- **`completeness_ratio()` scope**: The 8 intelligence and 22 DSE fields must NOT be included in `completeness_ratio()` (which measures core technical completeness). They get their own `intelligence_ratio()` and `dse_ratio()` methods — parallel to existing `enrichment_ratio()` for OpenBB.
- **Context token budget**: Current context block is ~25-35 lines. Full intelligence + DSE adds ~30 lines → ~55-65 total → ~500 tokens, within the 2000-token budget for context data in the 8192-token model window.
- **`_safe_float`/`_safe_int` duplication**: Currently defined as module-level functions in `openbb_service.py`. Could cause import issues if intelligence service tries to import from openbb_service. Solution: extract to `services/helpers.py` (PRD mentions this file already exists).
- **Test isolation**: Intelligence tests must mock yfinance calls (same as market_data tests). The `_yf_call` pattern is method-scoped, so mocking via `unittest.mock.patch` on `asyncio.to_thread` works.

## Open Questions

1. **`_safe_float`/`_safe_int` extraction**: Should these be extracted from `openbb_service.py` to `services/helpers.py` now, or duplicated in `intelligence.py`? PRD references `services/helpers.py` — need to check if that file already exists.
2. **DSE wiring without prior scan**: If a user runs `debate AAPL` without a prior scan, `TickerScore` doesn't exist and DSE fields will all be None. The PRD acknowledges this — graceful degradation. But should we show a hint in the context block that DSE data is unavailable because no scan was run?
3. **Migration 010 scope**: The PRD mentions `intelligence_snapshots` table for historical storage. But MarketContext is already persisted as JSON in `ai_debates.market_context_json`. Do we need a separate table, or just ensure the 30 new fields serialize properly in the existing JSON column?
4. **Second-order Greeks access**: The PRD says vanna/charm/vomma come from `first_contract.greeks`. Current `OptionGreeks` model needs to be checked — does it already have vanna, charm, vomma fields? If not, this may require `pricing/dispatch.py` changes (which would increase scope).

## Recommended Architecture

Follow the proven OpenBB integration pattern exactly:

**Epic A: Intelligence Service + Models (foundation)**
1. Create `IntelligenceConfig` in `models/config.py` → nest in `AppSettings`
2. Create 7 intelligence models in `models/intelligence.py` (all frozen, with validators)
3. Re-export from `models/__init__.py`
4. Create `IntelligenceService` in `services/intelligence.py` (6 public methods, never-raises)
5. Re-export from `services/__init__.py`
6. Add health check in `services/health.py`
7. Write unit tests for models + service (~135 tests)

**Epic B: Context Wiring + Integration (depends on A)**
1. Add 30 fields to `MarketContext` + `intelligence_ratio()` + `dse_ratio()` + validators
2. Extend `build_market_context()` with intelligence + DSE mapping
3. Add 7 sections to `render_context_block()`
4. Wire CLI: `--no-recon` flag, service creation, pass to orchestrator
5. Wire API: lifespan, deps, debate route
6. Create migration 010
7. Write unit + integration tests (~110 tests)

## Test Strategy Preview

### Existing Test Patterns
- **Model tests**: `tests/unit/models/` — construct models, validate fields, test validators (NaN/Inf rejection, UTC enforcement, confidence bounds)
- **Service tests**: `tests/unit/services/` — mock yfinance via `unittest.mock.patch("asyncio.to_thread")`, test cache hit/miss, test config gates, test error handling
- **Agent tests**: `tests/unit/agents/` — mock models, test `render_context_block()` output, test `build_market_context()` mapping
- **Integration tests**: `tests/integration/` — real yfinance calls, `@pytest.mark.integration`

### Test File Naming
- `tests/unit/models/test_intelligence_models.py`
- `tests/unit/services/test_intelligence_service.py`
- `tests/unit/agents/test_intelligence_context.py`
- `tests/unit/agents/test_dse_context.py`
- `tests/integration/test_intelligence_integration.py`

### Mocking Strategy
- yfinance: `patch("asyncio.to_thread")` to return pre-built DataFrames/dicts
- Cache: Real `ServiceCache` with in-memory-only mode, or mock `get()/set()`
- Rate limiter: Real `RateLimiter` (fast in tests) or mock

## Estimated Complexity

**L (Large)** — 2 epics, ~10 files to create, ~11 files to modify, ~245 new tests, 30 new MarketContext fields.

Justification:
- Follows a fully proven pattern (OpenBB integration) — reduces risk
- Zero new dependencies — reduces environment complexity
- All DSE data is already computed — zero new computation logic
- But sheer volume of fields (30), models (7), and test coverage (~245 tests) across models, services, agents, CLI, and API makes this a large effort
- Critical parsing nuances in yfinance output (camelCase columns, empty Transaction column, index-based dates) add implementation detail
