"""Watchlist endpoints — CRUD for watchlists and their tickers."""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from options_arena.api.deps import get_repo
from options_arena.api.schemas import (
    WatchlistAddTickerRequest,
    WatchlistCreateRequest,
    WatchlistUpdateRequest,
)
from options_arena.data import Repository
from options_arena.models import Watchlist, WatchlistDetail, WatchlistTicker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.post("/watchlists", status_code=201)
async def create_watchlist(
    body: WatchlistCreateRequest,
    repo: Repository = Depends(get_repo),
) -> Watchlist:
    """Create a new watchlist."""
    try:
        watchlist_id = await repo.create_watchlist(body.name, body.description)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Watchlist with name '{body.name}' already exists") from None
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:  # pragma: no cover — should never happen after successful insert
        raise HTTPException(500, "Failed to retrieve created watchlist")
    return watchlist


@router.get("/watchlists")
async def list_watchlists(
    repo: Repository = Depends(get_repo),
) -> list[Watchlist]:
    """List all watchlists."""
    return await repo.get_all_watchlists()


@router.get("/watchlists/{watchlist_id}")
async def get_watchlist(
    watchlist_id: int,
    repo: Repository = Depends(get_repo),
) -> WatchlistDetail:
    """Get a watchlist with its tickers."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    tickers = await repo.get_tickers_for_watchlist(watchlist_id)
    return WatchlistDetail(
        id=watchlist.id,
        name=watchlist.name,
        description=watchlist.description,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
        tickers=tickers,
    )


@router.put("/watchlists/{watchlist_id}")
async def update_watchlist(
    watchlist_id: int,
    body: WatchlistUpdateRequest,
    repo: Repository = Depends(get_repo),
) -> Watchlist:
    """Update a watchlist's name and/or description."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.update_watchlist(watchlist_id, name=body.name, description=body.description)
    updated = await repo.get_watchlist_by_id(watchlist_id)
    if updated is None:  # pragma: no cover — should never happen after successful update
        raise HTTPException(500, "Failed to retrieve updated watchlist")
    return updated


@router.delete("/watchlists/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: int,
    repo: Repository = Depends(get_repo),
) -> Response:
    """Delete a watchlist and all its tickers."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.delete_watchlist(watchlist_id)
    return Response(status_code=204)


@router.post("/watchlists/{watchlist_id}/tickers", status_code=201)
async def add_ticker(
    watchlist_id: int,
    body: WatchlistAddTickerRequest,
    repo: Repository = Depends(get_repo),
) -> WatchlistTicker:
    """Add a ticker to a watchlist."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    ticker_upper = body.ticker.upper()
    try:
        await repo.add_ticker_to_watchlist(watchlist_id, ticker_upper)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Ticker '{ticker_upper}' already in watchlist") from None
    # Return the newly added ticker
    tickers = await repo.get_tickers_for_watchlist(watchlist_id)
    match = next((t for t in tickers if t.ticker == ticker_upper), None)
    if match is None:  # pragma: no cover — should never happen after successful insert
        raise HTTPException(500, "Failed to retrieve added ticker")
    return match


@router.delete("/watchlists/{watchlist_id}/tickers/{ticker}", status_code=204)
async def remove_ticker(
    watchlist_id: int,
    ticker: str,
    repo: Repository = Depends(get_repo),
) -> Response:
    """Remove a ticker from a watchlist."""
    watchlist = await repo.get_watchlist_by_id(watchlist_id)
    if watchlist is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    await repo.remove_ticker_from_watchlist(watchlist_id, ticker.upper())
    return Response(status_code=204)
