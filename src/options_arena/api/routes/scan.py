"""Scan endpoints — start, list, results, cancel."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
    get_theme_service,
    get_universe,
)
from options_arena.api.schemas import (
    CancelScanResponse,
    PaginatedResponse,
    ScanRequest,
    ScanStarted,
    TickerDetail,
)
from options_arena.api.ws import WebSocketProgressBridge
from options_arena.data import Repository
from options_arena.models import (
    AppSettings,
    MarketRegime,
    ScanDiff,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerDelta,
    TickerScore,
)
from options_arena.scan import CancellationToken, ScanPipeline, ScanResult
from options_arena.services import (
    FredService,
    MarketDataService,
    OptionsDataService,
    UniverseService,
)
from options_arena.services.theme_service import ThemeService

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
) -> None:
    """Run the scan pipeline as a background task.

    The lock is already acquired by the caller — this task releases it on completion.
    """
    try:
        result: ScanResult = await pipeline.run(preset, token, bridge)

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
        # Clean up app.state references (initialized in lifespan)
        request.app.state.active_scans.pop(scan_id, None)
        request.app.state.scan_queues.pop(scan_id, None)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post("/scan", status_code=202)
@limiter.limit("5/minute")
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
    theme_service: ThemeService = Depends(get_theme_service),
) -> ScanStarted:
    """Start a new scan pipeline in the background."""
    # Atomic try-acquire: eliminates TOCTOU race between lock.locked() and acquire()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    token = CancellationToken()
    bridge = WebSocketProgressBridge()

    # Apply per-request filters to settings (immutable copy pattern)
    effective_settings = settings
    scan_overrides: dict[str, object] = {}
    if body.sectors:
        scan_overrides["sectors"] = body.sectors
    if body.market_cap_tiers:
        scan_overrides["market_cap_tiers"] = body.market_cap_tiers
    if body.exclude_near_earnings_days is not None:
        scan_overrides["exclude_near_earnings_days"] = body.exclude_near_earnings_days
    if body.direction_filter is not None:
        scan_overrides["direction_filter"] = body.direction_filter
    if body.min_iv_rank is not None:
        scan_overrides["min_iv_rank"] = body.min_iv_rank
    if body.industry_groups:
        scan_overrides["industry_groups"] = body.industry_groups
    if body.themes:
        scan_overrides["theme_filters"] = body.themes
    if scan_overrides:
        scan_override = settings.scan.model_copy(update=scan_overrides)
        effective_settings = settings.model_copy(update={"scan": scan_override})

    pipeline = ScanPipeline(
        settings=effective_settings,
        market_data=market_data,
        options_data=options_data,
        fred=fred,
        universe=universe,
        repository=repo,
        theme_service=theme_service,
    )

    # Use a counter for scan IDs (initialized in lifespan)
    request.app.state.scan_counter += 1
    scan_id: int = request.app.state.scan_counter

    # Register for WebSocket + cancellation
    request.app.state.active_scans[scan_id] = token
    request.app.state.scan_queues[scan_id] = bridge.queue

    # Background task owns the lock and releases it on completion
    asyncio.create_task(
        _run_scan_background(request, scan_id, body.preset, token, bridge, pipeline, repo, lock)
    )
    return ScanStarted(scan_id=scan_id)


@router.get("/scan")
@limiter.limit("60/minute")
async def list_scans(
    request: Request,
    repo: Repository = Depends(get_repo),
    limit: int = Query(10, ge=1, le=100),
) -> list[ScanRun]:
    """List past scan runs, newest first."""
    return await repo.get_recent_scans(limit=limit)


@router.get("/scan/{scan_id}")
@limiter.limit("60/minute")
async def get_scan(
    request: Request,
    scan_id: int,
    repo: Repository = Depends(get_repo),
) -> ScanRun:
    """Get a single scan run's metadata."""
    scan = await repo.get_scan_by_id(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return scan


@router.get("/scan/{scan_id}/scores")
@limiter.limit("60/minute")
async def get_scores(  # noqa: ANN201
    request: Request,
    scan_id: int,
    repo: Repository = Depends(get_repo),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("composite_score"),
    order: str = Query("desc"),
    direction: str | None = Query(None),
    min_score: float = Query(0.0, ge=0.0),
    search: str | None = Query(None),
    sectors: str | None = Query(None),
    # Dimensional filters (#224)
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    market_regime: str | None = Query(None),
    min_trend: float | None = Query(None, ge=0.0, le=100.0),
    min_iv_vol: float | None = Query(None, ge=0.0, le=100.0),
    min_flow: float | None = Query(None, ge=0.0, le=100.0),
    min_risk: float | None = Query(None, ge=0.0, le=100.0),
    max_earnings_days: int | None = Query(None, ge=0),
    min_earnings_days: int | None = Query(None, ge=0),
    # GICS industry group + theme filters (#230)
    industry_groups: str | None = Query(None),
    themes: str | None = Query(None),
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
    if sectors:
        sector_set = {s.strip().lower() for s in sectors.split(",") if s.strip()}
        filtered = [s for s in filtered if s.sector is not None and s.sector.lower() in sector_set]

    # Dimensional filters (#224)
    if min_confidence is not None:
        filtered = [
            s
            for s in filtered
            if s.direction_confidence is not None and s.direction_confidence >= min_confidence
        ]
    if market_regime is not None:
        try:
            regime_enum = MarketRegime(market_regime)
            filtered = [s for s in filtered if s.market_regime == regime_enum]
        except ValueError:
            pass
    if min_trend is not None:
        filtered = [
            s
            for s in filtered
            if s.dimensional_scores is not None
            and s.dimensional_scores.trend is not None
            and s.dimensional_scores.trend >= min_trend
        ]
    if min_iv_vol is not None:
        filtered = [
            s
            for s in filtered
            if s.dimensional_scores is not None
            and s.dimensional_scores.iv_vol is not None
            and s.dimensional_scores.iv_vol >= min_iv_vol
        ]
    if min_flow is not None:
        filtered = [
            s
            for s in filtered
            if s.dimensional_scores is not None
            and s.dimensional_scores.flow is not None
            and s.dimensional_scores.flow >= min_flow
        ]
    if min_risk is not None:
        filtered = [
            s
            for s in filtered
            if s.dimensional_scores is not None
            and s.dimensional_scores.risk is not None
            and s.dimensional_scores.risk >= min_risk
        ]
    if max_earnings_days is not None or min_earnings_days is not None:
        market_today = datetime.now(ZoneInfo("America/New_York")).date()
        if max_earnings_days is not None:
            filtered = [
                s
                for s in filtered
                if s.next_earnings is not None
                and (s.next_earnings - market_today).days <= max_earnings_days
            ]
        if min_earnings_days is not None:
            filtered = [
                s
                for s in filtered
                if s.next_earnings is not None
                and (s.next_earnings - market_today).days >= min_earnings_days
            ]

    # Industry group filter (#230)
    if industry_groups:
        ig_set = {g.strip().lower() for g in industry_groups.split(",") if g.strip()}
        filtered = [
            s
            for s in filtered
            if s.industry_group is not None and s.industry_group.value.lower() in ig_set
        ]

    # Theme filter (#230)
    if themes:
        theme_set = {t.strip() for t in themes.split(",") if t.strip()}
        filtered = [s for s in filtered if any(tag in theme_set for tag in s.thematic_tags)]

    # Sort
    reverse = order.lower() == "desc"
    if sort == "ticker":
        filtered.sort(key=lambda s: s.ticker, reverse=reverse)
    elif sort == "direction_confidence":
        filtered.sort(
            key=lambda s: s.direction_confidence if s.direction_confidence is not None else -1.0,
            reverse=reverse,
        )
    else:
        filtered.sort(key=lambda s: s.composite_score, reverse=reverse)

    # Paginate
    total = len(filtered)
    pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    items = filtered[start : start + page_size]

    return PaginatedResponse[TickerScore](items=items, total=total, page=page, pages=pages)


@router.get("/scan/{scan_id}/scores/{ticker}")
@limiter.limit("60/minute")
async def get_ticker_detail(
    request: Request,
    scan_id: int,
    ticker: str = Path(
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z0-9][A-Z0-9.\-^]{0,9}$",
    ),
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


@router.get("/scan/{scan_id}/diff")
@limiter.limit("60/minute")
async def get_scan_diff(
    request: Request,
    scan_id: int,
    repo: Repository = Depends(get_repo),
    base_id: int = Query(..., description="Base scan ID to compare against"),
) -> ScanDiff:
    """Compute the diff between two scans.

    Compares the current scan (``scan_id``) against a baseline scan (``base_id``),
    returning added/removed tickers and score deltas for common tickers.
    """
    # Validate both scans exist
    current_scan = await repo.get_scan_by_id(scan_id)
    if current_scan is None:
        raise HTTPException(404, f"Scan {scan_id} not found")

    base_scan = await repo.get_scan_by_id(base_id)
    if base_scan is None:
        raise HTTPException(404, f"Base scan {base_id} not found")

    # Fetch scores for both scans
    current_scores = await repo.get_scores_for_scan(scan_id)
    base_scores = await repo.get_scores_for_scan(base_id)

    # Build dicts keyed by ticker
    current_by_ticker: dict[str, TickerScore] = {s.ticker: s for s in current_scores}
    base_by_ticker: dict[str, TickerScore] = {s.ticker: s for s in base_scores}

    current_tickers = set(current_by_ticker.keys())
    base_tickers = set(base_by_ticker.keys())

    # Set operations for added/removed
    added = sorted(current_tickers - base_tickers)
    removed = sorted(base_tickers - current_tickers)

    # Compute deltas for common tickers + new tickers
    movers: list[TickerDelta] = []

    # Common tickers: compute score change
    for ticker in current_tickers & base_tickers:
        curr = current_by_ticker[ticker]
        base = base_by_ticker[ticker]
        score_change = curr.composite_score - base.composite_score
        movers.append(
            TickerDelta(
                ticker=ticker,
                current_score=curr.composite_score,
                previous_score=base.composite_score,
                score_change=score_change,
                current_direction=curr.direction,
                previous_direction=base.direction,
                is_new=False,
            )
        )

    # New tickers: score_change is the full current score (previous = 0)
    for ticker in added:
        curr = current_by_ticker[ticker]
        movers.append(
            TickerDelta(
                ticker=ticker,
                current_score=curr.composite_score,
                previous_score=0.0,
                score_change=curr.composite_score,
                current_direction=curr.direction,
                previous_direction=None,
                is_new=True,
            )
        )

    # Sort by absolute score change descending
    movers.sort(key=lambda d: abs(d.score_change), reverse=True)

    return ScanDiff(
        current_scan_id=scan_id,
        base_scan_id=base_id,
        added=added,
        removed=removed,
        movers=movers,
    )


@router.delete("/scan/current")
@limiter.limit("60/minute")
async def cancel_scan(request: Request) -> CancelScanResponse:
    """Cancel the currently running scan."""
    active_scans: dict[int, CancellationToken] = request.app.state.active_scans
    if not active_scans:
        raise HTTPException(404, "No scan in progress")
    for scan_id, token in active_scans.items():
        token.cancel()
        logger.info("Cancelled scan %d", scan_id)
    return CancelScanResponse(status="cancelled")
