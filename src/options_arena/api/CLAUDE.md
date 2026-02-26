# CLAUDE.md -- API Module (`api/`)

## Purpose

The **FastAPI backend** that exposes the Options Arena engine as a REST + WebSocket API.
Like `cli/`, this is a top-of-stack entry point — it wires services together, handles HTTP
concerns, and delegates all business logic to existing modules. The `api/` package contains
zero business logic, zero pricing math, zero indicator computation.

The `api/` module is the bridge between the Vue 3 SPA (`web/`) and the Python engine.
It translates HTTP requests into service/pipeline/orchestrator calls and streams progress
events via WebSocket.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `app` and `create_app()` |
| `app.py` | App factory: `create_app()`, `lifespan()`, CORS, static mount, router includes |
| `deps.py` | `Depends()` providers: `get_repo()`, `get_market_data()`, `get_operation_lock()`, etc. |
| `schemas.py` | API-only request/response wrappers not covered by existing models |
| `ws.py` | WebSocket handlers: `/ws/scan/{id}`, `/ws/debate/{id}` |
| `routes/scan.py` | Scan endpoints: start, list, results, cancel |
| `routes/debate.py` | Debate endpoints: start (single + batch), get result, list, export |
| `routes/universe.py` | Universe endpoints: stats, refresh |
| `routes/health.py` | Health check endpoint |
| `routes/config.py` | Read-only config endpoint |
| `routes/export.py` | Debate export endpoint (Markdown/PDF download) |

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Thin wrapper** | Routes call existing services/orchestrator directly. No new business logic. |
| **Pydantic models as responses** | Return existing models from `models/`. FastAPI auto-serializes. No manual `model_dump()`. |
| **App-scoped services** | Services created in `lifespan()`, stored on `app.state`, injected via `Depends()`. Never per-request. |
| **Operation mutex** | One long-running op (scan/batch debate) at a time via `asyncio.Lock`. Return 409 if busy. |
| **Background tasks** | Scans and batch debates run in `asyncio.create_task()`. WebSocket streams progress. |
| **No `print()`** | Use `logging.getLogger(__name__)`. Same rule as all library modules. |
| **Error → HTTP** | Catch domain exceptions → appropriate HTTP status codes. See Error Mapping table. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all models, enums, config) | Nothing imports from `api/` |
| `services/` (all service classes) | `cli/` (these are sibling entry points) |
| `data/` (Database, Repository) | |
| `scan/` (ScanPipeline, ScanPhase, CancellationToken, ProgressCallback, ScanResult) | |
| `agents/` (run_debate, DebateResult, build_market_context) | |
| `reporting/` (debate_export) | |
| stdlib: `asyncio`, `logging`, `pathlib` | |
| External: `fastapi`, `uvicorn` | |

`api/` is a dependency root (like `cli/`). Nothing imports from it.

---

## Service Lifecycle (Lifespan)

Services live for the lifetime of the application, not per-request:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # --- Startup ---
    settings = AppSettings()
    db = Database(DATA_DIR / "options_arena.db")
    await db.connect()
    repo = Repository(db)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(settings.service.rate_limit_rps, settings.service.max_concurrent_requests)

    app.state.settings = settings
    app.state.repo = repo
    app.state.db = db
    app.state.cache = cache
    app.state.limiter = limiter
    app.state.market_data = MarketDataService(settings.service, cache, limiter)
    app.state.options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter)
    app.state.fred = FredService(settings.service, settings.pricing, cache)
    app.state.universe = UniverseService(settings.service, cache, limiter)
    app.state.operation_lock = asyncio.Lock()
    app.state.active_scans: dict[int, CancellationToken] = {}
    app.state.scan_queues: dict[int, asyncio.Queue] = {}
    app.state.debate_queues: dict[int, asyncio.Queue] = {}

    yield

    # --- Shutdown ---
    await app.state.market_data.close()
    await app.state.options_data.close()
    await app.state.fred.close()
    await app.state.universe.close()
    await db.close()
```

**Critical difference from CLI**: CLI creates/destroys services per command. API keeps them
alive. Cache and rate limiter state accumulates across requests (which is desirable — cache
hits improve performance, rate limiter prevents abuse).

---

## Dependency Injection Pattern

```python
# deps.py
from fastapi import Depends, Request

def get_repo(request: Request) -> Repository:
    return request.app.state.repo

def get_market_data(request: Request) -> MarketDataService:
    return request.app.state.market_data

def get_options_data(request: Request) -> OptionsDataService:
    return request.app.state.options_data

def get_fred(request: Request) -> FredService:
    return request.app.state.fred

def get_universe(request: Request) -> UniverseService:
    return request.app.state.universe

def get_settings(request: Request) -> AppSettings:
    return request.app.state.settings

def get_operation_lock(request: Request) -> asyncio.Lock:
    return request.app.state.operation_lock
```

Usage in routes:

```python
@router.get("/api/scan/{scan_id}/scores")
async def get_scores(
    scan_id: int,
    repo: Repository = Depends(get_repo),
) -> list[TickerScore]:
    scores = await repo.get_scores_for_scan(scan_id)
    if not scores:
        raise HTTPException(404, "Scan not found")
    return scores
```

FastAPI auto-serializes `list[TickerScore]` to JSON via Pydantic.

---

## Error Mapping

| Domain Exception | HTTP Status | Response |
|-----------------|-------------|----------|
| `TickerNotFoundError` | 404 | `{"detail": "Ticker not found: BADTK"}` |
| `InsufficientDataError` | 422 | `{"detail": "Insufficient data for AAPL"}` |
| `DataSourceUnavailableError` | 503 | `{"detail": "Yahoo Finance unavailable"}` |
| `RateLimitExceededError` | 429 | `{"detail": "Rate limit exceeded"}` |
| Operation lock held | 409 | `{"detail": "Another operation is in progress"}` |
| Scan not found in DB | 404 | `{"detail": "Scan not found"}` |
| Debate not found in DB | 404 | `{"detail": "Debate not found"}` |
| WeasyPrint not installed | 501 | `{"detail": "PDF export requires weasyprint"}` |

Register exception handlers in `app.py`:

```python
from options_arena.utils import (
    TickerNotFoundError, InsufficientDataError,
    DataSourceUnavailableError, RateLimitExceededError,
)

@app.exception_handler(TickerNotFoundError)
async def ticker_not_found(request: Request, exc: TickerNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

---

## WebSocket Progress Bridge

The scan pipeline has a sync `ProgressCallback` protocol. WebSocket is async. Bridge via
`asyncio.Queue`:

```python
# ws.py
class WebSocketProgressBridge:
    """Bridges sync ProgressCallback → asyncio.Queue for WebSocket consumption."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        # ProgressCallback is sync — put_nowait is safe from sync context
        self.queue.put_nowait({
            "type": "progress",
            "phase": phase.value,
            "current": current,
            "total": total,
        })

    def complete(self, scan_id: int, cancelled: bool) -> None:
        self.queue.put_nowait({
            "type": "complete",
            "scan_id": scan_id,
            "cancelled": cancelled,
        })
```

WebSocket handler reads from queue and forwards to client:

```python
@app.websocket("/ws/scan/{scan_id}")
async def ws_scan(websocket: WebSocket, scan_id: int) -> None:
    await websocket.accept()
    queue = websocket.app.state.scan_queues.get(scan_id)
    if queue is None:
        await websocket.close(code=4004)
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "complete":
                    break
            except asyncio.TimeoutError:
                continue  # keep waiting, check for disconnect
            except WebSocketDisconnect:
                break
    finally:
        await websocket.close()
```

**Cancellation via WebSocket**: client sends `{"type": "cancel"}`. Handler sets the
`CancellationToken` stored in `app.state.active_scans[scan_id]`.

---

## Scan Start Pattern

```python
# routes/scan.py
@router.post("/api/scan", status_code=202)
async def start_scan(
    request: ScanStartRequest,
    lock: asyncio.Lock = Depends(get_operation_lock),
    settings: AppSettings = Depends(get_settings),
    # ... all services via Depends
) -> ScanStarted:
    if lock.locked():
        raise HTTPException(409, "Another operation is in progress")

    async with lock:
        token = CancellationToken()
        bridge = WebSocketProgressBridge()

        # Pre-create scan_run for ID
        scan_run = ScanRun(preset=request.preset, started_at=datetime.now(UTC))
        scan_id = await repo.save_scan_run(scan_run)

        # Register for WebSocket consumption
        request.app.state.active_scans[scan_id] = token
        request.app.state.scan_queues[scan_id] = bridge.queue

        # Start pipeline in background
        asyncio.create_task(_run_scan(scan_id, request.preset, token, bridge, ...))

        return ScanStarted(scan_id=scan_id)
```

**Key: `async with lock` holds the lock for the entire scan duration.** The background task
runs inside the lock context. Other requests to start a scan will see `lock.locked()` and
get 409.

---

## API-Only Schemas

Most responses use existing Pydantic models directly. A few thin wrappers are needed:

```python
# schemas.py
from pydantic import BaseModel

class ScanStartRequest(BaseModel):
    preset: ScanPreset = ScanPreset.SP500

class ScanStarted(BaseModel):
    scan_id: int

class DebateStartRequest(BaseModel):
    ticker: str
    scan_id: int | None = None

class DebateStarted(BaseModel):
    debate_id: int

class BatchDebateRequest(BaseModel):
    scan_id: int
    limit: int = 5

class BatchDebateStarted(BaseModel):
    batch_id: int
    tickers: list[str]

class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    pages: int

class ConfigResponse(BaseModel):
    groq_api_key_set: bool
    scan_preset_default: str
    enable_rebuttal: bool
    enable_volatility_agent: bool
    agent_timeout: int

class UniverseStats(BaseModel):
    optionable_count: int
    sp500_count: int
    last_refresh: datetime | None
```

---

## CORS Configuration

```python
# app.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Dev only**: In production, the Vue SPA is served from FastAPI's `StaticFiles` on the same
origin — no CORS needed. The CORS middleware is harmless in production (no cross-origin
requests to match).

---

## Static File Serving (Production)

```python
# app.py — mount AFTER API routes so /api/* takes precedence
from fastapi.staticfiles import StaticFiles
from pathlib import Path

WEB_DIST = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"

if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")
```

`html=True` makes StaticFiles serve `index.html` for any path not matching a static file,
enabling Vue Router's history mode.

---

## Testing Patterns

### Framework

- `pytest` + `httpx` (`AsyncClient`) for API endpoint tests
- FastAPI's `TestClient` (sync) for simple route tests
- Mock services via dependency override: `app.dependency_overrides[get_repo] = lambda: mock_repo`

### Test Structure

```
tests/unit/api/
    test_scan_routes.py
    test_debate_routes.py
    test_universe_routes.py
    test_health_routes.py
    test_ws_scan.py
    test_ws_debate.py
    test_deps.py
    test_schemas.py
    conftest.py              # Shared fixtures: test app, mock services, mock repo
```

### Endpoint Test Pattern

```python
import pytest
from httpx import ASGITransport, AsyncClient
from options_arena.api.app import create_app
from options_arena.api.deps import get_repo

@pytest.fixture
def app():
    app = create_app()
    app.dependency_overrides[get_repo] = lambda: mock_repo
    return app

@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac

@pytest.mark.asyncio
async def test_list_scans(client: AsyncClient, mock_repo) -> None:
    mock_repo.get_recent_scans.return_value = [make_scan_run()]
    response = await client.get("/api/scan?limit=5")
    assert response.status_code == 200
    assert len(response.json()) == 1
```

### What to Test

- Route → correct service method called with correct args
- Error paths: 404, 409, 422, 503
- Pagination math (page, pages, total)
- WebSocket event sequence (connect → events → complete → close)
- Schema validation (request bodies, response shapes)

### What NOT to Test

- Business logic (tested in service/pipeline/orchestrator tests)
- Pydantic model serialization (tested in model tests)
- FastAPI framework internals (JSON encoding, OpenAPI generation)

---

## What Claude Gets Wrong -- API-Specific (Fix These)

1. **Creating services per request** — Services are app-scoped, created in `lifespan()`. Never
   instantiate `MarketDataService()` inside a route handler. Use `Depends()`.

2. **Manual `model_dump_json()`** — FastAPI auto-serializes Pydantic models. Just return the
   model from the route: `return score`. Don't call `score.model_dump()` or `score.model_dump_json()`.

3. **Blocking the event loop** — Never call sync `yfinance` functions directly in a route.
   All external calls go through existing async services (which use `asyncio.to_thread` internally).

4. **Forgetting `async with lock`** — The operation lock must be held for the entire duration of
   a scan/batch, not just at the start. `asyncio.create_task()` must run inside the lock context.

5. **`app.state` typing** — FastAPI's `app.state` is untyped. Use the `Depends()` functions in
   `deps.py` to add type information at the injection site.

6. **Returning raw dicts** — Same rule as the rest of the project: never return `dict[str, Any]`.
   Use existing Pydantic models or define a schema in `schemas.py`.

7. **`Exception` handlers catching too broadly** — Register handlers for specific domain exceptions
   only. Never `@app.exception_handler(Exception)` — let FastAPI's default 500 handler work.

8. **Forgetting to clean up WebSocket queues** — When a scan completes or a WebSocket disconnects,
   remove the queue from `app.state.scan_queues`. Leaked queues accumulate memory.

9. **Sync `ProgressCallback` in async context** — `ProgressCallback.__call__` is sync. Use
   `queue.put_nowait()`, never `await queue.put()`. The callback runs in the pipeline's thread
   context (via `asyncio.to_thread` in services).

10. **Binding to `0.0.0.0`** — Always bind to `127.0.0.1`. The default `uvicorn.run()` example
    shows `0.0.0.0` but this tool is localhost-only. Exposing to the network is a security issue.
