"""Analytics endpoints — win rate, score calibration, delta performance, and more."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from options_arena.agents import auto_tune_weights
from options_arena.analysis.correlation import compute_correlation_matrix
from options_arena.api.app import limiter
from options_arena.api.deps import (
    get_market_data,
    get_operation_lock,
    get_outcome_collector,
    get_repo,
)
from options_arena.api.schemas import OutcomeCollectionResult
from options_arena.data import Repository
from options_arena.models import (
    AgentAccuracyReport,
    AgentCalibrationData,
    AgentWeightsComparison,
    DeltaPerformanceResult,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    IndicatorSignals,
    PerformanceSummary,
    RecommendedContract,
    RiskAdjustedMetrics,
    ScoreCalibrationBucket,
    SignalDirection,
    WeightSnapshot,
    WinRateResult,
)
from options_arena.models.correlation import CorrelationMatrix
from options_arena.models.enums import TICKER_RE
from options_arena.services.market_data import MarketDataService
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
    if indicator not in IndicatorSignals.model_fields:
        raise HTTPException(400, f"Unknown indicator: {indicator!r}")
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
) -> OutcomeCollectionResult:
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
        return OutcomeCollectionResult(outcomes_collected=len(outcomes))
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
    ticker: str = Path(),
    limit: int = Query(default=50, ge=1, le=200),
    repo: Repository = Depends(get_repo),
) -> list[RecommendedContract]:
    """Get recommended contracts for a specific ticker."""
    ticker = ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(422, f"Invalid ticker format: {ticker!r}")
    return await repo.get_contracts_for_ticker(ticker, limit=limit)


@router.get("/agent-accuracy")
@limiter.limit("60/minute")
async def get_agent_accuracy(
    request: Request,
    window: int | None = Query(default=None, ge=1),
    repo: Repository = Depends(get_repo),
) -> list[AgentAccuracyReport]:
    """Get per-agent direction accuracy and Brier scores."""
    return await repo.get_agent_accuracy(window)


@router.get("/agent-calibration")
@limiter.limit("60/minute")
async def get_agent_calibration(
    request: Request,
    agent: str | None = Query(default=None),
    repo: Repository = Depends(get_repo),
) -> AgentCalibrationData:
    """Get confidence calibration buckets for agents."""
    return await repo.get_agent_calibration(agent)


@router.get("/agent-weights")
@limiter.limit("60/minute")
async def get_agent_weights(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[AgentWeightsComparison]:
    """Get manual vs auto-tuned weight comparison."""
    return await repo.get_latest_auto_tune_weights()


@router.post("/weights/auto-tune")
@limiter.limit("5/minute")
async def trigger_auto_tune(
    request: Request,
    repo: Repository = Depends(get_repo),
    lock: asyncio.Lock = Depends(get_operation_lock),
    window: int = Query(90, ge=1, le=365),
    dry_run: bool = Query(False),
) -> list[AgentWeightsComparison]:
    """Trigger auto-tune weight computation.

    Computes optimal agent weights from historical accuracy data.
    When ``dry_run`` is ``True``, weights are computed but not persisted.
    """
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    try:
        return await auto_tune_weights(repo, window_days=window, dry_run=dry_run)
    finally:
        lock.release()


@router.get("/weights/history")
@limiter.limit("60/minute")
async def get_weight_history(
    request: Request,
    repo: Repository = Depends(get_repo),
    limit: int = Query(20, ge=1, le=100),
) -> list[WeightSnapshot]:
    """Retrieve historical auto-tune weight snapshots, newest first."""
    return await repo.get_weight_history(limit=limit)


@router.get("/risk-metrics")
@limiter.limit("60/minute")
async def get_risk_metrics(
    request: Request,
    lookback_days: int = Query(default=365, ge=1),
    repo: Repository = Depends(get_repo),
) -> RiskAdjustedMetrics:
    """Get risk-adjusted performance metrics (Sharpe, Sortino, max drawdown)."""
    return await repo.get_risk_adjusted_metrics(lookback_days=lookback_days)


@router.get("/correlation")
@limiter.limit("30/minute")
async def get_correlation(
    request: Request,
    tickers: str = Query(..., description="Comma-separated ticker symbols (e.g. AAPL,MSFT,GOOG)"),
    lookback_days: int = Query(default=252, ge=30, le=756),
    market_data: MarketDataService = Depends(get_market_data),
) -> CorrelationMatrix:
    """Compute pairwise Pearson correlation matrix for the given tickers.

    Fetches OHLCV data for each ticker, computes log daily returns,
    and returns the full correlation matrix.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) < 2:  # noqa: PLR2004
        raise HTTPException(422, "At least 2 tickers are required for correlation analysis")
    if len(ticker_list) > 50:  # noqa: PLR2004
        raise HTTPException(422, "Maximum 50 tickers allowed for correlation analysis")

    # Validate each ticker against TICKER_RE
    for t in ticker_list:
        if not TICKER_RE.match(t):
            raise HTTPException(422, f"Invalid ticker format: {t!r}")

    # Deduplicate
    ticker_list = list(dict.fromkeys(ticker_list))

    # Determine period from lookback_days
    if lookback_days <= 252:  # noqa: PLR2004
        period = "1y"
    elif lookback_days <= 504:  # noqa: PLR2004
        period = "2y"
    else:
        period = "3y"

    # Fetch OHLCV for each ticker
    import pandas as pd

    price_data: dict[str, pd.DataFrame] = {}
    batch_result = await market_data.fetch_batch_ohlcv(ticker_list, period=period)
    for item in batch_result.succeeded():
        if item.data:
            # Convert list[OHLCV] to DataFrame with Close column
            rows = [{"date": bar.date, "Close": float(bar.close)} for bar in item.data]
            df = pd.DataFrame(rows).set_index("date")
            price_data[item.ticker] = df

    if len(price_data) < 2:  # noqa: PLR2004
        raise HTTPException(
            422, "Insufficient data: fewer than 2 tickers have valid price history"
        )

    return compute_correlation_matrix(price_data, min_overlap=30)
