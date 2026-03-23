# CLAUDE.md -- API Module (`api/`)

## Purpose

The **FastAPI backend** that exposes the Options Arena engine as a REST + WebSocket API.
Like `cli/`, this is a top-of-stack entry point -- wires services together, handles HTTP
concerns, and delegates all business logic to existing modules. The `api/` package contains
zero business logic, zero pricing math, zero indicator computation.

The `api/` module bridges the Vue 3 SPA (`web/`) and the Python engine. It translates
HTTP requests into service/pipeline/orchestrator calls and streams progress via WebSocket.

Use Glob to discover files in `routes/`.

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Thin wrapper** | Routes call existing services/orchestrator directly. No new business logic. |
| **Pydantic responses** | Return existing models from `models/`. FastAPI auto-serializes. No manual `model_dump()`. |
| **App-scoped services** | Services created in `lifespan()`, stored on `app.state`, injected via `Depends()`. Never per-request. |
| **Operation mutex** | One long-running op (scan/batch) at a time via `asyncio.Lock`. Return 409 if busy. |
| **Background tasks** | Scans and batch debates run in `asyncio.create_task()`. Counter-based IDs. |
| **No `print()`** | Use `logging.getLogger(__name__)`. Same rule as all library modules. |
| **Error -> HTTP** | Catch domain exceptions -> appropriate HTTP status codes. |

### Import Rules

`api/` is a dependency root (like `cli/`). Nothing imports from it.

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all models, enums, config) | `cli/` (sibling entry point) |
| `services/` (all service classes) | |
| `data/` (Database, Repository) | |
| `scan/` (ScanPipeline, ScanPhase, CancellationToken) | |
| `agents/` (run_recommendation, DebateResult) | |
| `reporting/` (debate_export) | |
| `learning/` (tuning, mining, playbook) | |
| stdlib: `asyncio`, `logging`, `pathlib` | |
| External: `fastapi`, `uvicorn` | |

---

## Routes Overview

| Route File | Endpoints | Purpose |
|-----------|-----------|---------|
| `routes/scan.py` | `POST /api/scan`, `GET /api/scan`, `GET /api/scan/{id}/scores` | Start, list, results |
| `routes/debate.py` | `POST /api/debate`, `POST /api/debate/batch`, `GET /api/debate/{id}` | Single, batch, get result |
| `routes/universe.py` | `GET /api/universe/stats`, `POST /api/universe/refresh` | Universe management |
| `routes/health.py` | `GET /api/health` | Health check |
| `routes/config.py` | `GET /api/config`, `GET /api/config/routing` | Read-only config |
| `routes/export.py` | `POST /api/debate/{id}/export` | Markdown/PDF download |
| `routes/market.py` | `GET /api/market/heatmap` | S&P 500 heatmap |
| `routes/backtest.py` | `GET /api/analytics/backtest/*` (7 endpoints) | Backtesting analytics |
| `routes/analytics.py` | `GET /api/analytics/*` (9+ endpoints) | Win rate, calibration, costs |
| `routes/ticker.py` | `GET /api/ticker/*` | Score history, trending, info |

WebSocket: `WS /ws/scan/{id}`, `WS /ws/debate/{id}` -- real-time progress.
Agency: `POST /api/agency/ask`, `POST /api/agency/chat`.
Learning: `POST /api/learning/tune-*`, `GET /api/learning/status`, `POST /api/learning/mine`,
`GET /api/learning/playbook`.

---

## Service Lifecycle (Lifespan)

Services live for the lifetime of the application, not per-request. Created in `lifespan()`,
stored on `app.state`:

- `settings: AppSettings`
- `db: Database`, `repo: Repository`
- `cache: ServiceCache`, `limiter: RateLimiter`
- `market_data: MarketDataService`, `options_data: OptionsDataService`
- `fred: FredService`, `universe: UniverseService`
- `operation_lock: asyncio.Lock`
- `active_scans: dict[int, CancellationToken]`
- `scan_queues: dict[int, asyncio.Queue]`
- `debate_queues: dict[int, asyncio.Queue]`

**Critical difference from CLI**: CLI creates/destroys services per command. API keeps them
alive. Cache and rate limiter state accumulates across requests (desirable).

Shutdown: close all services and DB connection in the lifespan's exit.

---

## Dependency Injection

`deps.py` provides `Depends()` functions that read from `request.app.state`:
`get_repo()`, `get_market_data()`, `get_options_data()`, `get_fred()`, `get_universe()`,
`get_settings()`, `get_operation_lock()`.

FastAPI's `app.state` is untyped. The `Depends()` functions add type information at the
injection site.

---

## Error Mapping

| Domain Exception | HTTP Status | Response |
|-----------------|-------------|----------|
| `TickerNotFoundError` | 404 | `{"detail": "Ticker not found: BADTK"}` |
| `InsufficientDataError` | 422 | `{"detail": "Insufficient data for AAPL"}` |
| `DataSourceUnavailableError` | 503 | `{"detail": "Yahoo Finance unavailable"}` |
| `RateLimitExceededError` | 429 | `{"detail": "Rate limit exceeded"}` |
| Operation lock held | 409 | `{"detail": "Another operation is in progress"}` |
| Scan/Debate not found | 404 | `{"detail": "Scan not found"}` |
| WeasyPrint not installed | 501 | `{"detail": "PDF export requires weasyprint"}` |

Register exception handlers for specific domain exceptions only. Never
`@app.exception_handler(Exception)` -- let FastAPI's default 500 handler work.

---

## WebSocket Progress Bridge

The scan pipeline has a sync `ProgressCallback` protocol. WebSocket is async.
Bridge via `asyncio.Queue`:

- `WebSocketProgressBridge.__call__()` uses `queue.put_nowait()` (sync context, NOT `await`)
- `complete()` puts a `{"type": "complete"}` event
- WebSocket handler reads from queue in a loop with `asyncio.wait_for(queue.get(), timeout=1.0)`
- Timeout -> continue loop (check for disconnect)
- `{"type": "complete"}` -> break loop
- Client cancellation: sends `{"type": "cancel"}`, handler sets `CancellationToken`

**Critical**: Clean up queues on completion/disconnect. Remove from `app.state.scan_queues`.
Leaked queues accumulate memory.

---

## Operation Mutex (Scan Start Pattern)

1. Check `lock.locked()` -- if busy, return 409
2. `async with lock:` -- holds lock for ENTIRE scan/batch duration
3. Create `CancellationToken` and `WebSocketProgressBridge`
4. Register in `app.state` for WebSocket consumption
5. `asyncio.create_task(_run_scan(...))` runs INSIDE the lock context
6. Return 202 with scan ID

The background task runs inside the lock context. Other scan requests see `lock.locked()`
and get 409.

---

## CORS Configuration

Dev only (Vite dev server at :5173). Origins: `http://localhost:5173`, `http://127.0.0.1:5173`.
In production, Vue SPA served from same origin -- no CORS needed. Middleware is harmless.

---

## Static File Serving (Production)

- `/assets` mounted via `StaticFiles` for hashed static files from `web/dist/assets`
- Catch-all GET `/{path:path}` serves static files if they exist, else `index.html` for
  Vue Router history mode
- **Why not `StaticFiles(html=True)`**: only serves `index.html` for directory paths, NOT for
  SPA routes like `/scan` or `/debate/123`. The catch-all route handles this correctly.
- Path traversal safety: resolve path, check `is_relative_to(WEB_DIST)` before serving

---

## API-Only Schemas

Most responses use existing Pydantic models directly. Thin wrappers in `schemas.py`:
`ScanStartRequest`, `ScanStarted`, `DebateStartRequest`, `DebateStarted`,
`BatchDebateRequest`, `BatchDebateStarted`, `PaginatedResponse[T]`, `ConfigResponse`,
`UniverseStats`.

---

## Testing Guidance

- `pytest` + `httpx` (`AsyncClient` with `ASGITransport`) for endpoint tests
- Mock services via `app.dependency_overrides[get_repo] = lambda: mock_repo`
- Test: route -> correct service method called, error paths (404/409/422/503),
  pagination math, WebSocket event sequences, schema validation
- Do NOT test: business logic (tested elsewhere), Pydantic serialization, FastAPI internals

---

## What Claude Gets Wrong -- API-Specific (Fix These)

1. **Creating services per request** -- App-scoped in `lifespan()`. Use `Depends()`.

2. **Manual `model_dump_json()`** -- FastAPI auto-serializes Pydantic models. Just return.

3. **Blocking the event loop** -- Never call sync yfinance in routes. Use async services.

4. **Forgetting `async with lock`** -- Lock held for entire scan/batch, not just at start.

5. **`app.state` typing** -- Untyped. Use `Depends()` functions for type info.

6. **Returning raw dicts** -- Use existing models or define schema in `schemas.py`.

7. **`Exception` handlers too broad** -- Specific domain exceptions only.

8. **Forgetting WebSocket queue cleanup** -- Leaked queues accumulate memory.

9. **Sync `ProgressCallback` in async** -- `put_nowait()`, never `await queue.put()`.

10. **Binding to `0.0.0.0`** -- Always `127.0.0.1`. Localhost-only security.
