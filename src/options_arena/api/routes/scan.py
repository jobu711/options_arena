"""Scan endpoints — start, list, results, cancel."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
    get_universe,
)
from options_arena.api.schemas import PaginatedResponse, ScanRequest, ScanStarted, TickerDetail
from options_arena.api.ws import WebSocketProgressBridge
from options_arena.data import Repository
from options_arena.models import AppSettings, ScanPreset, ScanRun, SignalDirection, TickerScore
from options_arena.scan import CancellationToken, ScanPipeline, ScanResult
from options_arena.services import (
    FredService,
    MarketDataService,
    OptionsDataService,
    UniverseService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["scan"])


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_scan_background(
    request: Request,
    scan_id: int,
    preset: ScanPreset,
    token: CancellationToken,
    bridge: WebSocketProgressBridge,
    pipeline: ScanPipeline,
    repo: Repository,
    lock: asyncio.Lock,
    watchlist_tickers: list[str] | None = None,
) -> None:
    """Run the scan pipeline as a background task.

    The lock is already acquired by the caller — this task releases it on completion.
    """
    try:
        result: ScanResult = await pipeline.run(
            preset, token, bridge, watchlist_tickers=watchlist_tickers
        )

        # Persist
        actual_id = await repo.save_scan_run(result.scan_run)
        await repo.save_ticker_scores(actual_id, result.scores)

        bridge.complete(actual_id, cancelled=result.cancelled)
    except Exception:
        logger.exception("Scan %d failed", scan_id)
        bridge.error("Scan failed due to an internal error")
        bridge.complete(scan_id, cancelled=False)
    finally:
        lock.release()
        # Clean up app.state references
        active_scans: dict[int, CancellationToken] = getattr(request.app.state, "active_scans", {})
        active_scans.pop(scan_id, None)
        scan_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            request.app.state, "scan_queues", {}
        )
        scan_queues.pop(scan_id, None)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post("/scan", status_code=202)
async def start_scan(
    request: Request,
    body: ScanRequest,
    lock: asyncio.Lock = Depends(get_operation_lock),
    settings: AppSettings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
    market_data: MarketDataService = Depends(get_market_data),
    options_data: OptionsDataService = Depends(get_options_data),
    fred: FredService = Depends(get_fred),
    universe: UniverseService = Depends(get_universe),
) -> ScanStarted:
    """Start a new scan pipeline in the background."""
    if lock.locked():
        raise HTTPException(409, "Another operation is in progress")

    # Resolve watchlist_id → ticker list
    watchlist_tickers: list[str] | None = None
    if body.watchlist_id is not None:
        watchlist = await repo.get_watchlist_by_id(body.watchlist_id)
        if watchlist is None:
            raise HTTPException(404, f"Watchlist {body.watchlist_id} not found")
        ticker_rows = await repo.get_tickers_for_watchlist(body.watchlist_id)
        if not ticker_rows:
            raise HTTPException(422, "Watchlist is empty")
        watchlist_tickers = [t.ticker for t in ticker_rows]

    # Acquire the lock atomically before any awaits to prevent TOCTOU race
    await lock.acquire()

    token = CancellationToken()
    bridge = WebSocketProgressBridge()
    pipeline = ScanPipeline(
        settings=settings,
        market_data=market_data,
        options_data=options_data,
        fred=fred,
        universe=universe,
        repository=repo,
    )

    # Use a counter for scan IDs (no orphaned placeholder rows)
    if not hasattr(request.app.state, "scan_counter"):
        request.app.state.scan_counter = 0
    request.app.state.scan_counter += 1
    scan_id: int = request.app.state.scan_counter

    # Register for WebSocket + cancellation
    if not hasattr(request.app.state, "active_scans"):
        request.app.state.active_scans = {}
    if not hasattr(request.app.state, "scan_queues"):
        request.app.state.scan_queues = {}

    request.app.state.active_scans[scan_id] = token
    request.app.state.scan_queues[scan_id] = bridge.queue

    # Background task owns the lock and releases it on completion
    asyncio.create_task(
        _run_scan_background(
            request, scan_id, body.preset, token, bridge, pipeline, repo, lock,
            watchlist_tickers=watchlist_tickers,
        )
    )
    return ScanStarted(scan_id=scan_id)


@router.get("/scan")
async def list_scans(
    repo: Repository = Depends(get_repo),
    limit: int = Query(10, ge=1, le=100),
) -> list[ScanRun]:
    """List past scan runs, newest first."""
    return await repo.get_recent_scans(limit=limit)


@router.get("/scan/{scan_id}")
async def get_scan(
    scan_id: int,
    repo: Repository = Depends(get_repo),
) -> ScanRun:
    """Get a single scan run's metadata."""
    scan = await repo.get_scan_by_id(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return scan


@router.get("/scan/{scan_id}/scores")
async def get_scores(
    scan_id: int,
    repo: Repository = Depends(get_repo),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("composite_score"),
    order: str = Query("desc"),
    direction: str | None = Query(None),
    min_score: float = Query(0.0, ge=0.0),
    search: str | None = Query(None),
) -> PaginatedResponse[TickerScore]:
    """Get paginated scores for a scan run with filtering/sorting."""
    all_scores = await repo.get_scores_for_scan(scan_id)
    if not all_scores:
        # Check whether the scan exists at all
        scan = await repo.get_scan_by_id(scan_id)
        if scan is None:
            raise HTTPException(404, "Scan not found")

    # Filter
    filtered = all_scores
    if min_score > 0.0:
        filtered = [s for s in filtered if s.composite_score >= min_score]
    if direction is not None:
        try:
            dir_enum = SignalDirection(direction)
            filtered = [s for s in filtered if s.direction == dir_enum]
        except ValueError:
            pass
    if search:
        search_upper = search.upper()
        filtered = [s for s in filtered if search_upper in s.ticker.upper()]

    # Sort
    reverse = order.lower() == "desc"
    if sort == "ticker":
        filtered.sort(key=lambda s: s.ticker, reverse=reverse)
    else:
        filtered.sort(key=lambda s: s.composite_score, reverse=reverse)

    # Paginate
    total = len(filtered)
    pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    items = filtered[start : start + page_size]

    return PaginatedResponse[TickerScore](items=items, total=total, page=page, pages=pages)


@router.get("/scan/{scan_id}/scores/{ticker}")
async def get_ticker_detail(
    scan_id: int,
    ticker: str,
    repo: Repository = Depends(get_repo),
) -> TickerDetail:
    """Get a single ticker's score and recommended contracts."""
    all_scores = await repo.get_scores_for_scan(scan_id)
    ticker_upper = ticker.upper()
    match = next((s for s in all_scores if s.ticker == ticker_upper), None)
    if match is None:
        raise HTTPException(404, f"Ticker {ticker_upper} not found in scan {scan_id}")
    return TickerDetail(
        ticker=match.ticker,
        composite_score=match.composite_score,
        direction=match.direction,
        contracts=[],  # contracts not persisted in DB — empty for now
    )


@router.delete("/scan/current")
async def cancel_scan(request: Request) -> dict[str, str]:
    """Cancel the currently running scan."""
    active_scans: dict[int, CancellationToken] = getattr(request.app.state, "active_scans", {})
    if not active_scans:
        raise HTTPException(404, "No scan in progress")
    for scan_id, token in active_scans.items():
        token.cancel()
        logger.info("Cancelled scan %d", scan_id)
    return {"status": "cancelled"}
