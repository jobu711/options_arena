---
name: openbb-wiring
description: Wire existing OpenBB enrichment infrastructure to CLI debate, Web API, and Vue frontend
status: backlog
created: 2026-03-02T07:02:05Z
---

# OpenBB End-to-End Wiring

## Executive Summary

The OpenBB enrichment infrastructure (service, models, config, MarketContext fields, prompt rendering, health checks) is fully built and tested but never invoked. This PRD wires the 3 consumer entry points — CLI debate commands, FastAPI debate routes, and the Vue 3 frontend — so enrichment data flows from `OpenBBService` through to the user's screen.

## Problem

`_debate_single()` and `_batch_async()` in `cli/commands.py` never create `OpenBBService`. The API lifespan doesn't create it. The frontend has no UI for enrichment data. Result: `fundamentals`, `flow`, `sentiment` params on `run_debate()` and `run_debate_v2()` are always `None` despite full backend support.

## User Stories

**US-1: CLI Enriched Debates**
As a CLI user running `options-arena debate AAPL`, I want the debate to automatically fetch fundamentals, flow, and sentiment so agents have richer context. A `--no-openbb` flag provides an opt-out.

**US-2: API Enriched Debates**
As a web UI user starting a debate, I want the API to fetch OpenBB data so browser-initiated debates have the same enrichment as CLI.

**US-3: Frontend Enrichment Display**
As a user viewing debate results, I want to see fundamentals, flow signals, and news sentiment sections so I can assess the data quality informing the AI debate.

## Functional Requirements

| FR | Scope | Files | Detail |
|----|-------|-------|--------|
| FR-1 | CLI lifecycle | `cli/commands.py` | Create `OpenBBService(settings.openbb, cache, limiter)` in `_debate_async()` and `_batch_async()`, close in `finally`, pass to `_debate_single()` |
| FR-2 | CLI enrichment fetch | `cli/commands.py` | In `_debate_single()`, fetch fundamentals/flow/sentiment via `asyncio.gather()`, pass to `run_debate()` / `run_debate_v2()` |
| FR-3 | CLI flag | `cli/commands.py` | Add `--no-openbb` flag to `debate` command; when True, skip service creation |
| FR-4 | API lifecycle | `api/app.py` | Create `OpenBBService` in `lifespan()`, store on `app.state.openbb`, close at shutdown |
| FR-5 | API DI | `api/deps.py` | Add `get_openbb()` dependency provider |
| FR-6 | API enrichment fetch | `api/routes/debate.py` | Fetch enrichment in `_run_debate_background()` and `_run_batch_debate_background()` before `run_debate_v2()` |
| FR-7 | API response schema | `api/schemas.py` | Add enrichment fields to `DebateResultDetail` (pe_ratio, forward_pe, debt_to_equity, etc. + enrichment_ratio) |
| FR-8 | API serialization | `api/routes/debate.py` | Parse `market_context_json` -> extract enrichment fields for response |
| FR-9 | Frontend types | `web/src/types/debate.ts` | Add enrichment fields to `DebateResult` TypeScript interface |
| FR-10 | Frontend display | `web/src/pages/DebateResultPage.vue` | 3 conditional sections: Fundamental Profile, Unusual Flow, News Sentiment + enrichment_ratio in metadata strip |

## Key Files

**Backend (modify)**:
- `src/options_arena/cli/commands.py` — FR-1, FR-2, FR-3
- `src/options_arena/api/app.py` — FR-4
- `src/options_arena/api/deps.py` — FR-5
- `src/options_arena/api/routes/debate.py` — FR-6, FR-8
- `src/options_arena/api/schemas.py` — FR-7

**Frontend (modify)**:
- `web/src/types/debate.ts` — FR-9
- `web/src/pages/DebateResultPage.vue` — FR-10

**Reference (read-only)**:
- `src/options_arena/services/openbb_service.py` — constructor pattern, `close()`, 3 fetch methods
- `src/options_arena/agents/orchestrator.py:275` — `run_debate()` accepts fundamentals/flow/sentiment
- `src/options_arena/agents/orchestrator.py:1258` — `run_debate_v2()` accepts fundamentals/flow/sentiment
- `src/options_arena/models/analysis.py` — MarketContext with 11 enrichment fields + `enrichment_ratio()`
- `src/options_arena/models/config.py:266` — `OpenBBConfig` (enabled, per-source toggles, TTLs)

## Existing Patterns to Reuse

- **Service lifecycle**: `MarketDataService`/`FredService` creation at `cli/commands.py:296-299`, close at `349-356`
- **API lifespan**: `api/app.py:64-78` (create), `95-98` (close)
- **DI provider**: `api/deps.py` — `get_market_data()`, `get_options_data()` patterns
- **Parallel fetch**: `asyncio.gather()` pattern used throughout services
- **Frontend conditional sections**: `v-if` on data presence, PrimeVue Panel for optional sections
- **Metadata strip**: `DebateResultPage.vue` lines 154-180 for metadata items

## Test Plan

| New Tests | Count | Scope |
|-----------|-------|-------|
| `tests/unit/cli/test_debate_openbb.py` | ~8 | CLI creates/closes OpenBBService, fetches enrichment, `--no-openbb` skips |
| `tests/unit/api/test_debate_openbb.py` | ~6 | API fetches enrichment, DebateResultDetail includes enrichment fields |
| `tests/unit/api/test_app_lifespan_openbb.py` | ~3 | Lifespan creates/closes OpenBBService |
| **Total** | **~17** | |

**Verify no breakage**: Run full suite (2,773 tests) — all enrichment params default to `None` so existing tests are unaffected.

## Out of Scope

- Epic B CBOE chain migration (separate PRD)
- Scan pipeline enrichment (debate-time only by design)
- Fundamental scoring engine integration
- New OpenBB models or service methods (all built in PR #184)
- Health check changes (already wired in PR #184)
- Database migrations (enrichment stored in existing `market_context_json` TEXT field)

## Sequencing

3 parallel work streams:
1. **CLI wiring** (FR-1 through FR-3) — independent
2. **API wiring** (FR-4 through FR-8) — independent
3. **Frontend** (FR-9, FR-10) — can build optimistically against planned API schema

Recommended solo order: API -> CLI -> Frontend
