---
name: openbb-wiring
status: backlog
created: 2026-03-02T07:03:40Z
updated: 2026-03-02T07:12:33Z
progress: 0%
prd: .claude/prds/openbb-wiring.md
research: .claude/epics/openbb-wiring/research.md
github: https://github.com/jobu711/options_arena/issues/185
---

# Epic: openbb-wiring

## Overview

Wire the existing OpenBB enrichment infrastructure (service, models, config, prompt rendering — all built and tested in PR #184 with 319 tests) into the three consumer entry points: CLI debate, FastAPI debate routes, and Vue frontend. This is pure plumbing — no new models, no new service methods, no new algorithms, no DB migrations. Every piece already exists; we connect 7 files with ~150 lines of production code.

## Architecture Decisions

- **No new abstractions**: `OpenBBService` constructor takes `(config, cache, limiter)` — identical DI pattern to `MarketDataService`/`FredService`. Reuse exactly.
- **Enrichment happens pre-debate**: Fetch fundamentals/flow/sentiment via `asyncio.gather()` before calling `run_debate_v2()`, pass as keyword args. The orchestrator already accepts these params (lines 1258-1322).
- **Never-raises contract preserved**: All OpenBB fetch calls return `None` on failure — debate proceeds without enrichment. No new error paths.
- **Config-gated creation**: `if settings.openbb.enabled:` before creating service. If disabled or SDK missing, `openbb_svc = None` and all enrichment stays `None`. Per-source toggles handled inside service methods.
- **Flat enrichment fields on API schema**: Research resolved this — extract specific fields server-side into flat optional fields on `DebateResultDetail` (not nested, not raw JSON). Matches existing typed boundary pattern.
- **No new DB migrations**: Enrichment stored in existing `market_context_json` TEXT column (migration 009). Repository already parses it to `MarketContext` model.

## Technical Approach

### Backend Services

#### CLI Wiring (FR-1, FR-2, FR-3) — `cli/commands.py`

Research identified exact insertion points:

- **Service creation** (~lines 296-299 in `_batch_async`, ~557-559 in `_debate_async`): Add `OpenBBService(settings.openbb, cache, limiter)` after existing services. Guard with `no_openbb` flag.
- **Service close** (~lines 349-356, ~596-604): Add `if openbb_svc is not None: await openbb_svc.close()` in `finally` blocks.
- **`_debate_single()`** (line 384): Add `openbb_svc: OpenBBService | None = None` param. Before `run_debate_v2()` call (line 471), fetch with `asyncio.gather()` and pass as kwargs.
- **`debate` command** (line 230): Add `--no-openbb` Typer Option (default False). When True, skip service creation.

#### API Wiring (FR-4, FR-5, FR-6, FR-7, FR-8)

- **Lifespan** (`app.py:47-89`): Create `OpenBBService` after other services, store as `app.state.openbb`. Guard with `settings.openbb.enabled`. Close at shutdown (~line 98).
- **DI** (`deps.py:21-54`): Add `get_openbb(request: Request) -> OpenBBService | None` — same pattern as `get_market_data()`.
- **Background tasks** (`debate.py`): In `_run_debate_background()` (~line 105) and `_run_batch_debate_background()` (~line 269), fetch enrichment via `asyncio.gather()` before `run_debate_v2()`. Access openbb from `request.app.state.openbb`.
- **Schema** (`schemas.py:139-165`): Add flat optional fields to `DebateResultDetail`: `pe_ratio`, `forward_pe`, `peg_ratio`, `price_to_book`, `debt_to_equity`, `revenue_growth`, `profit_margin`, `net_call_premium`, `net_put_premium`, `news_sentiment_score`, `news_sentiment_label`, `enrichment_ratio` — all `float | None` or `str | None`.
- **Serialization** (`debate.py:447-506`): In `get_debate()`, extract enrichment from `row.market_context` (already parsed by Repository) into `DebateResultDetail` constructor.

### Frontend Components

#### Types + Display (FR-9, FR-10)

- **Types** (`debate.ts:38-54`): Extend `DebateResult` interface with optional enrichment fields matching API schema.
- **Display** (`DebateResultPage.vue`): Add 3 conditional `v-if` sections below the thesis banner:
  1. **Fundamental Profile** — PE, forward PE, D/E, revenue growth, profit margin (when `pe_ratio` present)
  2. **Unusual Flow** — net call/put premium (when `net_call_premium` present)
  3. **News Sentiment** — score + label (when `news_sentiment_score` present)
- **Metadata strip** (lines 154-180): Add `enrichment_ratio` item (conditional, same pattern as `citation_density`).
- **Styling**: Use existing `.metadata-strip`, `.meta-item`, `.meta-label`, `.meta-value`, `.mono` classes. PrimeVue CSS vars for dark theme.

### Infrastructure

- No deployment changes — OpenBB SDK is optional, guarded imports handle absence.
- No new environment variables — `ARENA_OPENBB__ENABLED` already supported via `AppSettings`.
- Health check already wired in PR #184.

## Implementation Strategy

Three independent work streams, recommended solo order: **API → CLI → Frontend**.

1. **API wiring** (FR-4→FR-8): Lifespan → DI → background tasks → schema → serialization. Must define schema before frontend.
2. **CLI wiring** (FR-1→FR-3): Service creation → enrichment fetch → `--no-openbb` flag. Independent of API.
3. **Frontend** (FR-9→FR-10): Types → display sections. Depends on API schema definition.

**Risk mitigation**: All enrichment params default to `None`, so existing tests remain unaffected. Each task can be tested independently.

## Task Breakdown Preview

- [ ] Task 1: API lifecycle + DI + schema — Create OpenBBService in lifespan, add DI provider, add enrichment fields to `DebateResultDetail`, extract from `row.market_context` in `get_debate()` (FR-4, FR-5, FR-7, FR-8)
- [ ] Task 2: API debate enrichment — Fetch enrichment in `_run_debate_background()` and `_run_batch_debate_background()` before `run_debate_v2()` calls (FR-6)
- [ ] Task 3: CLI wiring — Create/close OpenBBService in `_debate_async()`/`_batch_async()`, fetch enrichment in `_debate_single()`, add `--no-openbb` flag (FR-1, FR-2, FR-3)
- [ ] Task 4: Frontend types + display — Extend TS interface, add 3 enrichment sections + enrichment_ratio metadata item (FR-9, FR-10)
- [ ] Task 5: Tests + verification — Unit tests for CLI, API lifecycle, API enrichment (~17 tests); run full suite (2,773)

## Dependencies

- **PR #184 on working branch**: All OpenBB infrastructure (service, models, config, prompt rendering, 319 tests) lives on `epic/openbb-integration` branch.
- **No external dependencies**: OpenBB SDK is optional (guarded import). Wiring works whether SDK is installed or not.

## Success Criteria (Technical)

- `options-arena debate AAPL` fetches OpenBB data when SDK is installed and `ARENA_OPENBB__ENABLED=true`
- `--no-openbb` flag skips all enrichment
- API `GET /api/debate/{id}` returns enrichment fields in `DebateResultDetail` response
- Vue frontend shows enrichment sections when data is present, hides when absent
- All 2,773 existing tests pass (enrichment defaults to `None`)
- ~17 new tests covering CLI lifecycle, API lifecycle, API enrichment, and `--no-openbb` flag
- Lint (`ruff`), format, and type check (`mypy --strict`) all pass

## Estimated Effort

- **5 tasks**, all focused on plumbing existing infrastructure
- **Complexity**: S (Small) — ~150 lines production code + ~200 lines tests across 7 files
- **Critical path**: API schema (Task 1) should precede frontend (Task 4)
- Tasks 1-3 are independent and can run in parallel

## Tasks Created

- [ ] #186 - API lifecycle + DI + schema + serialization (parallel: true)
- [ ] #187 - API debate enrichment fetch (parallel: false, depends: #186)
- [ ] #188 - CLI debate OpenBB wiring (parallel: true)
- [ ] #189 - Frontend enrichment types + display (parallel: false, depends: #186)
- [ ] #190 - Tests + full suite verification (parallel: false, depends: #186, #187, #188)

Total tasks: 5
Parallel tasks: 2 (#186, #188)
Sequential tasks: 3 (#187 → after #186, #189 → after #186, #190 → after #186-#188)
Estimated total effort: 10-14 hours

## Test Coverage Plan

Total test files planned: 3
Total test cases planned: 17
