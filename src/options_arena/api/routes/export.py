"""Debate export endpoint — Markdown file download."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from options_arena.api.app import limiter
from options_arena.api.deps import get_repo
from options_arena.data import Repository
from options_arena.models import (
    AgentResponse,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    RiskAssessment,
    TradeThesis,
)
from options_arena.reporting import export_debate_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/debate/{debate_id}/export")
@limiter.limit("60/minute")
async def export_debate(
    request: Request,
    debate_id: int,
    repo: Repository = Depends(get_repo),
    fmt: str = Query("md", alias="format"),
) -> FileResponse:
    """Export a debate result as a downloadable Markdown file.

    Supports ``?format=md`` (default).
    """
    row = await repo.get_debate_by_id(debate_id)
    if row is None:
        raise HTTPException(404, "Debate not found")

    if fmt != "md":
        raise HTTPException(422, f"Unsupported format: {fmt}")

    # Reconstruct a minimal DebateResult for the export function
    from datetime import UTC, datetime
    from decimal import Decimal

    from pydantic_ai.usage import RunUsage

    from options_arena.agents._parsing import DebateResult
    from options_arena.models import (
        ExerciseStyle,
        MacdSignal,
        MarketContext,
        SignalDirection,
        VolatilityThesis,
    )

    # Parse stored JSON
    bull_response = (
        AgentResponse.model_validate_json(row.bull_json)
        if row.bull_json
        else AgentResponse(
            agent_name="bull",
            direction=SignalDirection.BULLISH,
            confidence=0.0,
            argument="No data",
            key_points=[],
            risks_cited=[],
            contracts_referenced=[],
            model_used=row.model_name,
        )
    )
    bear_response = (
        AgentResponse.model_validate_json(row.bear_json)
        if row.bear_json
        else AgentResponse(
            agent_name="bear",
            direction=SignalDirection.BEARISH,
            confidence=0.0,
            argument="No data",
            key_points=[],
            risks_cited=[],
            contracts_referenced=[],
            model_used=row.model_name,
        )
    )
    thesis = (
        TradeThesis.model_validate_json(row.verdict_json)
        if row.verdict_json
        else TradeThesis(
            ticker=row.ticker,
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            summary="No data",
            bull_score=0.0,
            bear_score=0.0,
            key_factors=[],
            risk_assessment="No data",
        )
    )

    vol_response: VolatilityThesis | None = None
    if row.vol_json:
        with contextlib.suppress(Exception):
            vol_response = VolatilityThesis.model_validate_json(row.vol_json)

    bull_rebuttal: AgentResponse | None = None
    if row.rebuttal_json:
        with contextlib.suppress(Exception):
            bull_rebuttal = AgentResponse.model_validate_json(row.rebuttal_json)

    # --- V2 agent outputs ---
    flow_response: FlowThesis | None = None
    with contextlib.suppress(Exception):
        if row.flow_json:
            flow_response = FlowThesis.model_validate_json(row.flow_json)

    fundamental_response: FundamentalThesis | None = None
    with contextlib.suppress(Exception):
        if row.fundamental_json:
            fundamental_response = FundamentalThesis.model_validate_json(row.fundamental_json)

    risk_v2_response: RiskAssessment | None = None
    with contextlib.suppress(Exception):
        if row.risk_v2_json:
            risk_v2_response = RiskAssessment.model_validate_json(row.risk_v2_json)

    contrarian_response: ContrarianThesis | None = None
    with contextlib.suppress(Exception):
        if row.contrarian_json:
            contrarian_response = ContrarianThesis.model_validate_json(row.contrarian_json)

    # Prefer persisted MarketContext; fall back to minimal placeholder
    context: MarketContext | None = row.market_context
    if context is None:
        context = MarketContext(
            ticker=row.ticker,
            current_price=Decimal("0"),
            price_52w_high=Decimal("0"),
            price_52w_low=Decimal("0"),
            rsi_14=50.0,
            macd_signal=MacdSignal.NEUTRAL,
            next_earnings=None,
            dte_target=30,
            target_strike=Decimal("0"),
            target_delta=0.0,
            sector="Unknown",
            dividend_yield=0.0,
            exercise_style=ExerciseStyle.AMERICAN,
            data_timestamp=datetime.now(UTC),
        )

    debate_result = DebateResult(
        context=context,
        bull_response=bull_response,
        bear_response=bear_response,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=row.duration_ms,
        is_fallback=row.is_fallback,
        vol_response=vol_response,
        bull_rebuttal=bull_rebuttal,
        flow_response=flow_response,
        fundamental_response=fundamental_response,
        risk_v2_response=risk_v2_response,
        contrarian_response=contrarian_response,
        debate_protocol=row.debate_protocol,
    )

    md_content = export_debate_markdown(debate_result)
    filename = f"{row.ticker}_debate_{debate_id}"

    if fmt == "md":
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp_fd:
            tmp_path = tmp_fd.name
        Path(tmp_path).write_text(md_content, encoding="utf-8")
        return FileResponse(
            path=tmp_path,
            filename=f"{filename}.md",
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}.md"'},
            background=BackgroundTask(os.unlink, tmp_path),
        )

    # Unreachable — format validated above; satisfies mypy return type
    raise HTTPException(422, f"Unsupported format: {fmt}")  # pragma: no cover
