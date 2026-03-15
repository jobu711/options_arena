"""Ticker-specific endpoints -- score history, trending tickers, and ticker info."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_market_data, get_repo
from options_arena.data import Repository
from options_arena.models import HistoryPoint, TickerInfo, TrendingTicker
from options_arena.models.enums import SignalDirection
from options_arena.services.market_data import MarketDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ticker"])


@router.get("/ticker/{ticker}/history")
@limiter.limit("60/minute")
async def get_ticker_history(
    request: Request,
    ticker: str = Path(
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z0-9][A-Z0-9.\-^]{0,9}$",
    ),
    repo: Repository = Depends(get_repo),
    limit: int = Query(20, ge=1, le=100),
) -> list[HistoryPoint]:
    """Get score history for a ticker across recent scans."""
    return await repo.get_score_history(ticker, limit=limit)


@router.get("/ticker/{ticker}/info")
@limiter.limit("60/minute")
async def get_ticker_info(
    request: Request,
    ticker: str = Path(
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z0-9][A-Z0-9.\-^]{0,9}$",
    ),
    market_data: MarketDataService = Depends(get_market_data),
) -> TickerInfo:
    """Get fundamental info for a ticker (company name, sector, price, etc.)."""
    return await market_data.fetch_ticker_info(ticker)


@router.get("/ticker/trending")
@limiter.limit("60/minute")
async def get_trending_tickers(
    request: Request,
    repo: Repository = Depends(get_repo),
    direction: SignalDirection = Query(SignalDirection.BULLISH),
    min_scans: int = Query(3, ge=1, le=50),
) -> list[TrendingTicker]:
    """Get tickers trending in a consistent direction over recent scans."""
    return await repo.get_trending_tickers(direction.value, min_scans=min_scans)
