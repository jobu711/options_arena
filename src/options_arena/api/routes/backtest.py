"""Backtesting analytics endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_repo
from options_arena.data import Repository
from options_arena.models import (
    DrawdownPoint,
    DTEBucketResult,
    EquityCurvePoint,
    GreeksDecompositionResult,
    HoldingPeriodComparison,
    IVRankBucketResult,
    SectorPerformanceResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics/backtest", tags=["backtest"])


@router.get("/equity-curve")
@limiter.limit("60/minute")
async def get_equity_curve(
    request: Request,
    direction: str | None = Query(default=None),
    period: int | None = Query(default=None, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[EquityCurvePoint]:
    """Get cumulative equity curve from contract outcomes."""
    return await repo.get_equity_curve(direction=direction, period_days=period)


@router.get("/drawdown")
@limiter.limit("60/minute")
async def get_drawdown(
    request: Request,
    period: int | None = Query(default=None, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[DrawdownPoint]:
    """Get drawdown series from the equity curve."""
    return await repo.get_drawdown_series(period_days=period)


@router.get("/sector-performance")
@limiter.limit("60/minute")
async def get_sector_performance(
    request: Request,
    holding_days: int = Query(default=20, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[SectorPerformanceResult]:
    """Get win rate and average return grouped by GICS sector."""
    return await repo.get_win_rate_by_sector(holding_days=holding_days)


@router.get("/dte-performance")
@limiter.limit("60/minute")
async def get_dte_performance(
    request: Request,
    holding_days: int = Query(default=20, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[DTEBucketResult]:
    """Get win rate and average return grouped by DTE buckets."""
    return await repo.get_win_rate_by_dte_bucket(holding_days=holding_days)


@router.get("/iv-performance")
@limiter.limit("60/minute")
async def get_iv_performance(
    request: Request,
    holding_days: int = Query(default=20, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[IVRankBucketResult]:
    """Get win rate and average return grouped by IV rank quartiles."""
    return await repo.get_win_rate_by_iv_rank(holding_days=holding_days)


@router.get("/greeks-decomposition")
@limiter.limit("60/minute")
async def get_greeks_decomposition(
    request: Request,
    groupby: str = Query(default="direction"),
    holding_days: int = Query(default=20, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[GreeksDecompositionResult]:
    """Get P&L decomposition by Greeks (delta-attributable vs residual)."""
    return await repo.get_greeks_decomposition(holding_days=holding_days, groupby=groupby)


@router.get("/holding-comparison")
@limiter.limit("60/minute")
async def get_holding_comparison(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[HoldingPeriodComparison]:
    """Compare performance across holding periods and directions."""
    return await repo.get_holding_period_comparison()
