# Research: openbb-integration

## PRD Summary

Integrate OpenBB Platform SDK as a supplementary data layer alongside the existing yfinance/FRED/CBOE stack. Two epics:

- **Epic A** (Supplement): Add fundamentals (P/E, margins, debt), unusual options flow (Stockgrid), and news sentiment (VADER) to enrich AI debate agents with data they currently lack. All free providers, no paid API keys.
- **Epic B** (Migration): Replace yfinance as primary options chain source with CBOE via OpenBB, gaining native Greeks. yfinance becomes automatic fallback.

## Relevant Existing Modules

| Module | Relationship to Feature |
|--------|------------------------|
| `services/` | New `OpenBBService` lives here. Only layer allowed to touch external APIs. Existing `MarketDataService`, `OptionsDataService`, `FredService`, `HealthService` are templates. |
| `models/` | New `models/openbb.py` for `FundamentalSnapshot`, `UnusualFlowSnapshot`, `NewsSentimentSnapshot`, etc. Extend `MarketContext` in `analysis.py`, add `SentimentLabel` to `enums.py`, add `OpenBBConfig` to `config.py`. |
| `agents/` | `orchestrator.py` — `build_market_context()` wires OpenBB data into debates. `_parsing.py` — renders new context sections in agent prompts. |
| `scan/pipeline.py` | Phase 3 (`_process_ticker_options()`) runs parallel fetches via `asyncio.gather()` — OpenBB fundamentals/flow can be added here. |
| `services/health.py` | Extend `check_all()` with OpenBB provider probes. Pattern: never-raises, returns `HealthStatus`. |
| `services/options_data.py` | Epic B: Add `ChainProvider` protocol, `CBOEChainProvider`, fallback chain. Existing `_yf_call()` is the canonical async wrapping pattern. |
| `cli/commands.py` | Health command renders via `render_health_table()` — auto-picks up new health entries. |
| `api/routes/health.py` | `/health/services` endpoint auto-serializes new `HealthStatus` entries. |

## Existing Patterns to Reuse

### 1. Async Wrapping (`services/options_data.py` lines 151-186)
```python
async def _yf_call(self, fn: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.wait_for(
        asyncio.to_thread(fn, *args, **kwargs),
        timeout=self._config.yfinance_timeout,
    )
```
**CRITICAL**: `to_thread(fn, *args)` — pass callable + args separately, NOT `to_thread(fn())`.

### 2. Class-Based DI (all services)
```python
class MarketDataService:
    def __init__(self, config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> None: ...
    async def close(self) -> None: ...
```
OpenBBService must follow this exact pattern: `(config: OpenBBConfig, cache: ServiceCache, limiter: RateLimiter)`.

### 3. Never-Raises Contract (`services/fred.py`)
All public methods catch broad exceptions, return fallback value or `None`, log warnings. OpenBB data is optional — failures must never crash scans or debates.

### 4. Cache-First (`services/market_data.py`)
Check cache -> fetch if miss -> store -> return. Two-tier: in-memory LRU + SQLite WAL. Cache key format: `"openbb:{type}:{ticker}"`.

### 5. Batch Isolation
`asyncio.gather(*tasks, return_exceptions=True)` — one failed ticker never crashes batch.

### 6. Retry with Backoff (`services/helpers.py` lines 18-63)
`fetch_with_retry()` accepts zero-arg async factory. Exponential backoff: 1s -> 16s, max 5 retries.

### 7. Frozen Pydantic Models (all data models)
`ConfigDict(frozen=True)`, `field_validator` with `math.isfinite()` on all float fields, UTC datetime validator on all datetime fields.

### 8. StrEnum Pattern (`models/enums.py`)
All values lowercase, underscores for multi-word. Test: member count, values, `issubclass(StrEnum)`, iteration.

### 9. Prompt Context Rendering (`agents/_parsing.py` lines 354-431)
`render_context_block(ctx: MarketContext)` renders flat key-value text. Uses `_render_optional()` helper for None-safe formatting. New sections are additive — omitted entirely when data is None.

### 10. Health Check Pattern (`services/health.py`)
Each check method returns `HealthStatus`, never raises. `check_all()` runs all checks in parallel via `asyncio.gather(return_exceptions=True)`.

## Existing Code to Extend

### `src/options_arena/models/analysis.py` — MarketContext
Currently has ~30 fields: ticker, price, 52w high/low, sector, scoring context, IV/options metrics, technical indicators, contract/Greeks fields, earnings. `completeness_ratio()` checks 11 base optional fields + 4 Greeks fields (when contract_mid is not None). **Needs ~15 new optional fields** for fundamentals, flow, sentiment — all `float | None = None`.

### `src/options_arena/models/config.py` — AppSettings
Single `BaseSettings` root with 6 nested `BaseModel` configs: `ScanConfig`, `PricingConfig`, `ServiceConfig`, `DebateConfig`, `DataConfig`, `LogConfig`. **Add `OpenBBConfig(BaseModel)`** as 7th nested config. Env pattern: `ARENA_OPENBB__ENABLED=false`.

### `src/options_arena/agents/orchestrator.py` — build_market_context()
Currently takes `(ticker_score, quote, ticker_info, contracts, next_earnings)`. **Extend signature** with `fundamentals: FundamentalSnapshot | None = None`, `flow: UnusualFlowSnapshot | None = None`, `sentiment: NewsSentimentSnapshot | None = None`.

### `src/options_arena/agents/_parsing.py` — render_context_block()
**Add 3 new sections** (omitted when data is None):
- `## Fundamental Profile` (P/E, debt/equity, margins, revenue growth)
- `## Unusual Options Flow` (net call/put premium, put/call ratio)
- `## News Sentiment` (aggregate score, recent headlines)

### `src/options_arena/services/health.py` — HealthService
**Add `check_openbb()`** method probing OpenBB SDK availability with a test call to a known ticker.

### `src/options_arena/services/options_data.py` — Epic B
**Add `ChainProvider` protocol**, `CBOEChainProvider` (primary), `YFinanceChainProvider` (fallback). Three-tier Greeks: CBOE native -> local BAW/BSM -> None.

### `src/options_arena/models/enums.py`
**Add `SentimentLabel(StrEnum)`**: BULLISH, BEARISH, NEUTRAL.

### `src/options_arena/models/__init__.py` & `services/__init__.py`
**Re-export** all new public models and the `OpenBBService` class.

### `pyproject.toml` — Dependencies
**New optional extras**:
```toml
[project.optional-dependencies]
openbb = ["openbb>=4.0", "vaderSentiment>=3.3"]
```
OpenBB SDK is optional — guarded import, system works without it.

## Potential Conflicts

### 1. MarketContext Field Naming
- Existing: `put_call_ratio` (from indicators)
- OpenBB: `options_put_call_ratio` (from unusual flow)
- **Mitigation**: Use different field name as PRD specifies. No conflict.

### 2. Completeness Ratio Denominator Increase
- Adding ~15 new optional fields increases denominator -> lower ratio initially -> may trigger more data-driven fallbacks (60% threshold).
- **Mitigation**: Only count OpenBB fields in completeness_ratio when OpenBB is enabled in config. Or separate the new fields into their own completeness check.

### 3. OpenBB SDK Weight
- OpenBB Platform is a heavy dependency with many transitive deps. May conflict with existing package versions.
- **Mitigation**: Make it optional (`pip install options-arena[openbb]`). Guard import with `try/except ImportError`. Run CI without OpenBB installed.

### 4. CBOE Chain Schema Differences (Epic B)
- yfinance: camelCase columns, no Greeks
- CBOE via OpenBB: Different column names, includes Greeks
- **Mitigation**: Provider abstraction handles mapping. Both produce `OptionContract`. Extensive unit tests on field mapping.

### 5. VADER Sentiment Accuracy
- VADER is a general-purpose lexicon. Financial headlines may be misclassified.
- **Mitigation**: Sentiment is context only (not scored). Agents can disagree with the label. Consider financial lexicon additions later.

## Open Questions

1. **OpenBB SDK version pinning**: Which OpenBB Platform version to target? v4.x has different API than v3.x. Need Context7 verification of exact method signatures before implementation.
2. **VADER vs vaderSentiment**: PRD mentions both `nltk` and standalone `vaderSentiment` package. Standalone `vaderSentiment` is lighter (no NLTK download required). Recommend `vaderSentiment>=3.3`.
3. **Completeness ratio strategy**: Should new OpenBB fields count toward the 60% debate quality gate? If yes, debates without OpenBB data could be penalized. Recommend: separate OpenBB completeness from core completeness, or only count when OpenBB is enabled.
4. **Scan pipeline enrichment**: Should fundamentals/flow data appear in scan results table, or only in debate context? PRD US-2 says "Scan results indicate when unusual activity is detected" — implies scan display changes.
5. **Database persistence**: Should OpenBB snapshots be persisted to SQLite (new tables, migration 010), or is in-memory caching sufficient for v1?
6. **Epic A vs Epic B ordering**: PRD says "Epic A is lower risk and should ship first." Confirm: implement Epic A fully before starting Epic B?

## Recommended Architecture

### Epic A: Supplement Pattern (Low Risk)
```
1. models/openbb.py          — New typed models (FundamentalSnapshot, etc.)
2. models/enums.py            — SentimentLabel StrEnum
3. models/config.py           — OpenBBConfig nested in AppSettings
4. services/openbb_service.py — New service (DI, async wrap, cache, never-raises)
5. models/analysis.py         — Extend MarketContext with optional fields
6. agents/orchestrator.py     — Wire OpenBB data into build_market_context()
7. agents/_parsing.py         — Render fundamental/flow/sentiment sections
8. services/health.py         — Add OpenBB provider health checks
9. models/__init__.py         — Re-export new models
10. services/__init__.py      — Re-export OpenBBService
```

### Epic B: Migration Pattern (Medium Risk)
```
1. services/options_data.py   — ChainProvider protocol + CBOEChainProvider
2. models/options.py          — Extend OptionContract for native Greeks source
3. pricing/dispatch.py        — Three-tier Greeks resolution
4. scoring/contracts.py       — Enhanced selection using native delta
5. Parallel validation        — Compare CBOE vs yfinance output
6. Config cutover             — cboe_chains_enabled=True default
```

### Data Flow (Epic A Complete)
```
CLI/API → create OpenBBService (DI) → parallel fetch:
  ├── fetch_fundamentals(ticker) → FundamentalSnapshot | None
  ├── fetch_unusual_flow(ticker) → UnusualFlowSnapshot | None
  └── fetch_news_sentiment(ticker) → NewsSentimentSnapshot | None
→ build_market_context(..., fundamentals, flow, sentiment)
→ render_context_block() adds 3 new sections
→ Agents see enriched context → Better arguments
```

## Test Strategy Preview

### Existing Test Patterns
- **Model tests** (`tests/unit/models/`): Test member counts, values, validators, serialization, frozen enforcement
- **Service tests** (`tests/unit/services/`): Fixtures for config/cache/limiter, mock external calls, assert typed returns
- **Agent tests** (`tests/unit/agents/`): Mock models, test prompt rendering, test orchestrator flow
- **Naming**: `test_{module_name}.py`, class-based grouping (`class TestFundamentalSnapshot:`)
- **Assertions**: `pytest.approx(rel=1e-4)` for floats, `pytest.raises(ValidationError)` for validators

### New Test Files
| File | Test Count (est.) | Coverage |
|------|-------------------|----------|
| `tests/unit/models/test_openbb_models.py` | ~35 | All new Pydantic models, validators, serialization |
| `tests/unit/services/test_openbb_service.py` | ~40 | Service methods, caching, error handling, never-raises |
| `tests/unit/agents/test_openbb_prompts.py` | ~20 | Prompt rendering with fundamental/flow/sentiment data |
| `tests/unit/services/test_chain_providers.py` | ~25 | Epic B: CBOE provider, fallback chain, Greeks mapping |
| `tests/integration/test_openbb_pipeline.py` | ~15 | End-to-end with mocked OpenBB responses |

### Mocking Strategy
- Mock OpenBB SDK at the import level: `unittest.mock.patch("openbb.obb")`
- Create fixture factories for `FundamentalSnapshot`, `UnusualFlowSnapshot`, `NewsSentimentSnapshot`
- Test guarded import: verify system works when `openbb` is not installed
- Test never-raises: inject exceptions into mocked SDK calls, verify `None` returns

## Database Context
- **Latest migration**: `009_market_context.sql`
- **Next available**: `010_openbb_data.sql` (if persistence needed)
- **Pattern**: `{NNN}_{description}.sql`, `CREATE TABLE IF NOT EXISTS`, `schema_version` tracking

## Estimated Complexity

**Epic A: L (Large)**
- 2 new files, ~8 modified files, ~120 new tests
- New service class, model extensions, prompt rendering, health checks
- All patterns exist — this is "build another service following the template"
- Risk: OpenBB SDK compatibility, VADER accuracy, completeness ratio impact

**Epic B: XL (Extra Large)**
- New provider abstraction (first in project), three-tier Greeks resolution
- Schema mapping between yfinance and CBOE formats
- Parallel validation phase, cutover logic
- Risk: CBOE chain schema differences, native Greeks validation, regression risk in scoring layer
