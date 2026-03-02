---
name: openbb-integration
status: in-progress
created: 2026-03-01T19:04:56Z
progress: 0%
prd: .claude/prds/openbb-integration.md
github: https://github.com/jobu711/options_arena/issues/178
---

# Epic: openbb-integration

## Overview

Add OpenBB Platform SDK as a supplementary data layer to enrich AI debate agents with fundamentals (P/E, margins, debt), unusual options flow (Stockgrid), and news sentiment (VADER). All providers are free with no API keys. OpenBB is an optional dependency — the system runs identically without it.

This epic covers **Epic A** from the PRD (supplement pattern). Epic B (CBOE chain migration) will be a separate follow-up epic after this ships.

## Architecture Decisions

1. **OpenBB as optional dependency**: `uv add --optional openbb openbb vaderSentiment`. Guarded import — `try/except ImportError` at module top. All `OpenBBService` methods return `None` when SDK is unavailable.

2. **Standalone vaderSentiment over nltk**: Lighter (no NLTK data download), same VADER engine, no API key. `vaderSentiment>=3.3`.

3. **OpenBB fields excluded from core completeness_ratio()**: New fields go in a separate `enrichment_ratio()` method on MarketContext. Prevents penalizing debates when OpenBB is disabled or data is unavailable. The 60% quality gate remains unchanged.

4. **Debate-path only (v1)**: OpenBB data flows into debate context via MarketContext. Scan pipeline does NOT fetch OpenBB data in v1 — avoids rate limiting on full-universe scans (~5,000 tickers). Scan enrichment deferred.

5. **In-memory caching only**: No new SQLite tables or migrations. Cache-first via existing `ServiceCache` with config-driven TTLs. Database persistence of OpenBB snapshots deferred.

6. **Three independent data fetches**: Fundamentals, flow, and sentiment are fetched in parallel via `asyncio.gather()` before `build_market_context()`. Each is independent — one failure doesn't block others.

## Technical Approach

### New Files
| File | Purpose |
|------|---------|
| `src/options_arena/models/openbb.py` | 6 Pydantic models: `FundamentalSnapshot`, `UnusualFlowSnapshot`, `NewsSentimentSnapshot`, `NewsHeadline`, `SentimentLabel` enum, `OpenBBHealthStatus` |
| `src/options_arena/services/openbb_service.py` | `OpenBBService` class with guarded import, DI, async wrapping, 3 fetch methods, health check |
| `tests/unit/models/test_openbb_models.py` | Model tests |
| `tests/unit/services/test_openbb_service.py` | Service tests |
| `tests/unit/agents/test_openbb_prompts.py` | Prompt rendering tests |

### Modified Files
| File | Change |
|------|--------|
| `pyproject.toml` | Add `openbb` optional extra with `openbb`, `vaderSentiment` |
| `src/options_arena/models/enums.py` | Add `SentimentLabel(StrEnum)` |
| `src/options_arena/models/config.py` | Add `OpenBBConfig(BaseModel)` nested in `AppSettings` |
| `src/options_arena/models/analysis.py` | Extend `MarketContext` with ~13 optional fields + `enrichment_ratio()` |
| `src/options_arena/models/__init__.py` | Re-export new models |
| `src/options_arena/services/__init__.py` | Re-export `OpenBBService` |
| `src/options_arena/agents/orchestrator.py` | Extend `build_market_context()` signature, wire parallel OpenBB fetches in debate path |
| `src/options_arena/agents/_parsing.py` | Add 3 new context sections (fundamental, flow, sentiment) |
| `src/options_arena/services/health.py` | Add `check_openbb()` to `HealthService.check_all()` |

### Data Flow
```
debate command → create OpenBBService(config, cache, limiter)
  → asyncio.gather(
      fetch_fundamentals(ticker),
      fetch_unusual_flow(ticker),
      fetch_news_sentiment(ticker),
    )
  → build_market_context(..., fundamentals, flow, sentiment)
  → render_context_block() adds 3 new sections when data present
  → Agents see enriched context → Better arguments
```

## Implementation Strategy

5 tasks executed in dependency order. Tasks 1-2 are sequential (models before service). Tasks 3-5 depend on task 2 but are parallelizable with each other.

```
Task 1 (Foundation) → Task 2 (Service) → Task 3 (MarketContext + Wiring)
                                       → Task 4 (Prompt Rendering)
                                       → Task 5 (Health + Integration)
```

### Risk Mitigation
- **OpenBB SDK compatibility**: Verify SDK method signatures via Context7 before implementing service layer.
- **Rate limiting**: Independent token bucket per OpenBB provider. Configurable via `OpenBBConfig`.
- **CI without OpenBB**: Tests mock at import level. CI does not install OpenBB.

### Testing Approach
- All OpenBB SDK calls mocked (never real network in tests)
- Guarded import tested (verify `None` returns when SDK missing)
- Never-raises contract tested (inject exceptions, verify graceful `None` returns)
- Model validators tested (NaN/Inf, UTC datetime, confidence bounds)
- Prompt sections tested (present when data exists, absent when `None`)

## Task Breakdown Preview

- [ ] **Task 1 — Foundation: Models, Enums, Config, Dependencies** (~35 tests)
  New `models/openbb.py` with 5 frozen Pydantic models + `SentimentLabel` StrEnum in `enums.py` + `OpenBBConfig` in `config.py` + optional deps in `pyproject.toml` + re-exports.

- [ ] **Task 2 — OpenBB Service Layer** (~40 tests)
  New `services/openbb_service.py` with class-based DI, guarded OpenBB import, `_obb_call()` async wrapper, `fetch_fundamentals()`, `fetch_unusual_flow()`, `fetch_news_sentiment()`, never-raises contract, cache-first pattern.

- [ ] **Task 3 — MarketContext Extension + Debate Wiring** (~15 tests)
  Add ~13 optional fields to `MarketContext`, add `enrichment_ratio()` method, extend `build_market_context()` signature, wire parallel OpenBB fetches in debate orchestrator.

- [ ] **Task 4 — Agent Prompt Enrichment** (~15 tests)
  Add 3 new sections to `render_context_block()`: Fundamental Profile, Unusual Options Flow, News Sentiment. Omitted entirely when data is `None`.

- [ ] **Task 5 — Health Checks + Integration** (~15 tests)
  Add `check_openbb()` to `HealthService.check_all()`. Integration tests verifying end-to-end debate with mocked OpenBB data. Verify CLI/API health display auto-picks up new checks.

## Dependencies

- **External packages**: `openbb>=4.0` (optional), `vaderSentiment>=3.3` (optional) — bundled as `[openbb]` extra
- **Existing services**: `ServiceCache`, `RateLimiter` — reused, not modified
- **Existing models**: `MarketContext`, `AppSettings`, `HealthStatus` — extended with optional fields
- **No blocking dependencies**: All work is additive. Existing 2,454 tests must remain green.

## Success Criteria (Technical)

| Criterion | Gate |
|-----------|------|
| `ruff check .`, `mypy --strict src/`, `pytest tests/ -v` all pass | Hard |
| Existing 2,454 tests unchanged and passing | Hard |
| OpenBB disabled → system identical to pre-integration | Hard |
| OpenBB SDK not installed → system identical to pre-integration | Hard |
| Fundamentals appear in debate context for S&P 500 tickers (mocked test) | Hard |
| Flow data appears in debate context (mocked test) | Hard |
| Sentiment scored via VADER (mocked test) | Hard |
| Health command reports OpenBB provider status | Hard |
| No paid API keys required | Hard |
| ~120 new tests | Soft |

## Estimated Effort

- **Complexity**: L (Large)
- **Tasks**: 5
- **New tests**: ~120
- **New files**: 5 (2 source + 3 test)
- **Modified files**: 9
- **Critical path**: Task 1 → Task 2 → Tasks 3/4/5 (parallel)

## Tasks Created

- [ ] #179 - Foundation — Models, Enums, Config, Dependencies (parallel: false)
- [ ] #180 - OpenBB Service Layer (parallel: false, depends: #179)
- [ ] #181 - MarketContext Extension + Debate Wiring (parallel: true, depends: #179, #180)
- [ ] #182 - Agent Prompt Enrichment (parallel: true, depends: #179, #180)
- [ ] #183 - Health Checks + Integration Testing (parallel: true, depends: #179, #180)

Total tasks: 5
Parallel tasks: 3 (#181, #182, #183)
Sequential tasks: 2 (#179 → #180)

## Test Coverage Plan

Total test files planned: 5
- `tests/unit/models/test_openbb_models.py` (~35 tests)
- `tests/unit/services/test_openbb_service.py` (~40 tests)
- `tests/unit/agents/test_openbb_context.py` (~7 tests)
- `tests/unit/agents/test_openbb_prompts.py` (~15 tests)
- `tests/unit/services/test_openbb_health.py` (~8 tests)
- `tests/integration/test_openbb_integration.py` (~15 tests)

Total test cases planned: ~120

## Future Work (Not in This Epic)

- **Epic B: CBOE Chain Migration** — `ChainProvider` protocol, CBOE as primary chain source, native Greeks, yfinance fallback. Separate epic.
- **Scan pipeline enrichment** — Fetch fundamentals/flow during scan Phase 3 for display in scan results.
- **Database persistence** — New migration for OpenBB snapshot tables.
- **Web UI enrichment panels** — Dedicated fundamentals/flow/sentiment components in debate/ticker views.
