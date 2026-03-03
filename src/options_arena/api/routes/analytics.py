"""Analytics endpoints — win rate, score calibration, delta performance, and more."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_operation_lock, get_outcome_collector, get_repo
from options_arena.data import Repository
from options_arena.models import (
    DeltaPerformanceResult,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    PerformanceSummary,
    RecommendedContract,
    ScoreCalibrationBucket,
    SignalDirection,
    WinRateResult,
)
from options_arena.services.outcome_collector import OutcomeCollector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/win-rate")
@limiter.limit("60/minute")
async def get_win_rate(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[WinRateResult]:
    """Get win rate by signal direction."""
    return await repo.get_win_rate_by_direction()


@router.get("/score-calibration")
@limiter.limit("60/minute")
async def get_score_calibration(
    request: Request,
    bucket_size: float = Query(default=10.0, ge=1.0),
    repo: Repository = Depends(get_repo),
) -> list[ScoreCalibrationBucket]:
    """Get score calibration buckets — return by composite score range."""
    return await repo.get_score_calibration(bucket_size=bucket_size)


@router.get("/indicator-attribution/{indicator}")
@limiter.limit("60/minute")
async def get_indicator_attribution(
    request: Request,
    indicator: str,
    holding_days: int = Query(default=5, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[IndicatorAttributionResult]:
    """Get indicator attribution — correlation between indicator values and returns."""
    return await repo.get_indicator_attribution(indicator=indicator, holding_days=holding_days)


@router.get("/holding-period")
@limiter.limit("60/minute")
async def get_holding_period(
    request: Request,
    direction: SignalDirection | None = Query(default=None),
    repo: Repository = Depends(get_repo),
) -> list[HoldingPeriodResult]:
    """Get holding period analysis — return statistics by holding period."""
    return await repo.get_optimal_holding_period(direction=direction)


@router.get("/delta-performance")
@limiter.limit("60/minute")
async def get_delta_performance(
    request: Request,
    bucket_size: float = Query(default=0.1, gt=0),
    holding_days: int = Query(default=5, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[DeltaPerformanceResult]:
    """Get delta performance — return statistics by delta bucket."""
    return await repo.get_delta_performance(bucket_size=bucket_size, holding_days=holding_days)


@router.get("/summary")
@limiter.limit("60/minute")
async def get_summary(
    request: Request,
    lookback_days: int = Query(default=30, ge=1),
    repo: Repository = Depends(get_repo),
) -> PerformanceSummary:
    """Get aggregate performance summary over a lookback period."""
    return await repo.get_performance_summary(lookback_days=lookback_days)


@router.post("/collect-outcomes", status_code=202)
@limiter.limit("5/minute")
async def collect_outcomes(
    request: Request,
    holding_days: int | None = Query(default=None, ge=1),
    collector: OutcomeCollector = Depends(get_outcome_collector),
    lock: asyncio.Lock = Depends(get_operation_lock),
) -> dict[str, int]:
    """Trigger outcome collection.

    Uses the operation mutex to prevent concurrent runs. Returns count
    of outcomes collected.
    """
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    try:
        outcomes = await collector.collect_outcomes(holding_days=holding_days)
        return {"outcomes_collected": len(outcomes)}
    finally:
        lock.release()


@router.get("/scan/{scan_id}/contracts")
@limiter.limit("60/minute")
async def get_scan_contracts(
    request: Request,
    scan_id: int,
    repo: Repository = Depends(get_repo),
) -> list[RecommendedContract]:
    """Get recommended contracts for a specific scan run."""
    return await repo.get_contracts_for_scan(scan_id)


@router.get("/ticker/{ticker}/contracts")
@limiter.limit("60/minute")
async def get_ticker_contracts(
    request: Request,
    ticker: str,
    limit: int = Query(default=50, ge=1, le=200),
    repo: Repository = Depends(get_repo),
) -> list[RecommendedContract]:
    """Get recommended contracts for a specific ticker."""
    return await repo.get_contracts_for_ticker(ticker, limit=limit)
