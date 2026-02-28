"""Watchlist endpoints -- CRUD for user-defined watchlists."""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from options_arena.api.deps import get_repo
from options_arena.api.schemas import (
    WatchlistCreateRequest,
    WatchlistCreateResponse,
    WatchlistTickerRequest,
)
from options_arena.data import Repository
from options_arena.models import Watchlist, WatchlistDetail, WatchlistTickerDetail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.post("/watchlist", status_code=201)
async def create_watchlist(
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
async def delete_watchlist(
    watchlist_id: int,
    repo: Repository = Depends(get_repo),
) -> None:
    """Delete a watchlist by ID.  Returns 404 if not found."""
    existing = await repo.get_watchlist_by_id(watchlist_id)
    if existing is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.delete_watchlist(watchlist_id)


@router.get("/watchlist")
async def list_watchlists(
    repo: Repository = Depends(get_repo),
) -> list[Watchlist]:
    """List all watchlists, ordered by name."""
    return await repo.get_watchlists()


@router.get("/watchlist/{watchlist_id}")
async def get_watchlist(
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
    scores_by_ticker: dict[str, tuple[float, str]] = {}
    if latest_scan is not None and latest_scan.id is not None:
        all_scores = await repo.get_scores_for_scan(latest_scan.id)
        for score in all_scores:
            scores_by_ticker[score.ticker] = (
                score.composite_score,
                score.direction.value,
            )

    for wt in tickers:
        score_data = scores_by_ticker.get(wt.ticker)
        composite_score = score_data[0] if score_data is not None else None
        direction = score_data[1] if score_data is not None else None

        # Get last debate date for this ticker
        debates = await repo.get_debates_for_ticker(wt.ticker, limit=1)
        last_debate_at = debates[0].created_at if debates else None

        enriched.append(
            WatchlistTickerDetail(
                ticker=wt.ticker,
                added_at=wt.added_at,
                composite_score=composite_score,
                direction=direction,
                last_debate_at=last_debate_at,
            )
        )

    return WatchlistDetail(
        id=watchlist.id,
        name=watchlist.name,
        created_at=watchlist.created_at,
        tickers=enriched,
    )


@router.post("/watchlist/{watchlist_id}/tickers", status_code=201)
async def add_ticker(
    watchlist_id: int,
    body: WatchlistTickerRequest,
    repo: Repository = Depends(get_repo),
) -> dict[str, str]:
    """Add a ticker to a watchlist.  Returns 409 on duplicate, 404 if watchlist not found."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    try:
        await repo.add_ticker_to_watchlist(watchlist_id, body.ticker)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, f"Ticker '{body.ticker.upper()}' already in watchlist") from exc
    return {"status": "added", "ticker": body.ticker.upper()}


@router.delete("/watchlist/{watchlist_id}/tickers/{ticker}", status_code=204)
async def remove_ticker(
    watchlist_id: int,
    ticker: str,
    repo: Repository = Depends(get_repo),
) -> None:
    """Remove a ticker from a watchlist."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.remove_ticker_from_watchlist(watchlist_id, ticker)
