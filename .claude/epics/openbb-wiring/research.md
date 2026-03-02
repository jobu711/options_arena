# Research: openbb-wiring

## PRD Summary

Wire the 3 consumer entry points (CLI debate, FastAPI debate routes, Vue frontend) to the fully-built OpenBB enrichment infrastructure so `fundamentals`, `flow`, and `sentiment` params on `run_debate_v2()` are no longer always `None`.

## Relevant Existing Modules

- `services/openbb_service.py` — Complete. Constructor `(config, cache, limiter)`, 3 fetch methods (never-raises), `close()` (no-op). Ready to instantiate.
- `models/openbb.py` — 5 frozen models: `FundamentalSnapshot`, `UnusualFlowSnapshot`, `NewsHeadline`, `NewsSentimentSnapshot`, `OpenBBHealthStatus`.
- `models/config.py:266-283` — `OpenBBConfig` with master toggle, per-source toggles, TTLs. Already wired as `AppSettings.openbb`.
- `models/analysis.py:102-119` — `MarketContext` has 11 enrichment fields + `enrichment_ratio()`.
- `agents/orchestrator.py:1258-1322` — `run_debate_v2()` already accepts `fundamentals`, `flow`, `sentiment` kwargs.
- `agents/orchestrator.py:98-220` — `build_market_context()` maps snapshots → MarketContext enrichment fields.
- `agents/_parsing.py` — Prompt rendering already builds Fundamental/Flow/Sentiment sections from MarketContext.
- `cli/commands.py` — Debate commands create services but NOT OpenBBService. **Target for wiring.**
- `api/app.py` — Lifespan creates services but NOT OpenBBService. **Target for wiring.**
- `api/routes/debate.py` — Background tasks call `run_debate_v2()` without enrichment. **Target for wiring.**
- `api/schemas.py` — `DebateResultDetail` lacks enrichment fields. **Target for extension.**
- `web/src/types/debate.ts` — `DebateResult` interface lacks enrichment. **Target for extension.**
- `web/src/pages/DebateResultPage.vue` — No enrichment display. **Target for UI addition.**

## Existing Patterns to Reuse

### CLI Service Lifecycle (commands.py)
```python
# Creation (~lines 296-299 in _batch_async, ~557-559 in _debate_async)
market_data = MarketDataService(settings.service, cache, limiter)
options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter)
fred = FredService(settings.service, settings.pricing, cache)

# Close (~lines 349-356 in _batch_async, ~596-604 in _debate_async)
finally:
    if market_data is not None:
        await market_data.close()
    # ... same for each service
```
**Reuse**: Add `OpenBBService(settings.openbb, cache, limiter)` to creation block. Add `openbb_svc.close()` to finally.

### API Lifespan (app.py:44-102)
```python
# Startup (~lines 47-89)
market_data = MarketDataService(settings.service, cache, limiter)
app.state.market_data = market_data
# Shutdown (~lines 95-101)
await market_data.close()
```
**Reuse**: Add OpenBBService creation + `app.state.openbb` + close.

### DI Providers (deps.py:21-54)
```python
def get_market_data(request: Request) -> MarketDataService:
    return request.app.state.market_data  # type: ignore[no-any-return]
```
**Reuse**: Add `get_openbb()` returning `OpenBBService | None`.

### Background Task Enrichment (debate.py)
```python
# _run_debate_background (~line 105)
result = await run_debate_v2(
    ticker_score=score_match, contracts=contracts, quote=quote,
    ticker_info=ticker_info, config=settings.debate, ...
)
```
**Reuse**: Fetch 3 snapshots via `asyncio.gather()` before this call, pass as kwargs.

### Vue Conditional Rendering (DebateResultPage.vue:154-180)
```vue
<div v-if="debateStore.currentDebate.citation_density !== null" class="meta-item">
  <span class="meta-label">Citation Density</span>
  <span class="meta-value mono">{{ (debateStore.currentDebate.citation_density * 100).toFixed(0) }}%</span>
</div>
```
**Reuse**: Same `v-if` guard pattern for enrichment fields and enrichment_ratio.

## Existing Code to Extend

| File | What Exists | What to Add |
|------|-------------|-------------|
| `cli/commands.py:230-241` | `debate` command signature (7 Typer Options) | `--no-openbb` flag |
| `cli/commands.py:384-393` | `_debate_single()` signature (6 params + fallback_only) | `openbb_svc: OpenBBService \| None = None` param |
| `cli/commands.py:471-495` | `_debate_single()` calls `run_debate_v2()` | Fetch enrichment, pass `fundamentals=`, `flow=`, `sentiment=` |
| `api/app.py:47-89` | Lifespan creates 4 services | Add OpenBBService (guarded) |
| `api/app.py:95-101` | Lifespan closes 4 services | Add `openbb.close()` |
| `api/deps.py:21-54` | 7 DI providers | Add `get_openbb()` |
| `api/routes/debate.py:105-114` | `run_debate_v2()` call (no enrichment) | Fetch + pass enrichment |
| `api/routes/debate.py:269-281` | Batch `run_debate_v2()` call (no enrichment) | Same |
| `api/routes/debate.py:447-506` | `get_debate()` constructs `DebateResultDetail` | Extract enrichment from `row.market_context` |
| `api/schemas.py:139-165` | `DebateResultDetail` (20 fields) | Add ~8 enrichment display fields |
| `web/src/types/debate.ts:38-54` | `DebateResult` interface (14 fields) | Add matching enrichment fields |
| `web/src/pages/DebateResultPage.vue:122-180` | Agent cards + metadata strip | Add enrichment sections below thesis |

## Potential Conflicts

- **None identified.** All enrichment params default to `None`, so existing code paths are unaffected. OpenBBService follows the never-raises contract — no new error paths. The `market_context_json` column already exists and stores enrichment when populated.

## Open Questions

1. **Schema design**: Should enrichment fields be flat on `DebateResultDetail` (e.g., `pe_ratio`, `forward_pe`) or nested in a sub-object (e.g., `enrichment: EnrichmentData | None`)? Flat is simpler and matches existing pattern; nested groups logically.
2. **Raw JSON vs parsed fields**: Should API return `market_context_json` as raw string (frontend parses) or extract specific fields server-side? Extracting server-side is safer and matches typed model pattern.

**Recommendation**: Extract specific fields server-side into flat optional fields on `DebateResultDetail`. This maintains the typed boundary pattern and gives the frontend simple nullable fields to render.

## Recommended Architecture

### Data Flow
```
CLI/API debate command
  → Create OpenBBService (if enabled + SDK installed)
  → asyncio.gather(fetch_fundamentals, fetch_unusual_flow, fetch_news_sentiment)
  → Pass to run_debate_v2(fundamentals=..., flow=..., sentiment=...)
  → Orchestrator calls build_market_context() which maps to 11 fields
  → MarketContext serialized to market_context_json (already done)
  → API get_debate() extracts enrichment fields from row.market_context
  → DebateResultDetail includes enrichment fields
  → Frontend renders conditionally with v-if guards
```

### Key Design Decisions
- **Config-gated creation**: `if settings.openbb.enabled:` before creating service. If disabled or SDK missing, `openbb_svc = None` and all enrichment stays `None`.
- **Parallel fetch**: All 3 enrichment calls via `asyncio.gather()` — they're independent.
- **No new DB migrations**: Enrichment stored in existing `market_context_json` TEXT column.
- **Repository already parses**: `DebateRow.market_context: MarketContext | None` is populated from JSON.

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/cli/test_debate_*.py` — Mock services, verify `run_debate_v2()` called with expected args
- `tests/unit/api/test_debate_routes.py` — `httpx.AsyncClient` against test app, mock repo
- `tests/unit/api/test_app_lifespan.py` — Test lifespan creates/closes services
- `tests/unit/services/test_openbb_service.py` — Already has 100+ tests for the service itself

### New Tests Needed
| File | Count | What to Test |
|------|-------|-------------|
| `tests/unit/cli/test_debate_openbb.py` | ~8 | Service creation/close, enrichment fetch, `--no-openbb` skip |
| `tests/unit/api/test_debate_openbb.py` | ~6 | Enrichment in background tasks, DebateResultDetail fields |
| `tests/unit/api/test_app_lifespan_openbb.py` | ~3 | Lifespan creates/closes OpenBBService |
| **Total** | **~17** | |

### Mocking Strategy
- Mock `OpenBBService` constructor (avoid SDK import)
- Mock `fetch_*` methods to return fixture snapshots
- Verify kwargs passed to `run_debate_v2()` include enrichment

## Estimated Complexity

**S (Small)** — Pure plumbing of existing infrastructure. No new models, no new algorithms, no new service methods, no DB migrations. Every piece exists; we connect 7 files with ~150 lines of new production code + ~200 lines of tests.
