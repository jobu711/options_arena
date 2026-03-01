"""Ticker-specific endpoints -- score history and trending tickers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query

from options_arena.api.deps import get_repo
from options_arena.data import Repository
from options_arena.models import HistoryPoint, TrendingTicker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ticker"])


@router.get("/ticker/{ticker}/history")
async def get_ticker_history(
    ticker: str = Path(min_length=1, max_length=10, pattern=r"^[A-Z0-9.\-^]{1,10}$"),
    repo: Repository = Depends(get_repo),
    limit: int = Query(20, ge=1, le=100),
) -> list[HistoryPoint]:
    """Get score history for a ticker across recent scans."""
    return await repo.get_score_history(ticker, limit=limit)


@router.get("/ticker/trending")
async def get_trending_tickers(
    repo: Repository = Depends(get_repo),
    direction: str = Query("bullish"),
    min_scans: int = Query(3, ge=1, le=50),
) -> list[TrendingTicker]:
    """Get tickers trending in a consistent direction over recent scans."""
    return await repo.get_trending_tickers(direction, min_scans=min_scans)
