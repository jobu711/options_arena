---
name: intel-wave7-api-wiring
description: FastAPI routes, WebSocket alerts endpoint, app factory wiring, and dependency injection for intelligence layer
status: backlog
created: 2026-03-24T15:48:29Z
effort: M
---

# PRD: intel-wave7-api-wiring

## Executive Summary

Wire all intelligence infrastructure into the FastAPI application: new REST endpoints for snapshots/deltas/alerts, WebSocket endpoint for real-time alert streaming, service instantiation in the app lifespan, and dependency injection helpers. This makes the intelligence layer accessible to the Vue frontend and any API consumer.

## Problem Statement

### What problem are we solving?

The intelligence services (Waves 2-4) and desk agent (Wave 5) work at the service/agent layer but are not exposed via the API. The frontend can't display intelligence data, alerts, or delta reports without API endpoints. The services aren't instantiated at startup without lifespan wiring.

### Why is this important now?

Final wave that connects all backend intelligence work to the outside world. Required for frontend intelligence panel (future) and for the recommendation orchestrator to access intelligence services via app.state.

## Requirements

### Functional Requirements

#### FR-1: API Routes (`api/routes/intelligence.py`)

New router with prefix `/api/intelligence`:

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| `GET` | `/api/intelligence/snapshot` | `IntelligenceSnapshot \| null` | Latest intelligence snapshot |
| `GET` | `/api/intelligence/delta` | `DeltaReport \| null` | Latest delta report |
| `GET` | `/api/intelligence/alerts` | `list[AlertRecord]` | Alert history (query: tier, status, limit) |
| `POST` | `/api/intelligence/alerts/{id}/ack` | `204 No Content` | Acknowledge alert |

All endpoints return 503 if intelligence is disabled (`settings.intelligence.enabled = False`).

#### FR-2: WebSocket Alert Endpoint (`api/ws.py`)

New endpoint `WS /ws/alerts`:
- `AlertBridge` class (queue-based, same pattern as `WebSocketProgressBridge`)
- Origin check (loopback only, same as existing WS endpoints)
- Connection limit enforcement
- Drains alert queue in loop with `asyncio.wait_for(queue.get(), timeout=1.0)`
- Sends JSON alert events: `{"type": "alert", "tier": "...", "title": "...", ...}`
- Breaks on disconnect

Add `app.state.alert_queue: asyncio.Queue | None` for the alert bridge.

#### FR-3: App Factory Wiring (`api/app.py`)

In `lifespan()`, after existing service creation:

```python
if settings.intelligence.enabled:
    # Create individual data source services
    gdelt_svc = GdeltService(settings.gdelt, cache, limiter) if settings.gdelt.enabled else None
    eia_svc = EiaService(settings.eia, cache, limiter) if settings.eia.enabled and settings.eia.api_key else None
    bls_svc = BlsService(settings.bls, cache) if settings.bls.enabled else None
    gscpi_svc = GscpiService(settings.gscpi, cache) if settings.gscpi.enabled else None
    treasury_svc = TreasuryFiscalService(settings.treasury_fiscal, cache) if settings.treasury_fiscal.enabled else None

    # Create orchestrator
    intelligence_collector = IntelligenceCollector(
        gdelt=gdelt_svc, eia=eia_svc, bls=bls_svc,
        gscpi=gscpi_svc, treasury=treasury_svc,
        fred=fred, config=settings.intelligence,
    )
    delta_engine = DeltaEngine(settings.intelligence)
    alert_service = AlertService(settings.intelligence, repo) if settings.intelligence.enable_alerts else None

    app.state.intelligence_collector = intelligence_collector
    app.state.delta_engine = delta_engine
    app.state.alert_service = alert_service
    app.state.alert_queue = asyncio.Queue(maxsize=100) if alert_service else None
else:
    app.state.intelligence_collector = None
    app.state.delta_engine = None
    app.state.alert_service = None
    app.state.alert_queue = None
```

In shutdown: close intelligence_collector if not None.

#### FR-4: Dependency Injection (`api/deps.py`)

```python
def get_intelligence_collector(request: Request) -> IntelligenceCollector | None:
    return getattr(request.app.state, "intelligence_collector", None)

def get_delta_engine(request: Request) -> DeltaEngine | None:
    return getattr(request.app.state, "delta_engine", None)

def get_alert_service(request: Request) -> AlertService | None:
    return getattr(request.app.state, "alert_service", None)
```

#### FR-5: Router Registration

Add intelligence router to app in `api/app.py`:
```python
from options_arena.api.routes.intelligence import router as intelligence_router
app.include_router(intelligence_router)
```

### Non-Functional Requirements

- Zero impact when `intelligence.enabled = False` — no services created, endpoints return 503
- All new endpoints follow existing error mapping (404, 422, 503)
- WebSocket follows existing patterns (origin check, connection limit, queue drain)
- Services properly closed on shutdown

## Success Criteria

- `GET /api/intelligence/snapshot` returns valid JSON when intelligence enabled
- `GET /api/intelligence/delta` returns latest delta or null
- `GET /api/intelligence/alerts` returns alert list with filtering
- `POST /api/intelligence/alerts/{id}/ack` updates alert status
- `WS /ws/alerts` streams alert events
- All endpoints return 503 when intelligence disabled
- `uv run pytest tests/unit/api/ -q` passes

## Out of Scope

- Frontend Vue components (separate epic/PR)
- CLI integration (can be added later)
- Frontend intelligence panel design

## Dependencies

- **Wave 2** (intel-wave2-data-sources) — service classes
- **Wave 3** (intel-wave3-delta-engine) — collector, delta engine, repository
- **Wave 4** (intel-wave4-alert-system) — alert service, alert bridge

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/api/routes/intelligence.py` | **Create** — 4 endpoints |
| `src/options_arena/api/ws.py` | Modify — add AlertBridge + WS /ws/alerts |
| `src/options_arena/api/app.py` | Modify — lifespan wiring + router registration |
| `src/options_arena/api/deps.py` | Modify — add 3 dependency providers |
| `tests/unit/api/test_intelligence_routes.py` | **Create** |
