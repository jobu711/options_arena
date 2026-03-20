"""Learning system endpoints — weight history, status, tuning, and strategy playbook."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_operation_lock, get_repo
from options_arena.api.schemas import UpdateStatusResponse
from options_arena.data import Repository
from options_arena.learning import auto_tune_indicator_weights, run_strategy_mining
from options_arena.models import (
    IndicatorWeightComparison,
    LearningStatus,
    RuleStatus,
    StrategyRule,
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
    weight_type: WeightType | None = Query(None, description="Filter: 'vote' or 'indicator'"),
    limit: int = Query(20, ge=1, le=100),
) -> list[WeightSnapshot]:
    """Retrieve historical weight snapshots, newest first."""
    return await repo.get_weight_history(limit=limit, weight_type=weight_type)


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


# ---------------------------------------------------------------------------
# Strategy Playbook endpoints
# ---------------------------------------------------------------------------


@router.post("/mine")
@limiter.limit("5/minute")
async def trigger_mining(
    request: Request,
    repo: Repository = Depends(get_repo),
    lock: asyncio.Lock = Depends(get_operation_lock),
) -> list[StrategyRule]:
    """Trigger strategy pattern mining from historical outcome data.

    Requires the operation mutex (409 if another scan/debate is running).
    """
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None
    try:
        return await asyncio.wait_for(run_strategy_mining(repo), timeout=300.0)
    except TimeoutError:
        return []
    finally:
        lock.release()


@router.get("/playbook")
@limiter.limit("60/minute")
async def get_playbook(
    request: Request,
    repo: Repository = Depends(get_repo),
    status: RuleStatus | None = Query(None, description="Filter by status"),
) -> list[StrategyRule]:
    """List strategy rules, optionally filtered by status."""
    return await repo.get_strategy_rules(status=status)


@router.put("/playbook/{rule_id}")
@limiter.limit("30/minute")
async def update_rule_status(
    request: Request,
    rule_id: str,
    status: RuleStatus = Query(..., description="New status: approved or rejected"),
    repo: Repository = Depends(get_repo),
) -> UpdateStatusResponse:
    """Update the status of a strategy rule (approve/reject)."""
    updated = await repo.update_rule_status(rule_id, status)
    if not updated:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    return UpdateStatusResponse(updated=True)
