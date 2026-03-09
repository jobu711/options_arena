# Research: financialdatasets-ai

## PRD Summary

Add a `FinancialDatasetsService` that calls the financialdatasets.ai REST API during debates to enrich the fundamental agent with income statements, balance sheets, and financial metrics. Provides 16 new `fd_*` fields on `MarketContext`, supplements/replaces OpenBB fundamental data (FD > OpenBB > None priority), and adds 3 new context sections for the fundamental agent prompt. Debate-only (not scan pipeline). Never-raises, cache-first, httpx-based.

## Relevant Existing Modules

- **`services/openbb_service.py`** — Primary template. Optional external API, DI constructor, never-raises, two-tier caching, rate limiting. Most similar pattern to new FD service.
- **`services/fred.py`** — Secondary template. httpx AsyncClient setup, timeout config, aclose() lifecycle.
- **`services/intelligence.py`** — Multi-source aggregation template. Shows how multiple data sources feed into debate context.
- **`services/health.py`** — Health check orchestrator. Shows check_*() method pattern with latency measurement and HealthStatus return.
- **`services/cache.py`** — ServiceCache with TTL constants. `TTL_FUNDAMENTALS = 86400` available for reuse.
- **`models/analysis.py`** — MarketContext (90+ fields, lines 52-397). Target for 16 new `fd_*` fields. Has `completeness_ratio()`, `enrichment_ratio()`, `intelligence_ratio()`, `dse_ratio()` methods as templates.
- **`models/config.py`** — AppSettings root (lines 534-558). OpenBBConfig (lines 512-534) as template for FinancialDatasetsConfig nesting.
- **`models/openbb.py`** — Frozen enrichment models (FundamentalSnapshot, etc.). Template for FD response models with `frozen=True`, validators, UTC checks.
- **`agents/_parsing.py`** — Context rendering (lines 577-884). `render_fundamental_context()` and `render_context_block()` where 3 new FD sections will be inserted.
- **`agents/fundamental_agent.py`** — FUNDAMENTAL_SYSTEM_PROMPT (lines 28-73). Will bump to v3.0 with financial health, valuation depth, growth trajectory requirements.
- **`agents/orchestrator.py`** — `build_market_context()` (lines 108-240) and `run_debate()` (~line 420+). Integration points for FD data flow.
- **`api/app.py`** — Lifespan factory (lines 46-127). Conditional service creation pattern.
- **`api/deps.py`** — Dependency injection. Will add `get_financial_datasets()`.
- **`api/routes/debate.py`** — Debate route handlers. Will add FD fetch before `run_debate()`.
- **`cli/commands.py`** — CLI debate command. Service creation in try/finally pattern.

## Existing Patterns to Reuse

### Service Class Pattern (openbb_service.py:58-81, fred.py:36-70)
- Class-based DI: `__init__(config, cache, limiter)`
- Single `httpx.AsyncClient` with timeout, `aclose()` in `close()`
- Never-raises: all public methods return `Type | None`, log at WARNING
- Cache-first: `cache.get(key)` -> hit return -> fetch -> `cache.set(key, json, ttl)`
- Rate-limited: `async with self._limiter:` before API call
- Timeout-bounded: `asyncio.wait_for(coro, timeout=config.timeout)`

### Config Nesting Pattern (config.py:512-558)
- `FinancialDatasetsConfig(BaseModel)` — NOT BaseSettings
- Env override via nested delimiter: `ARENA_FINANCIAL_DATASETS__API_KEY`
- `enabled: bool`, `api_key: str | None`, feature toggles
- Added to AppSettings as: `financial_datasets: FinancialDatasetsConfig = FinancialDatasetsConfig()`

### Frozen Model Pattern (openbb.py:22-100)
- `model_config = ConfigDict(frozen=True)`
- Optional float fields default to `None`
- `@field_validator` with `math.isfinite()` before range checks
- UTC validator on datetime fields
- `field_serializer` for Decimal fields if needed

### MarketContext Extension Pattern (analysis.py:52-291)
- Flat optional fields: `fd_revenue: float | None = None`
- Separate coverage method: `financial_datasets_ratio()` (parallel to `enrichment_ratio()`)
- Include new float fields in `validate_optional_finite()` validator (lines 301-370)

### Context Rendering Pattern (_parsing.py:577-884)
- Section headers: `"## Income Statement (TTM)"`
- Key-value format: `"Revenue: $435.6B\nNet Income: $117.8B"`
- None-check before rendering: `if ctx.fd_revenue is not None:`
- Insert between existing "Fundamental Profile" and "Analyst Intelligence" sections

### Health Check Pattern (health.py:45-100)
- `check_financial_datasets()` returns `HealthStatus`
- Latency measurement: `time.monotonic()` before/after
- Added to `check_all()` gather list when config enabled
- Omitted (not errored) when API key not configured

## Existing Code to Extend

### `models/config.py` (lines 512-558)
- Add `FinancialDatasetsConfig` class (parallel to `OpenBBConfig`)
- Add `financial_datasets` field to `AppSettings`

### `models/analysis.py` (lines 52-397)
- Add 16 `fd_*` fields after existing OpenBB enrichment fields (~line 150)
- Add `financial_datasets_ratio()` method after `dse_ratio()` (~line 291)
- Extend `validate_optional_finite()` to include new float fields

### `agents/_parsing.py` (lines 577-884)
- Extend `render_fundamental_context()` with 3 new sections after "Fundamental Profile"
- Extend `render_context_block()` with same 3 sections

### `agents/fundamental_agent.py` (lines 28-73)
- Bump FUNDAMENTAL_SYSTEM_PROMPT version to v3.0
- Add financial health, valuation depth, growth trajectory analysis requirements

### `agents/orchestrator.py` (lines 108-240, ~420+)
- Add `fd_package` parameter to `build_market_context()`
- Add FD field mapping with priority: FD > OpenBB > None for overlapping fields
- Add `fd_package` parameter to `run_debate()`

### `services/health.py`
- Add `check_financial_datasets()` method
- Add to `check_all()` gather list when enabled

### `api/app.py` (lifespan, lines 46-127)
- Create `FinancialDatasetsService` in lifespan (conditional on enabled)
- Store on `app.state.financial_datasets`
- Close in shutdown

### `api/deps.py`
- Add `get_financial_datasets(request) -> FinancialDatasetsService | None`

### `api/routes/debate.py`
- Fetch FD package before `run_debate()` calls

### `cli/commands.py`
- Create service, fetch package, pass to `run_debate()`, close in `finally`

### `models/__init__.py` and `services/__init__.py`
- Add re-exports for new models and service

## Potential Conflicts

### Field Name Overlaps (Mitigated by Priority Rule)
7 fields exist in both OpenBB and FD: `pe_ratio`, `forward_pe`, `peg_ratio`, `price_to_book`, `debt_to_equity`, `revenue_growth`, `profit_margin`. **Solution**: FD takes priority when both available. Pattern:
```python
pe_ratio=fd_package.metrics.pe_ratio if fd_package else (fundamentals.pe_ratio if fundamentals else None)
```
No breaking change — OpenBB remains fallback.

### MarketContext.completeness_ratio() Unaffected
Checks scan-derived fields only. New FD fields are enrichment, measured separately by `financial_datasets_ratio()`. Existing completeness thresholds unchanged.

### No Other Conflicts Found
- `fd_*` prefix is unique in codebase (confirmed via grep)
- All new parameters are optional (`| None`)
- Existing debate flow backward compatible
- Config defaults to enabled=True but no-ops without API key

## Open Questions

1. **Cache TTL**: PRD says 1 hour. Should we reuse `TTL_FUNDAMENTALS` (24h) or define FD-specific TTL? **Recommendation**: 1 hour as PRD specifies — financial data changes intraday less than options data but more than fundamentals.
2. **Enabled default**: Should `FinancialDatasetsConfig.enabled` default to `True` (activate when API key present) or `False` (require explicit opt-in)? **Recommendation**: `True` — service no-ops without API key anyway, matching OpenBB pattern.
3. **forward_pe**: FD provides `forward_pe_ratio` but PRD doesn't list it. Include? **Recommendation**: Yes, it's a free field from the metrics endpoint.

## Recommended Architecture

```
AppSettings.financial_datasets: FinancialDatasetsConfig
    |
    v
FinancialDatasetsService(config, cache, limiter)
    |-- fetch_financial_metrics(ticker) -> FinancialMetricsData | None
    |-- fetch_income_statement(ticker) -> IncomeStatementData | None
    |-- fetch_balance_sheet(ticker) -> BalanceSheetData | None
    |-- fetch_package(ticker) -> FinancialDatasetsPackage | None  (parallel gather of above 3)
    |-- close()
    |
    v
Orchestrator: run_debate(..., fd_package=package)
    |
    v
build_market_context(..., fd_package=package)
    |-- Maps FD fields to MarketContext.fd_* fields
    |-- FD > OpenBB > None priority for overlapping fields
    |
    v
render_fundamental_context(context)
    |-- Existing: Fundamental Profile, Analyst Intelligence, ...
    |-- NEW: Income Statement (TTM), Balance Sheet, Growth & Valuation
    |
    v
Fundamental Agent (v3.0 prompt)
    |-- Analyzes financial health, valuation depth, growth trajectory
```

Data flow is unidirectional: Config -> Service -> Orchestrator -> MarketContext -> Rendering -> Agent.

## Test Strategy Preview

### Existing Test Patterns
- **Service tests**: `tests/unit/services/` — Mock httpx, cache, limiter via `MagicMock`/`AsyncMock`. Never-raises assertion pattern.
- **Model tests**: `tests/unit/models/` — Validation tests (valid construction, NaN rejection, UTC enforcement, frozen immutability).
- **Agent tests**: `tests/unit/agents/` — `TestModel` override for PydanticAI. Context rendering string assertion.
- **Integration tests**: `tests/unit/agents/test_orchestrator.py` — `build_market_context()` field mapping tests.

### New Test Files
| File | Count | Coverage |
|------|-------|----------|
| `tests/unit/models/test_financial_datasets.py` | ~15 | Model construction, validators, NaN/Inf rejection, UTC enforcement, frozen |
| `tests/unit/services/test_financial_datasets.py` | ~15 | Happy path, cache hit, config disabled, timeout, API error, never-raises |
| Extend `tests/unit/models/test_analysis.py` | ~4 | New `fd_*` fields, `financial_datasets_ratio()` |
| Extend `tests/unit/agents/test_orchestrator.py` | ~4 | `fd_package` mapping, priority logic |
| Extend `tests/unit/agents/test_domain_renderers.py` | ~4 | 3 new context sections rendering |

### Mocking Strategy
- httpx calls mocked via `unittest.mock.patch` on `httpx.AsyncClient`
- Cache: `MagicMock` with `get=AsyncMock(return_value=None)`, `set=AsyncMock()`
- Rate limiter: `MagicMock` with `__aenter__`/`__aexit__` as `AsyncMock`
- No real API calls in unit tests

## Estimated Complexity

**Medium (M)** — Justification:
- Well-established patterns to follow (OpenBBService, IntelligenceService)
- No new dependencies or architectural changes
- All integration points identified with clear templates
- 2 new files + 11 modified files + 2 new test files + 3 extended test files
- ~42 new tests, ~800-1000 new lines of code
- Risk: Low (backward compatible, never-raises, config-gated)
