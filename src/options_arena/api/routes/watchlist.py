"""Watchlist endpoints -- CRUD for user-defined watchlists."""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_repo
from options_arena.api.schemas import (
    WatchlistCreateRequest,
    WatchlistCreateResponse,
    WatchlistTickerAddedResponse,
    WatchlistTickerRequest,
)
from options_arena.data import Repository
from options_arena.models import SignalDirection, Watchlist, WatchlistDetail, WatchlistTickerDetail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.post("/watchlist", status_code=201)
@limiter.limit("60/minute")
async def create_watchlist(
    request: Request,
    body: WatchlistCreateRequest,
    repo: Repository = Depends(get_repo),
) -> WatchlistCreateResponse:
    """Create a new watchlist.  Returns 409 if name already exists."""
    try:
        watchlist = await repo.create_watchlist(body.name)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, f"Watchlist '{body.name}' already exists") from exc
    return WatchlistCreateResponse(id=watchlist.id, name=watchlist.name)


@router.delete("/watchlist/{watchlist_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_watchlist(
    request: Request,
    watchlist_id: int,
    repo: Repository = Depends(get_repo),
) -> None:
    """Delete a watchlist by ID.  Returns 404 if not found."""
    existing = await repo.get_watchlist_by_id(watchlist_id)
    if existing is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.delete_watchlist(watchlist_id)


@router.get("/watchlist")
@limiter.limit("60/minute")
async def list_watchlists(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[Watchlist]:
    """List all watchlists, ordered by name."""
    return await repo.get_watchlists()


@router.get("/watchlist/{watchlist_id}")
@limiter.limit("60/minute")
async def get_watchlist(
    request: Request,
    watchlist_id: int,
    repo: Repository = Depends(get_repo),
) -> WatchlistDetail:
    """Get a watchlist with enriched ticker data (latest scores, last debate date)."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")

    tickers = await repo.get_tickers_for_watchlist(watchlist_id)

    # Enrich each ticker with latest score and last debate date
    enriched: list[WatchlistTickerDetail] = []

    # Get the latest scan for score lookups
    latest_scan = await repo.get_latest_scan()
    scores_by_ticker: dict[str, tuple[float, SignalDirection]] = {}
    if latest_scan is not None and latest_scan.id is not None:
        all_scores = await repo.get_scores_for_scan(latest_scan.id)
        for score in all_scores:
            scores_by_ticker[score.ticker] = (
                score.composite_score,
                score.direction,
            )

    # Batch-fetch last debate dates (avoids N+1 query)
    ticker_names = [wt.ticker for wt in tickers]
    last_debate_dates = await repo.get_last_debate_dates(ticker_names)

    for wt in tickers:
        score_data = scores_by_ticker.get(wt.ticker)
        composite_score = score_data[0] if score_data is not None else None
        direction = score_data[1] if score_data is not None else None

        enriched.append(
            WatchlistTickerDetail(
                ticker=wt.ticker,
                added_at=wt.added_at,
                composite_score=composite_score,
                direction=direction,
                last_debate_at=last_debate_dates.get(wt.ticker),
            )
        )

    return WatchlistDetail(
        id=watchlist.id,
        name=watchlist.name,
        created_at=watchlist.created_at,
        tickers=enriched,
    )


@router.post("/watchlist/{watchlist_id}/tickers", status_code=201)
@limiter.limit("60/minute")
async def add_ticker(
    request: Request,
    watchlist_id: int,
    body: WatchlistTickerRequest,
    repo: Repository = Depends(get_repo),
) -> WatchlistTickerAddedResponse:
    """Add a ticker to a watchlist.  Returns 409 on duplicate, 404 if watchlist not found."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    try:
        await repo.add_ticker_to_watchlist(watchlist_id, body.ticker)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, f"Ticker '{body.ticker.upper()}' already in watchlist") from exc
    return WatchlistTickerAddedResponse(status="added", ticker=body.ticker.upper())


@router.delete("/watchlist/{watchlist_id}/tickers/{ticker}", status_code=204)
@limiter.limit("60/minute")
async def remove_ticker(
    request: Request,
    watchlist_id: int,
    ticker: str = Path(
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z0-9][A-Z0-9.\-^]{0,9}$",
    ),
    repo: Repository = Depends(get_repo),
) -> None:
    """Remove a ticker from a watchlist."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.remove_ticker_from_watchlist(watchlist_id, ticker)
