"""FastAPI application factory with lifespan, CORS, and static file serving.

``create_app()`` is the single entry-point for both production (``uvicorn``)
and test (``TestClient`` / ``AsyncClient``) usage.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from options_arena.data import Database, Repository
from options_arena.models.config import AppSettings
from options_arena.services.cache import ServiceCache
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.fred import FredService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import MarketDataService
from options_arena.services.openbb_service import OpenBBService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.outcome_collector import OutcomeCollector
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

# Module-level limiter instance used by route decorators
limiter = Limiter(key_func=get_remote_address)

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

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)
    await db.connect()
    repo = Repository(db)

    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )

    market_data = MarketDataService(settings.service, cache, limiter)
    options_data = OptionsDataService(
        settings.service,
        settings.scan.filters.options,
        cache,
        limiter,
        openbb_config=settings.openbb,
    )
    fred = FredService(settings.service, settings.pricing, cache)
    universe = UniverseService(settings.service, cache, limiter)

    # OpenBB enrichment service — created only when enabled in config
    openbb_svc: OpenBBService | None = None
    if settings.openbb.enabled:
        openbb_svc = OpenBBService(settings.openbb, cache, limiter)

    # Intelligence service — created only when enabled in config
    intelligence_svc: IntelligenceService | None = None
    if settings.intelligence.enabled:
        intelligence_svc = IntelligenceService(settings.intelligence, cache, limiter)

    # Financial Datasets service — created only when enabled and API key set
    fd_svc: FinancialDatasetsService | None = None
    if settings.financial_datasets.enabled and settings.financial_datasets.api_key is not None:
        fd_svc = FinancialDatasetsService(
            config=settings.financial_datasets,
            cache=cache,
            limiter=limiter,
        )

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
    app.state.openbb = openbb_svc
    app.state.intelligence = intelligence_svc
    app.state.financial_datasets = fd_svc
    app.state.operation_lock = asyncio.Lock()

    # Outcome collector — used by analytics routes and optional scheduler
    outcome_collector = OutcomeCollector(
        config=settings.analytics,
        repository=repo,
        market_data=market_data,
        options_data=options_data,
    )
    app.state.outcome_collector = outcome_collector

    # Auto-scheduled outcome collection — runs daily at configured UTC hour
    scheduler_task: asyncio.Task[None] | None = None
    if settings.analytics.auto_collect_enabled:
        scheduler_task = asyncio.create_task(outcome_collector.run_scheduler())
        logger.info("Outcome auto-collection scheduler enabled")

    # Initialize counters and mutable state eagerly so route handlers
    # never need lazy ``hasattr`` / ``getattr`` fallbacks.
    app.state.scan_counter = 0
    app.state.active_scans = {}
    app.state.scan_queues = {}
    app.state.debate_counter = 0
    app.state.debate_queues = {}
    app.state.batch_counter = 0
    app.state.batch_queues = {}
    app.state.index_counter = 0

    logger.info("API services started")
    yield

    # Shutdown — cancel scheduler first, then close all services
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task

    if fd_svc is not None:
        await fd_svc.close()
    if intelligence_svc is not None:
        await intelligence_svc.close()
    if openbb_svc is not None:
        await openbb_svc.close()
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

    # Rate limiter — stored on app.state for route decorator access
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        # RateLimitExceeded has no retry_after attr; exc.detail holds the limit string
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {exc.detail}"},
            headers={"Retry-After": "60"},
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
    from options_arena.api.routes.analytics import router as analytics_router  # noqa: PLC0415
    from options_arena.api.routes.backtest import router as backtest_router  # noqa: PLC0415
    from options_arena.api.routes.config import router as config_router  # noqa: PLC0415
    from options_arena.api.routes.debate import router as debate_router  # noqa: PLC0415
    from options_arena.api.routes.export import router as export_router  # noqa: PLC0415
    from options_arena.api.routes.health import router as health_router  # noqa: PLC0415
    from options_arena.api.routes.market import router as market_router  # noqa: PLC0415
    from options_arena.api.routes.scan import router as scan_router  # noqa: PLC0415
    from options_arena.api.routes.ticker import router as ticker_router  # noqa: PLC0415
    from options_arena.api.routes.universe import router as universe_router  # noqa: PLC0415
    from options_arena.api.ws import router as ws_router  # noqa: PLC0415

    app.include_router(health_router)
    app.include_router(market_router)
    app.include_router(scan_router)
    app.include_router(debate_router)
    app.include_router(export_router)
    app.include_router(universe_router)
    app.include_router(config_router)
    app.include_router(ticker_router)
    app.include_router(analytics_router)
    app.include_router(backtest_router)
    app.include_router(ws_router)

    # Exception handlers for domain errors
    _register_exception_handlers(app)

    # Serve Vue SPA from web/dist/ (mount AFTER API routes)
    # NOTE: StaticFiles(html=True) only resolves index.html for directory paths,
    # not for arbitrary SPA routes like /scan or /debate/123.  Use an explicit
    # catch-all GET route so Vue Router history mode works for all client paths.
    if _WEB_DIST.exists():
        from fastapi.responses import FileResponse  # noqa: PLC0415

        _assets_dir = _WEB_DIST / "assets"
        if _assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

        _index_html = _WEB_DIST / "index.html"
        _resolved_dist = _WEB_DIST.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def spa_fallback(path: str) -> FileResponse:
            """Serve static files if they exist, otherwise index.html for SPA routing."""
            if path:
                file_path = (_WEB_DIST / path).resolve()
                if file_path.is_file() and file_path.is_relative_to(_resolved_dist):
                    return FileResponse(file_path)
            return FileResponse(_index_html)

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
