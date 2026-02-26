"""FastAPI application factory with lifespan, CORS, and static file serving.

``create_app()`` is the single entry-point for both production (``uvicorn``)
and test (``TestClient`` / ``AsyncClient``) usage.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from options_arena.data import Database, Repository
from options_arena.models.config import AppSettings
from options_arena.services.cache import ServiceCache
from options_arena.services.fred import FredService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

logger = logging.getLogger(__name__)

# Resolve paths relative to project root
# src/options_arena/api/app.py → parents[3] → project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _PROJECT_ROOT / "data"
_WEB_DIST = _PROJECT_ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Create all services at startup, close them at shutdown."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = Database(_DATA_DIR / "options_arena.db")
    await db.connect()
    repo = Repository(db)

    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )

    market_data = MarketDataService(settings.service, cache, limiter)
    options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter)
    fred = FredService(settings.service, settings.pricing, cache)
    universe = UniverseService(settings.service, cache, limiter)

    # Store on app.state for Depends() access
    app.state.settings = settings
    app.state.db = db
    app.state.repo = repo
    app.state.cache = cache
    app.state.limiter = limiter
    app.state.market_data = market_data
    app.state.options_data = options_data
    app.state.fred = fred
    app.state.universe = universe
    app.state.operation_lock = asyncio.Lock()

    logger.info("API services started")
    yield

    # Shutdown — close all services
    await market_data.close()
    await options_data.close()
    await fred.close()
    await universe.close()
    await cache.close()
    await db.close()
    logger.info("API services stopped")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Options Arena",
        description="AI-powered American-style options analysis API",
        version="1.5.0",
        lifespan=lifespan,
    )

    # CORS — allow Vite dev server
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

    # Register API routes
    from options_arena.api.routes.config import router as config_router  # noqa: PLC0415
    from options_arena.api.routes.debate import router as debate_router  # noqa: PLC0415
    from options_arena.api.routes.export import router as export_router  # noqa: PLC0415
    from options_arena.api.routes.health import router as health_router  # noqa: PLC0415
    from options_arena.api.routes.scan import router as scan_router  # noqa: PLC0415
    from options_arena.api.routes.universe import router as universe_router  # noqa: PLC0415
    from options_arena.api.ws import router as ws_router  # noqa: PLC0415

    app.include_router(health_router)
    app.include_router(scan_router)
    app.include_router(debate_router)
    app.include_router(export_router)
    app.include_router(universe_router)
    app.include_router(config_router)
    app.include_router(ws_router)

    # Exception handlers for domain errors
    _register_exception_handlers(app)

    # Serve Vue SPA from web/dist/ (mount AFTER API routes)
    if _WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="spa")

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Map domain exceptions to HTTP status codes."""
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    from options_arena.utils import (  # noqa: PLC0415
        DataSourceUnavailableError,
        InsufficientDataError,
        RateLimitExceededError,
        TickerNotFoundError,
    )

    @app.exception_handler(TickerNotFoundError)
    async def _ticker_not_found(request: object, exc: TickerNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InsufficientDataError)
    async def _insufficient_data(request: object, exc: InsufficientDataError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(DataSourceUnavailableError)
    async def _data_source_unavailable(
        request: object, exc: DataSourceUnavailableError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(RateLimitExceededError)
    async def _rate_limit_exceeded(request: object, exc: RateLimitExceededError) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
