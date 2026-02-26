---
name: web-ui
status: backlog
created: 2026-02-26T10:58:45Z
progress: 0%
prd: .claude/prds/web-ui.md
github: https://github.com/jobu711/options_arena/issues/121
---

# Epic: web-ui

## Overview

Add a Vue 3 SPA frontend + FastAPI backend to Options Arena. The API is a thin wrapper
over existing services (zero business logic duplication). WebSocket streams real-time
progress for scans and debates. Built as vertical slices — scan end-to-end first, then
debate end-to-end. Localhost-only, single-user, no auth.

## Architecture Decisions

- **FastAPI + Vue 3 + Vite**: FastAPI natively serializes Pydantic models. Vue 3 Composition
  API + TypeScript for the SPA. Vite for dev server + build.
- **PrimeVue (Aura dark theme)**: DataTable, Drawer, Dialog, Toast — eliminates custom
  table/drawer/modal work. Financial accent colors via CSS custom properties.
- **Service lifecycle via FastAPI `lifespan`**: Services created once at startup, injected
  via `Depends()`. Unlike CLI (per-command), API keeps services alive across requests.
- **Operation mutex**: `asyncio.Lock` — one scan or batch debate at a time. 409 Conflict if busy.
- **WebSocket for progress**: Scan pipeline's `ProgressCallback` bridges to WebSocket via
  `asyncio.Queue`. Debate orchestrator gets a new optional callback parameter.
- **`DebateResult` → Pydantic model**: Required for FastAPI auto-serialization. Currently a
  `@dataclass`. Inner fields are already Pydantic models.
- **Vertical slice build order**: Scan end-to-end first, then debate, then supporting pages.
- **Decimal → JSON string**: Prices serialize as strings (not floats). Frontend formats for
  display but never converts to JS `number`.
- **`options-arena serve` command**: Single CLI command starts FastAPI + serves built Vue SPA.

## Technical Approach

### Backend (`src/options_arena/api/`)

Top-of-stack module (same rules as `cli/`). Routes → services via DI (`Depends()`).
Returns existing Pydantic models directly. Catches domain exceptions → HTTP errors.

Key files: `app.py` (factory + lifespan), `deps.py` (DI providers), `routes/` (6 route
modules), `ws.py` (WebSocket handlers), `schemas.py` (thin request/response wrappers).

### Frontend (`web/`)

Separate build target (Node.js/npm). 6 routes, 4 Pinia stores, 5 custom components,
3 composables. Presentation only — zero business logic. PrimeVue for all UI primitives.

### Engine Changes (Pre-Requisites)

Three additive changes with no breaking impact:
1. Convert `DebateResult` from `@dataclass` to Pydantic `BaseModel(frozen=True)`
2. Add optional `DebateProgressCallback` to `run_debate()` in orchestrator
3. Add `get_debate_by_id()` to Repository

## Implementation Strategy

Build in vertical slices. Each task delivers a working end-to-end feature. Earlier tasks
are foundations for later ones. All existing 1,484 tests must remain green throughout.

**Testing approach**: Backend routes tested with FastAPI `TestClient` + mocked services.
Frontend tested with Vitest + Vue Test Utils + MSW. Aim for >= 90% endpoint coverage.

## Task Breakdown Preview

- [ ] Task 1: Engine pre-requisites — DebateResult conversion, debate progress callback, repo method
- [ ] Task 2: Project scaffold — FastAPI app factory + lifespan + deps + Vue project + PrimeVue + `serve` command
- [ ] Task 3: Scan API — REST endpoints (POST/GET scan, GET scores) + WebSocket progress + cancellation
- [ ] Task 4: Scan frontend — ScanPage + ScanResultsPage with PrimeVue DataTable + URL state + TickerDrawer
- [ ] Task 5: Debate API — REST endpoints (POST/GET debate) + WebSocket progress + export endpoint
- [ ] Task 6: Debate frontend — DebateResultPage + AgentCards + DebateProgressModal on scan page
- [ ] Task 7: Batch debate — POST /api/debate/batch + batch progress modal + summary table
- [ ] Task 8: Supporting pages + Dashboard — DashboardPage, UniversePage, HealthPage, config endpoint

## Dependencies

### Task Dependencies

```
Task 1 (engine pre-reqs)
  └─► Task 2 (scaffold)
        ├─► Task 3 (scan API) ──► Task 4 (scan frontend)
        │                           └─► Task 6 (debate frontend)
        └─► Task 5 (debate API) ──► Task 6 (debate frontend)
                                      └─► Task 7 (batch debate)
        └─► Task 8 (supporting pages) — can run after Task 2
```

### External Dependencies

- **New Python deps**: `fastapi`, `uvicorn[standard]` — added via `uv add`
- **New npm deps**: `vue`, `vue-router`, `pinia`, `primevue`, `@primeuix/themes`,
  `primeicons`, `typescript`, `vite`, `@vitejs/plugin-vue`, `openapi-typescript`
- **No new external services** — all existing services unchanged

### Internal Dependencies

- Existing service layer (`services/`), scan pipeline (`scan/`), debate orchestrator
  (`agents/`), data layer (`data/`), models (`models/`) — all consumed read-only by API
- `DebateResult` conversion (Task 1) must complete before any debate API work
- `web/CLAUDE.md` already defines all frontend conventions

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Core workflow (scan → browse → debate → view result) end-to-end | Working |
| API endpoint test coverage | >= 90% |
| Existing test suite (1,484 tests) | All green |
| Frontend initial load (localhost) | < 3s |
| WebSocket event latency (engine → browser) | < 500ms |
| Zero business logic in `api/` module | Verified |
| Engine pre-requisite changes fully tested | Yes |
| Decimal prices never parsed to JS `number` | Verified |

## Estimated Effort

| Task | Scope |
|------|-------|
| 1. Engine pre-requisites | ~100 lines Python + tests |
| 2. Project scaffold | FastAPI factory + Vue init + PrimeVue + serve cmd |
| 3. Scan API | 5 REST endpoints + WebSocket + tests |
| 4. Scan frontend | 2 pages + DataTable + Drawer + URL state |
| 5. Debate API | 5 REST endpoints + WebSocket + export + tests |
| 6. Debate frontend | 1 page + AgentCards + ProgressModal |
| 7. Batch debate | 1 API endpoint + batch modal + summary |
| 8. Supporting pages | 3 pages + 2 API endpoints |

**Critical path**: Tasks 1 → 2 → 3 → 4 (scan slice), then 5 → 6 → 7 (debate slice).
Task 8 can run in parallel after Task 2.

## Tasks Created

- [ ] #122 - Engine pre-requisites for Web API (parallel: false)
- [ ] #124 - Project scaffold — FastAPI + Vue + serve command (parallel: false)
- [ ] #126 - Scan API — REST endpoints + WebSocket progress (parallel: true)
- [ ] #128 - Scan frontend — ScanPage + ScanResultsPage + TickerDrawer (parallel: false)
- [ ] #123 - Debate API — REST endpoints + WebSocket progress + export (parallel: true)
- [ ] #125 - Debate frontend — DebateResultPage + AgentCards + progress modal (parallel: false)
- [ ] #127 - Batch debate — API endpoint + batch progress modal (parallel: false)
- [ ] #129 - Supporting pages — Dashboard + Universe + Health + Config (parallel: true)

Total tasks: 8
Parallel tasks: 3 (#126, #123, #129 — can run concurrently after their deps)
Sequential tasks: 5 (#122, #124, #128, #125, #127 — on critical path)
