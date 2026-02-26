"""Debate endpoints — start, list, get result."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.agents import DebateResult, run_debate
from options_arena.api.deps import (
    get_market_data,
    get_options_data,
    get_repo,
    get_settings,
)
from options_arena.api.schemas import DebateRequest, DebateResultSummary, DebateStarted
from options_arena.api.ws import DebateProgressBridge
from options_arena.data import Repository
from options_arena.models import AgentResponse, AppSettings, TradeThesis
from options_arena.services import MarketDataService, OptionsDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["debate"])


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_debate_background(
    request: Request,
    debate_id: int,
    ticker: str,
    scan_id: int | None,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    bridge: DebateProgressBridge,
) -> None:
    """Run the debate orchestrator as a background task."""
    try:
        # Fetch data for the ticker
        quote = await market_data.fetch_quote(ticker)
        ticker_info = await market_data.fetch_ticker_info(ticker)

        # Get contracts (from scan results if scan_id provided, else fetch fresh)
        contracts = []
        if scan_id is not None:
            all_scores = await repo.get_scores_for_scan(scan_id)
            score_match = next((s for s in all_scores if s.ticker == ticker), None)
        else:
            score_match = None

        if score_match is None:
            # Create a minimal TickerScore for the debate
            from options_arena.models import IndicatorSignals, SignalDirection, TickerScore

            score_match = TickerScore(
                ticker=ticker,
                composite_score=50.0,
                direction=SignalDirection.NEUTRAL,
                signals=IndicatorSignals(),
            )

        # Fetch fresh option chains
        chain_results = await options_data.fetch_chain_all_expirations(ticker)
        for chain in chain_results:
            contracts.extend(chain.contracts)

        result: DebateResult = await run_debate(
            ticker_score=score_match,
            contracts=contracts,
            quote=quote,
            ticker_info=ticker_info,
            config=settings.debate,
            repository=repo,
            progress=bridge,
        )

        # Persist debate to DB
        total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
        await repo.save_debate(
            scan_run_id=scan_id,
            ticker=ticker,
            bull_json=result.bull_response.model_dump_json(),
            bear_json=result.bear_response.model_dump_json(),
            risk_json=result.thesis.model_dump_json(),
            verdict_json=result.thesis.model_dump_json(),
            total_tokens=total_tokens,
            model_name=result.bull_response.model_used,
            duration_ms=result.duration_ms,
            is_fallback=result.is_fallback,
            vol_json=(
                result.vol_response.model_dump_json() if result.vol_response is not None else None
            ),
            rebuttal_json=(
                result.bull_rebuttal.model_dump_json()
                if result.bull_rebuttal is not None
                else None
            ),
        )

        bridge.complete(debate_id)
    except Exception:
        logger.exception("Debate %d for %s failed", debate_id, ticker)
        bridge.error(f"Debate failed for {ticker}")
        bridge.complete(debate_id)
    finally:
        # Clean up
        debate_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            request.app.state, "debate_queues", {}
        )
        debate_queues.pop(debate_id, None)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post("/debate", status_code=202)
async def start_debate(
    request: Request,
    body: DebateRequest,
    settings: AppSettings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
    market_data: MarketDataService = Depends(get_market_data),
    options_data: OptionsDataService = Depends(get_options_data),
) -> DebateStarted:
    """Start a single-ticker debate in the background."""
    bridge = DebateProgressBridge()

    # Use a counter for debate IDs since we don't pre-persist
    if not hasattr(request.app.state, "debate_counter"):
        request.app.state.debate_counter = 0
    request.app.state.debate_counter += 1
    debate_id: int = request.app.state.debate_counter

    if not hasattr(request.app.state, "debate_queues"):
        request.app.state.debate_queues = {}

    request.app.state.debate_queues[debate_id] = bridge.queue

    asyncio.create_task(
        _run_debate_background(
            request,
            debate_id,
            body.ticker.upper(),
            body.scan_id,
            settings,
            repo,
            market_data,
            options_data,
            bridge,
        )
    )
    return DebateStarted(debate_id=debate_id)


@router.get("/debate")
async def list_debates(
    repo: Repository = Depends(get_repo),
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> list[DebateResultSummary]:
    """List past debate summaries."""
    if ticker is not None:
        rows = await repo.get_debates_for_ticker(ticker.upper(), limit=limit)
    else:
        rows = await repo.get_recent_debates(limit=limit)

    summaries: list[DebateResultSummary] = []
    for row in rows:
        # Parse verdict to extract direction + confidence
        direction = "neutral"
        confidence = 0.0
        if row.verdict_json is not None:
            try:
                thesis = TradeThesis.model_validate_json(row.verdict_json)
                direction = thesis.direction.value
                confidence = thesis.confidence
            except Exception:
                pass

        summaries.append(
            DebateResultSummary(
                id=row.id,
                ticker=row.ticker,
                direction=direction,
                confidence=confidence,
                is_fallback=row.is_fallback,
                model_name=row.model_name,
                duration_ms=row.duration_ms,
                created_at=row.created_at,
            )
        )
    return summaries


@router.get("/debate/{debate_id}")
async def get_debate(
    debate_id: int,
    repo: Repository = Depends(get_repo),
) -> dict[str, object]:
    """Get full debate result by ID."""
    row = await repo.get_debate_by_id(debate_id)
    if row is None:
        raise HTTPException(404, "Debate not found")

    # Reconstruct structured response from stored JSON
    result: dict[str, object] = {
        "id": row.id,
        "ticker": row.ticker,
        "is_fallback": row.is_fallback,
        "model_name": row.model_name,
        "duration_ms": row.duration_ms,
        "total_tokens": row.total_tokens,
        "created_at": row.created_at.isoformat(),
        "debate_mode": row.debate_mode,
        "citation_density": row.citation_density,
    }

    # Parse stored JSON into typed models for response
    if row.bull_json is not None:
        result["bull_response"] = AgentResponse.model_validate_json(row.bull_json).model_dump()
    if row.bear_json is not None:
        result["bear_response"] = AgentResponse.model_validate_json(row.bear_json).model_dump()
    if row.verdict_json is not None:
        result["thesis"] = TradeThesis.model_validate_json(row.verdict_json).model_dump()
    if row.vol_json is not None:
        result["vol_response"] = row.vol_json
    if row.rebuttal_json is not None:
        result["bull_rebuttal"] = row.rebuttal_json

    return result
