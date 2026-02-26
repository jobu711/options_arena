---
name: web-ui
description: Web UI for Options Arena — FastAPI backend, Vue 3 SPA, WebSocket progress
status: backlog
created: 2026-02-26T10:11:52Z
updated: 2026-02-26T10:52:01Z
---

# PRD: Web UI for Options Arena (Revised)

## Architecture Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Kept: FastAPI + Vue 3 + Vite** | Sound choice. FastAPI natively serializes Pydantic models (zero adapter code). Vue 3 Composition API + TypeScript gives type safety without React's ecosystem weight. Context7-verified. |
| 2 | **Kept: WebSocket for progress** | Scan pipeline already has `ProgressCallback` protocol — WebSocket callback is a drop-in. Bidirectional needed for cancellation signals. SSE considered (simpler) but rejected because cancellation requires client→server messages. |
| 3 | **Kept: localhost-only, single-user, no auth** | Correct for personal tool. Over-engineering auth for v1 adds weeks of work with zero user value. |
| 4 | **Changed: Route structure reduced from 10 to 6** | Original had `/debate`, `/debate/batch`, `/debate/:id`, `/history` as separate pages. Debates launch from scan results (not standalone). History is a tab, not a page. Batch debate is a button on scan results, not a route. |
| 5 | **Changed: Service lifecycle uses FastAPI `lifespan`** | Original PRD didn't address this. CLI creates/destroys services per command — too slow for API. Services must be app-scoped singletons created at startup, injected via `Depends()`. This is the single most important architecture decision. |
| 6 | **Changed: `DebateResult` must become Pydantic model** | Currently a `@dataclass`. FastAPI can't auto-serialize it with the same fidelity as Pydantic models. Small refactor needed before API work begins. |
| 7 | **Changed: Debate orchestrator needs `ProgressCallback`** | Original PRD assumed progress streaming exists. It doesn't — orchestrator only logs. Must add optional callback parameter (~50 lines, no breaking changes). |
| 8 | **Changed: Vue app at `web/` (top-level), not inside `src/`** | Vue has its own toolchain (Node.js/npm). Putting it inside the Python package would include it in the wheel. Separate build target, separate directory. |
| 9 | **Changed: Settings page removed** | For a localhost tool, settings live in `.env` / config file. A settings UI adds significant complexity (validation, persistence, restart semantics) for marginal value. Config is read-only via `/api/config`. |
| 10 | **Added: Decimal serialization contract** | Original PRD didn't address this. All price fields (strike, bid, ask) serialize to JSON strings (not floats) via existing `@field_serializer`. Frontend must parse string prices. |
| 11 | **Added: Operation mutex** | One long-running operation at a time (scan or batch debate). API returns 409 Conflict if busy. Frontend shows global "operation in progress" state. |
| 12 | **Added: PrimeVue component library** | User chose PrimeVue for DataTable, Drawer, Toast, and UI primitives. Eliminates custom table/drawer work. PrimeVue's DataTable has built-in sort, filter, paginate, virtual scroll, row selection. |
| 13 | **Added: CLI/Web coexistence** | SQLite WAL mode supports concurrent readers. CLI and web UI can run simultaneously against the same database. User may run `options-arena scan` then view results in browser. |
| 14 | **Added: `options-arena serve` command** | Single CLI command starts FastAPI + serves built Vue SPA. Auto-opens browser. Dev mode uses separate processes (uvicorn + vite dev). |
| 15 | **Added: Toast notifications** | PrimeVue Toast for success/error/warning. Auto-dismiss after 5s. Used for background operation results and errors. |
| 16 | **Added: URL-persisted filter state** | Scan results table filters, sort, and pagination reflected in URL query params (`/scan/42?sort=score&dir=bullish`). Browser back/forward works. Bookmarkable. |
| 17 | **Added: Debate stays on scan page** | Debate progress shows in a modal/drawer on scan results page. User is NOT navigated away. Auto-redirect to `/debate/:id` only when complete. |
| 18 | **Added: Batch debate progress modal** | Modal overlay on scan results page shows current ticker, overall progress (3/5), mini-results as each completes. |
| 19 | **Added: Vertical slice build order** | Build scan end-to-end first (API + Vue page + WebSocket). Then debate end-to-end. Feature-by-feature, not layer-by-layer. |
| 20 | **Removed: Regulatory disclaimer** | User explicitly opted out. No disclaimer in web UI. |

---

## Overview

### Core User Workflow

The web UI serves one workflow with four steps:

```
Screen → Analyze → Decide → Record
  │         │         │        │
  Scan    Browse    Debate   Export/History
```

Every UI decision traces back to this flow. Features that don't serve it are deferred.

### Problem Statement

*Preserved from original — these are accurate:*

- **Scan results are ephemeral** — terminal history is the only record. The web UI provides persistent, sortable, filterable views backed by SQLite.
- **Debate output is text-heavy** — bull/bear/risk arguments are hard to compare side-by-side in a 99-column terminal.
- **No visual overview** — no dashboard for scan summaries, top scorers, or debate history.

The core engine is stable (v1.5.0, 1,483 tests). The service layer, models, and orchestration code are ready to be exposed through an API.

### What We're Building

A Vue 3 SPA served by a FastAPI backend. Runs on localhost for personal use. The API is a thin wrapper over existing services — zero business logic duplication. WebSocket streams real-time progress for scans and debates.

---

## System Architecture

### Layer Diagram

```
┌─────────────────────────────────────────┐
│  Vue 3 SPA (web/)                       │
│  Vite + TypeScript + Pinia + Vue Router │
└──────────────┬──────────────────────────┘
               │ HTTP REST + WebSocket
┌──────────────▼──────────────────────────┐
│  FastAPI (src/options_arena/api/)        │
│  Routes → Services (DI via Depends)     │
│  WebSocket handlers for progress        │
│  StaticFiles serves built SPA           │
└──────────────┬──────────────────────────┘
               │ Direct Python imports
┌──────────────▼──────────────────────────┐
│  Existing Engine (unchanged)            │
│  services/ scan/ agents/ models/ data/  │
└─────────────────────────────────────────┘
```

### Module Boundary

`api/` follows the same rules as `cli/` — it's a top-of-stack entry point:

| Rule | Detail |
|------|--------|
| Can import | Everything: `models/`, `services/`, `scan/`, `agents/`, `data/`, `reporting/` |
| Cannot contain | Business logic, pricing math, indicator computation |
| Serialization | Returns existing Pydantic models directly — FastAPI handles JSON |
| Error handling | Catches domain exceptions → HTTP error responses |

### Project Structure

```
src/options_arena/
    api/                      # NEW — FastAPI backend
        __init__.py           # Re-exports: app, create_app
        app.py                # App factory, lifespan, CORS, static mount
        deps.py               # Depends() providers: services, config, operation lock
        routes/
            __init__.py
            scan.py           # POST /api/scan, GET /api/scan, GET /api/scan/{id}/scores
            debate.py         # POST /api/debate, GET /api/debate/{id}, POST /api/debate/batch
            universe.py       # GET /api/universe, POST /api/universe/refresh
            health.py         # GET /api/health
            config.py         # GET /api/config (read-only)
            export.py         # GET /api/debate/{id}/export
        ws.py                 # WebSocket: /ws/scan/{id}, /ws/debate/{id}
        schemas.py            # API-only request/response wrappers (thin)
        CLAUDE.md             # Module rules

web/                          # NEW — Vue 3 SPA (separate from Python package)
    src/
        App.vue
        main.ts
        router/index.ts       # 6 routes, URL state for filters/sort
        stores/               # Pinia stores: scan, debate, health, operation
        pages/                # Page components (1 per route)
        components/           # AgentCard, ProgressTracker, ConfidenceBadge, DirectionBadge
        composables/          # useWebSocket, useApi, useOperation
        api/                  # Generated typed client from OpenAPI
        types/                # TypeScript interfaces (from OpenAPI schema)
    package.json              # PrimeVue, vue, vue-router, pinia, typescript, vite
    vite.config.ts
    tsconfig.json
```

### Service Lifecycle (FastAPI Lifespan)

The CLI creates/destroys services per command. The API must keep services alive across requests.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all services once
    settings = AppSettings()
    db = Database(DATA_DIR / "options_arena.db")
    await db.connect()                          # runs migrations
    repo = Repository(db)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(settings.service)

    app.state.settings = settings
    app.state.repo = repo
    app.state.market_data = MarketDataService(settings.service, cache, limiter)
    app.state.options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter)
    app.state.fred = FredService(settings.service, settings.pricing, cache)
    app.state.universe = UniverseService(settings.service, cache, limiter)
    app.state.operation_lock = asyncio.Lock()   # one scan/debate at a time

    yield

    # Shutdown: close all services
    await app.state.market_data.close()
    await app.state.options_data.close()
    await app.state.fred.close()
    await app.state.universe.close()
    await db.close()

app = FastAPI(title="Options Arena", lifespan=lifespan)
```

**Dependency injection:**
```python
from fastapi import Depends, Request

def get_repo(request: Request) -> Repository:
    return request.app.state.repo

def get_market_data(request: Request) -> MarketDataService:
    return request.app.state.market_data

# Used in routes:
@router.get("/api/scan/{scan_id}/scores")
async def get_scores(scan_id: int, repo: Repository = Depends(get_repo)) -> list[TickerScore]:
    return await repo.get_scores_for_scan(scan_id)
```

### Operation Mutex

One long-running operation (scan or batch debate) at a time. The `asyncio.Lock` in `app.state.operation_lock` guards this:

```python
@router.post("/api/scan", status_code=202)
async def start_scan(
    request: ScanRequest,
    lock: asyncio.Lock = Depends(get_operation_lock),
) -> ScanStarted:
    if lock.locked():
        raise HTTPException(409, "Another operation is in progress")
    # acquire lock, start scan in background task, return scan_id
```

Single-ticker debates are fast enough (~60s) to not need the lock. Only scans and batch debates acquire it.

---

## UI Components

### Route Structure (6 routes, down from 10)

| Route | Page | Maps to Workflow Step |
|-------|------|-----------------------|
| `/` | Dashboard | Overview: latest scan summary, health indicators, quick actions |
| `/scan` | Scan | Screen: run scan, list past scans |
| `/scan/:id` | Scan Results | Analyze: sortable/filterable ticker table, click row → ticker detail drawer |
| `/debate/:id` | Debate Result | Decide: full agent arguments, thesis, export button |
| `/universe` | Universe | Supporting: view/refresh ticker universe |
| `/health` | Health | Supporting: service health dashboard |

**Routes removed from original:**
- `/debate` (standalone) — debates launch from scan results, not a blank page
- `/debate/batch` — batch is a button on scan results, not a separate page
- `/history` — scan list is on `/scan`, debate history is on ticker detail
- `/settings` — config stays in `.env`; read-only view at `/api/config` if needed

### Page Descriptions

#### Dashboard (`/`)
- **Latest scan card**: preset, date, ticker count, top 5 scorers with direction badges
- **Health strip**: colored dots per service (green/yellow/red), auto-refreshes every 60s
- **Quick actions**: "Run Scan" button, "View Latest Results" link
- **Recent debates**: last 5 debates with ticker, verdict, confidence

#### Scan Page (`/scan`)
- **Scan launcher**: preset dropdown + "Run Scan" button
- **Progress panel** (visible during scan): 4-phase progress bar with ticker counts, cancel button
- **Past scans list**: table with date, preset, ticker count, click to view results

#### Scan Results (`/scan/:id`)
- **PrimeVue DataTable**: all TickerScore fields as columns
  - Sort: click header (asc/desc toggle) — PrimeVue built-in
  - Filter: direction dropdown, minimum score slider, ticker search — PrimeVue column filters
  - Pagination: 50 rows per page (configurable) — PrimeVue Paginator
  - Virtual scroll enabled if > 1,000 rows — PrimeVue `virtualScrollerOptions`
  - Row selection (checkbox column) for batch debate
- **URL state**: sort, filter, page params synced to URL query string (`?sort=composite_score&order=desc&direction=bullish&page=2`). Browser back/forward preserves state.
- **Row actions**: "Debate" button per row, row click opens detail drawer
- **Batch actions**: select multiple rows → "Debate Selected" button
- **Ticker detail drawer** (PrimeVue Drawer, right-side slide-out):
  - Indicator breakdown (18 signals with raw + normalized values)
  - Recommended contracts table (strike, type, bid/ask, mid, Greeks, IV)
  - Past debate history for this ticker
- **Debate progress modal** (PrimeVue Dialog, modal overlay):
  - Shows when debate is triggered from this page (single or batch)
  - Agent-by-agent progress tracker (Bull → Bear → ... → Risk)
  - For batch: current ticker, overall progress (3/5), mini-results per ticker
  - Auto-navigates to `/debate/:id` on completion (single) or shows summary table (batch)

#### Debate Result (`/debate/:id`)
- **Agent cards** (side-by-side layout):
  - Bull card: direction, confidence bar, key points, risks cited
  - Bear card: same layout, visually distinct color
  - Rebuttal card (if enabled): bull's counter-argument
  - Volatility card (if enabled): IV analysis, recommended strategy
- **Thesis banner**: verdict (BULLISH/BEARISH/NEUTRAL), confidence %, strategy, entry/exit
- **Metadata**: model used, duration, token usage, citation density, is_fallback flag
- **Export button**: dropdown with Markdown / PDF options → browser download

#### Universe (`/universe`)
- **Stats bar**: total optionable tickers, S&P 500 count, last refresh timestamp
- **Refresh button**: triggers re-fetch with loading indicator
- **Ticker list**: searchable table with ticker, sector (S&P 500 only)

#### Health (`/health`)
- **Service cards**: one per service (Groq, Yahoo Finance, FRED, CBOE)
  - Status badge (OK / Down), latency, last checked, error message if any
- **Re-check button**: runs all health checks, updates cards

### Shared Components

**PrimeVue components (used directly, not wrapped):**
- `DataTable` + `Column` — sort, filter, paginate, virtual scroll, row selection
- `Drawer` — right-side slide-out for ticker detail
- `Dialog` — modal overlay for debate progress
- `Toast` — slide-in notifications (success/error/warning, auto-dismiss 5s)
- `Button`, `Tag`, `Badge`, `ProgressBar`, `Skeleton` — standard primitives

**Custom components (project-specific):**

| Component | Props | Used By |
|-----------|-------|---------|
| `ProgressTracker` | phases[], currentPhase, current, total | Scan progress, Batch debate progress |
| `AgentCard` | agentName, response: AgentResponse, color | Debate Result |
| `ConfidenceBadge` | value: number, size | Everywhere confidence appears |
| `DirectionBadge` | direction: "bullish" \| "bearish" \| "neutral" | Scan Results, Debate Result |
| `HealthDot` | status: "ok" \| "degraded" \| "down" | Dashboard, Health page |

---

## Data Flow

### Scan Flow (End-to-End)

```
[Frontend]                    [API]                         [Engine]
    │                           │                              │
    ├─POST /api/scan ──────────►│                              │
    │  {preset: "sp500"}        ├─acquire operation_lock       │
    │                           ├─create CancellationToken     │
    │◄─202 {scan_id: 42} ──────┤                              │
    │                           ├─asyncio.create_task(         │
    ├─WS /ws/scan/42 ──────────►│  pipeline.run(              │
    │  (subscribe to progress)  │    preset, token,            │
    │                           │    ws_callback))  ──────────►│
    │                           │                              ├─Phase 1: Universe
    │◄─{phase:"universe",       │◄─callback(UNIVERSE,0,5286)──┤
    │   current:0,total:5286}   │                              ├─Phase 2: Scoring
    │◄─{phase:"scoring",...}    │◄─callback(SCORING,...)  ────┤
    │                           │                              ├─Phase 3: Options
    │◄─{phase:"options",...}    │◄─callback(OPTIONS,...)  ────┤  (incremental per ticker)
    │                           │                              ├─Phase 4: Persist
    │◄─{phase:"persist",...}    │◄─callback(PERSIST,1,1)  ────┤
    │◄─{type:"complete",        │◄─ScanResult ────────────────┤
    │   scan_id:42}             │  release operation_lock      │
    │                           │                              │
    ├─GET /api/scan/42/scores ─►│                              │
    │  ?sort=composite_score    ├─repo.get_scores_for_scan()   │
    │  &direction=bullish       │                              │
    │◄─[TickerScore, ...] ─────┤                              │
```

**Cancellation**: frontend sends `{"type": "cancel"}` over WebSocket → API sets `token.cancel()` → pipeline checks token between phases → returns `ScanResult(cancelled=True)`.

### Debate Flow (Single Ticker)

```
[Frontend]                    [API]                         [Engine]
    │                           │                              │
    ├─POST /api/debate ────────►│                              │
    │  {ticker:"AAPL",          │                              │
    │   scan_id:42}             ├─fetch quote, ticker_info     │
    │                           ├─fetch contracts from scan    │
    │◄─202 {debate_id: 7} ─────┤                              │
    │                           ├─asyncio.create_task(         │
    ├─WS /ws/debate/7 ─────────►│  run_debate(                │
    │                           │    ..., callback))  ─────────►│
    │◄─{agent:"bull",           │◄─callback(BULL,"started") ──┤
    │   status:"started"}       │                              ├─Bull agent (30s)
    │◄─{agent:"bull",           │◄─callback(BULL,"done") ─────┤
    │   status:"completed",     │                              ├─Bear agent (30s)
    │   confidence:0.72}        │                              │
    │◄─{agent:"bear",...}       │  ...                         │
    │◄─{agent:"risk",...}       │                              ├─Risk agent
    │◄─{type:"complete",        │◄─DebateResult ──────────────┤
    │   debate_id:7}            │                              │
    │                           │                              │
    ├─GET /api/debate/7 ───────►│                              │
    │◄─DebateResult (full) ─────┤                              │
```

### Serialization Contract

| Python Type | JSON Representation | Frontend Type | Notes |
|-------------|--------------------:|---------------|-------|
| `Decimal` | `"123.45"` (string) | `string` | Existing `@field_serializer`. Frontend formats for display, never does math on prices. |
| `datetime` (UTC) | `"2026-02-26T14:30:45+00:00"` | `string` | ISO 8601. Frontend uses `Intl.DateTimeFormat` for display. |
| `StrEnum` | `"bullish"` | `string` literal union | Lowercase values. Frontend defines matching TS string unions. |
| `float` (Greeks, scores) | `0.4523` | `number` | Standard JSON number. |
| `int` (volume, OI) | `1500` | `number` | Standard JSON integer. |
| `X \| None` | `null` or absent | `T \| null` | Pydantic emits `null` for None fields. |
| `frozen=True` models | Normal JSON object | interface | Frozen only affects mutation, not serialization. Context7-verified. |

---

## API Contracts

### REST Endpoints

#### Scan

```
POST /api/scan
  Body: { "preset": "sp500" | "full" | "etfs" }
  202: { "scan_id": int }
  409: { "detail": "Another operation is in progress" }

GET /api/scan
  Query: ?limit=10
  200: [ ScanRun, ... ]    (newest first)

GET /api/scan/{scan_id}
  200: ScanRun
  404: { "detail": "Scan not found" }

GET /api/scan/{scan_id}/scores
  Query: ?sort=composite_score&order=desc&direction=bullish&min_score=0.5
         &search=AAPL&page=1&page_size=50
  200: { "items": [TickerScore, ...], "total": int, "page": int, "pages": int }
  404: { "detail": "Scan not found" }

GET /api/scan/{scan_id}/scores/{ticker}
  200: { "score": TickerScore, "contracts": [OptionContract, ...] }
  404: { "detail": "Ticker not found in scan" }

DELETE /api/scan/current
  200: { "cancelled": true }
  404: { "detail": "No scan in progress" }
```

#### Debate

```
POST /api/debate
  Body: { "ticker": "AAPL", "scan_id": int | null }
  202: { "debate_id": int }
  409: (if batch debate running)

POST /api/debate/batch
  Body: { "scan_id": int, "limit": 5 }
  202: { "batch_id": int, "tickers": ["AAPL", "MSFT", ...] }
  409: { "detail": "Another operation is in progress" }

GET /api/debate/{debate_id}
  200: DebateResult    (full result with all agent responses)
  404: { "detail": "Debate not found" }

GET /api/debate
  Query: ?ticker=AAPL&limit=20
  200: [ DebateResultSummary, ... ]    (ticker, date, verdict, confidence)

GET /api/debate/{debate_id}/export
  Query: ?format=md|pdf
  200: file download (Content-Disposition: attachment)
  404 / 501: (not found / weasyprint unavailable for PDF)
```

#### Supporting

```
GET /api/health
  200: [ HealthStatus, ... ]

GET /api/universe
  200: { "optionable_count": int, "sp500_count": int,
         "last_refresh": datetime | null }

POST /api/universe/refresh
  200: { "optionable_count": int, "sp500_count": int }

GET /api/config
  200: { "groq_api_key_set": bool, "scan_preset_default": str,
         "enable_rebuttal": bool, "enable_volatility_agent": bool,
         "agent_timeout": int }
```

### WebSocket Events

**Connection**: `ws://127.0.0.1:8000/ws/scan/{scan_id}` or `ws://127.0.0.1:8000/ws/debate/{debate_id}`

**Server → Client (scan):**
```json
{ "type": "progress", "phase": "universe|scoring|options|persist",
  "current": 150, "total": 5286 }
{ "type": "error", "ticker": "BADTK", "message": "No OHLCV data" }
{ "type": "complete", "scan_id": 42, "cancelled": false }
```

**Server → Client (debate):**
```json
{ "type": "agent", "name": "bull|bear|rebuttal|volatility|risk",
  "status": "started|completed|failed", "confidence": 0.72 }
{ "type": "complete", "debate_id": 7 }
```

**Client → Server (both):**
```json
{ "type": "cancel" }
```

### WebSocket Implementation Pattern

The scan pipeline already has `ProgressCallback`. For WebSocket streaming, create a callback that pushes to an `asyncio.Queue`:

```python
class WebSocketProgressBridge:
    """Bridges ProgressCallback protocol to asyncio.Queue for WebSocket consumption."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        # ProgressCallback is sync — use put_nowait
        self.queue.put_nowait({
            "type": "progress", "phase": phase.value,
            "current": current, "total": total,
        })

# In WebSocket handler:
bridge = WebSocketProgressBridge()
task = asyncio.create_task(pipeline.run(preset, token, bridge))
while not task.done():
    try:
        event = await asyncio.wait_for(bridge.queue.get(), timeout=1.0)
        await websocket.send_json(event)
    except asyncio.TimeoutError:
        continue  # keep waiting
await websocket.send_json({"type": "complete", "scan_id": scan_id})
```

---

## Required Engine Changes (Pre-Requisites)

These changes to existing code must happen before API development begins:

| Change | Module | Effort | Description |
|--------|--------|--------|-------------|
| Add `ProgressCallback` to debate orchestrator | `agents/orchestrator.py` | ~50 lines | Add optional `progress: DebateProgressCallback \| None` parameter to `run_debate()`. Call on agent start/complete. Define `DebateProgressCallback` protocol and `DebatePhase(StrEnum)` with values: `BULL`, `BEAR`, `REBUTTAL`, `VOLATILITY`, `RISK`. No changes to debate logic. |
| Convert `DebateResult` from dataclass to Pydantic model | `agents/_parsing.py` | ~30 lines | Change `@dataclass` to `BaseModel` with `ConfigDict(frozen=True)`. Required for FastAPI auto-serialization. All inner fields are already Pydantic models. `RunUsage` from pydantic_ai is already a Pydantic model. |
| Add `get_debate_by_id()` to Repository | `data/repository.py` | ~20 lines | Currently only `save_debate_result()` and `get_debate_history()` exist. Need single-debate fetch by ID for `/api/debate/{id}`. |

**These are additive changes with no breaking impact on CLI or existing tests.**

---

## `options-arena serve` Command

New Typer command added to `cli/`:

```python
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port number"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't auto-open browser"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev mode)"),
) -> None:
    """Start the web UI server."""
    import uvicorn
    import webbrowser
    if not no_open:
        webbrowser.open(f"http://{host}:{port}")
    uvicorn.run("options_arena.api:app", host=host, port=port, reload=reload)
```

- Production: `options-arena serve` → serves built Vue SPA from `web/dist/` via StaticFiles
- Dev: `options-arena serve --reload` (backend only) + `cd web && npm run dev` (frontend HMR)
- Auto-opens browser unless `--no-open` flag is passed
- Uses `webbrowser.open()` (stdlib) — cross-platform

---

## Implementation Order (Vertical Slices)

Build feature-by-feature, not layer-by-layer. Each slice delivers a working end-to-end feature:

| Slice | Scope | Delivers |
|-------|-------|----------|
| **0. Engine pre-requisites** | `DebateResult` → Pydantic model, debate progress callback, `get_debate_by_id()` | Foundation for API work |
| **1. Project scaffold** | FastAPI app factory + lifespan + deps + CORS + Vue scaffold + PrimeVue setup + `serve` command | Both servers start and serve a hello-world page |
| **2. Scan end-to-end** | `POST /api/scan` + `GET /api/scan` + `GET /api/scan/{id}/scores` + WebSocket progress + ScanPage + ScanResultsPage with PrimeVue DataTable + URL state | User can run scan, watch progress, browse results |
| **3. Ticker detail** | `GET /api/scan/{id}/scores/{ticker}` + Drawer component | User can click a row and see indicator + contract detail |
| **4. Single debate** | `POST /api/debate` + `GET /api/debate/{id}` + WebSocket progress + debate modal on scan page + DebateResultPage with AgentCards | User can debate a ticker and view results |
| **5. Batch debate** | `POST /api/debate/batch` + batch progress modal + summary table | User can debate top N tickers |
| **6. Supporting pages** | Dashboard, Universe, Health, Export, Config endpoint | Full feature set |

Each slice includes: API route + tests + Vue page + integration.

---

## Non-Functional Requirements

### Performance
- API response < 200ms for data retrieval (scan results, debate history)
- WebSocket event latency < 500ms from engine callback to browser
- Frontend initial load < 3s on localhost
- DataTable handles 5,000 rows (virtual scrolling via `@tanstack/vue-virtual` if needed)

### Security
- Bind `127.0.0.1` only (not `0.0.0.0`) — enforced in uvicorn config
- CORS: `allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]` (dev), no CORS needed in production (same-origin static serving)
- Groq API key never in API responses — only `groq_api_key_set: bool`
- No auth needed (localhost personal tool)

### Reliability
- Backend reuses existing fallback patterns (data-driven debate on LLM failure)
- WebSocket auto-reconnect: frontend `useWebSocket` composable with exponential backoff
- Browser close during scan: scan completes and persists (results not lost)
- SQLite WAL mode handles concurrent read (API) + write (scan persist) safely
- **CLI/Web coexistence**: both can run simultaneously against the same database. CLI writes (scan, debate) are visible to the web UI on next query. No locking conflicts in WAL mode.

### Developer Experience
- **Production**: `options-arena serve` — single command starts FastAPI, serves built Vue SPA, auto-opens `http://127.0.0.1:8000` in default browser
- **Dev mode**: `uv run uvicorn options_arena.api:app --reload` (backend) + `cd web && npm run dev` (frontend with Vite HMR on port 5173)
- OpenAPI docs at `http://127.0.0.1:8000/docs` (FastAPI auto-generated)
- Typed API client: generate from OpenAPI spec via `openapi-typescript` → TypeScript interfaces

---

## Dependencies

### New Python Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | REST API + WebSocket framework |
| `uvicorn[standard]` | ASGI server (with uvloop + httptools for performance) |

No other Python dependencies needed. FastAPI's WebSocket support is built-in. Pydantic is already installed.

### New npm Dependencies (web/)

| Package | Purpose |
|---------|---------|
| `vue` | UI framework |
| `vue-router` | Client-side routing |
| `pinia` | State management |
| `primevue` | Component library (DataTable, Drawer, Dialog, Toast, Button, Tag, etc.) |
| `@primeuix/themes` | PrimeVue theming (Aura dark preset) |
| `primeicons` | Icon set for PrimeVue components |
| `typescript` | Type safety |
| `vite` | Build tool + dev server |
| `@vitejs/plugin-vue` | Vite Vue integration |
| `openapi-typescript` | Generate TS types from OpenAPI schema (dev dependency) |

### External Services (Unchanged)

All external services remain the same. The API layer adds no new external dependencies.

---

## Out of Scope (v1)

- **User authentication** — localhost personal tool
- **Cloud deployment / Docker** — can be added later without architecture changes
- **Charts and visualizations** — v1 is data tables; charts (candlestick, payoff diagrams) deferred to v2
- **LLM token streaming** — debate shows results per-agent, not per-token
- **Mobile layout** — desktop-first, responsive but not mobile-native
- **Settings UI** — config stays in `.env`; read-only `/api/config` endpoint only
- **Custom scan configs via UI** — preset-based only; custom configs via `.env`
- **Real-time market data streaming** — fetch-on-demand, same as CLI

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Core workflow (scan → browse → debate → view result) works end-to-end | Yes |
| API endpoint test coverage | >= 90% |
| Existing test suite unbroken | 1,483 tests green |
| Frontend loads in < 3s on localhost | Yes |
| Scan progress visible within 500ms of engine event | Yes |
| Zero business logic in `api/` module | Verified by code review |
| Engine changes (3 pre-requisites) have full test coverage | Yes |

---

## Resolved Questions

| # | Question | Resolution |
|---|----------|------------|
| 1 | UI component library? | **PrimeVue** — DataTable, Drawer, Dialog, Toast, all primitives. Eliminates custom table implementation. |
| 2 | CLI/Web coexistence? | **Both can run simultaneously.** SQLite WAL mode supports concurrent readers. CLI-generated data visible to web on next query. |
| 3 | Launch command? | **`options-arena serve`** — single command for production. Auto-opens browser at `http://127.0.0.1:8000`. Separate processes for dev mode. |
| 4 | Error notifications? | **PrimeVue Toast** — slide-in notifications (top-right), auto-dismiss 5s. |
| 5 | URL filter state? | **Yes** — sort, filter, page synced to URL query params. Browser back/forward preserves state. Bookmarkable. |
| 6 | Debate during scan results? | **Stays on scan page.** Debate progress in a PrimeVue Dialog modal. Auto-redirect to result page on completion. |
| 7 | Batch debate UX? | **Progress modal** on scan results page. Current ticker, overall progress (3/5), mini-results as each completes. |
| 8 | Build order? | **Vertical slice** — scan end-to-end first (API + page + WebSocket), then debate end-to-end. Feature-by-feature. |
| 9 | Ticker detail? | **PrimeVue Drawer** — right-side slide-out. Indicators, contracts, past debates. |
| 10 | Browser auto-open? | **Yes** — `options-arena serve` opens browser automatically. |
| 11 | Regulatory disclaimer? | **Not included** in web UI. User opted out. |

## Open Questions

| # | Question | Impact | Default if Unresolved |
|---|----------|--------|----------------------|
| 1 | Should the OpenAPI TypeScript client be auto-generated on each build, or manually maintained? | DX quality, type drift risk | Auto-generate via `openapi-typescript` in npm build script |
| 2 | Should batch debate acquire the operation lock (blocking scans) or run independently? | UX during long batch runs | Acquire lock (batch debates are long-running, same as scans) |
| 3 | Should we add a `web` optional dependency group to pyproject.toml (`pip install options-arena[web]`)? | Installation ergonomics | Yes — keeps `fastapi` + `uvicorn` optional for CLI-only users |
| 4 | PrimeVue theme: use Aura dark preset as-is, or customize a financial-themed dark palette? | Visual polish vs effort | Aura dark preset + CSS variable overrides for accent colors (green/red/blue) |
