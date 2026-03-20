"""Learning system endpoints — weight history, status, and tuning trigger."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_operation_lock, get_repo
from options_arena.data import Repository
from options_arena.learning import auto_tune_indicator_weights
from options_arena.models import (
    IndicatorWeightComparison,
    LearningStatus,
    WeightSnapshot,
    WeightType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/weights")
@limiter.limit("60/minute")
async def get_current_weights(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[WeightSnapshot]:
    """Get the most recent vote and indicator weight snapshots."""
    vote = await repo.get_weight_history(limit=1, weight_type=WeightType.VOTE)
    indicator = await repo.get_weight_history(limit=1, weight_type=WeightType.INDICATOR)
    return vote + indicator


@router.get("/weights/history")
@limiter.limit("60/minute")
async def get_weight_history(
    request: Request,
    repo: Repository = Depends(get_repo),
    weight_type: str | None = Query(None, description="Filter: 'vote' or 'indicator'"),
    limit: int = Query(20, ge=1, le=100),
) -> list[WeightSnapshot]:
    """Retrieve historical weight snapshots, newest first."""
    wt: WeightType | None = None
    if weight_type is not None:
        try:
            wt = WeightType(weight_type)
        except ValueError as exc:
            raise HTTPException(422, "Invalid weight_type. Use 'vote' or 'indicator'.") from exc

    return await repo.get_weight_history(limit=limit, weight_type=wt)


@router.get("/status")
@limiter.limit("60/minute")
async def get_learning_status(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> LearningStatus:
    """Get learning system status: last tune timestamps and counts."""
    vote_history = await repo.get_weight_history(limit=1, weight_type=WeightType.VOTE)
    indicator_history = await repo.get_weight_history(limit=1, weight_type=WeightType.INDICATOR)

    return LearningStatus(
        last_vote_tune=(vote_history[0].computed_at if vote_history else None),
        last_indicator_tune=(indicator_history[0].computed_at if indicator_history else None),
        vote_agent_count=(len(vote_history[0].weights) if vote_history else 0),
        indicator_count=(len(indicator_history[0].weights) if indicator_history else 0),
        accuracy_at_last_tune=(
            indicator_history[0].accuracy_at_time if indicator_history else None
        ),
    )


@router.post("/weights/tune")
@limiter.limit("5/minute")
async def trigger_indicator_tune(
    request: Request,
    repo: Repository = Depends(get_repo),
    lock: asyncio.Lock = Depends(get_operation_lock),
    window: int = Query(90, ge=1, le=365),
    dry_run: bool = Query(False),
) -> list[IndicatorWeightComparison]:
    """Trigger indicator weight tuning from historical outcome data.

    Requires the operation mutex (409 if another scan/debate is running).
    """
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None
    try:
        return await auto_tune_indicator_weights(repo, window_days=window, dry_run=dry_run)
    finally:
        lock.release()
