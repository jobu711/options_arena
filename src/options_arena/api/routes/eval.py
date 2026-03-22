"""Eval harness endpoints — run evals, view reports, browse history."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_operation_lock, get_repo, get_settings
from options_arena.data import Repository
from options_arena.evals import run_eval_check
from options_arena.models import AppSettings, EvalDefinition, EvalReport, EvalRun
from options_arena.models.enums import DeskType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.post("/check")
@limiter.limit("5/minute")
async def trigger_eval_check(
    request: Request,
    repo: Repository = Depends(get_repo),
    settings: AppSettings = Depends(get_settings),
    lock: asyncio.Lock = Depends(get_operation_lock),
    desk: str | None = Query(None, description="Filter by desk type"),
) -> EvalReport:
    """Trigger an eval run across all definitions.

    Requires the operation mutex (409 if another scan/debate is running).
    """
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    try:
        desk_filter: DeskType | None = None
        if desk is not None:
            try:
                desk_filter = DeskType(desk.lower())
            except ValueError:
                raise HTTPException(422, f"Unknown desk type: {desk}") from None

        return await asyncio.wait_for(
            run_eval_check(repo, settings.eval, desk_filter=desk_filter),
            timeout=settings.eval.eval_timeout,
        )
    except TimeoutError:
        raise HTTPException(504, "Eval check timed out") from None
    finally:
        lock.release()


@router.get("/report")
@limiter.limit("60/minute")
async def get_eval_report(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[EvalRun]:
    """Get the latest eval run for each definition."""
    return await repo.get_latest_eval_runs()


@router.get("/history")
@limiter.limit("60/minute")
async def get_eval_history(
    request: Request,
    repo: Repository = Depends(get_repo),
    eval_name: str | None = Query(None, description="Filter by eval name"),
    limit: int = Query(50, ge=1, le=500),
) -> list[EvalRun]:
    """Retrieve historical eval runs, newest first."""
    return await repo.get_eval_runs(eval_name=eval_name, limit=limit)


@router.get("/definitions")
@limiter.limit("60/minute")
async def get_eval_definitions(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> list[EvalDefinition]:
    """List all eval definitions."""
    return await repo.get_eval_definitions()
