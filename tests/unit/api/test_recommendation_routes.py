"""Tests for recommendation API routes (#670).

Verifies POST /api/debate starts recommendation tasks, GET /api/debate/{id}
performs dual-table lookup, and batch endpoint uses run_recommendation().
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.data._recommendation import RecommendationRow
from options_arena.data.repository import DebateRow
from options_arena.models import (
    AgentResponse,
    SignalDirection,
    TradeThesis,
)


def _make_recommendation_row(rec_id: int = 1) -> RecommendationRow:
    """Build a RecommendationRow with realistic data."""
    import json

    assessments = [
        {
            "desk": "trend",
            "direction": "bullish",
            "confidence": 0.8,
            "summary": "Strong uptrend confirmed.",
            "key_factors": ["ADX > 25", "RSI trending up"],
            "risks": ["Earnings in 14 days"],
            "contracts_referenced": ["AAPL 190C"],
            "tools_used": ["fetch_quote"],
            "model_used": "llama-3.3-70b-versatile",
        },
    ]
    return RecommendationRow(
        id=rec_id,
        ticker="AAPL",
        scan_run_id=None,
        direction="bullish",
        confidence=0.75,
        recommended_contract="AAPL 190C 2026-04-18",
        entry_price="5.25",
        entry_criteria="Buy on pullback to support.",
        exit_criteria="Exit at 50% profit or 30% loss.",
        stop_loss="3.00",
        take_profit="8.00",
        position_size_pct=0.05,
        risk_reward_ratio=1.5,
        recommended_strategy="vertical",
        summary="Bullish momentum play on AAPL.",
        key_factors_json=json.dumps(["Strong uptrend", "Healthy volume"]),
        risk_assessment="Moderate risk — earnings approaching.",
        agent_agreement_score=0.85,
        dissenting_desks_json=json.dumps(["contrarian"]),
        assessments_json=json.dumps(assessments),
        total_input_tokens=3000,
        total_output_tokens=2000,
        duration_ms=4500,
        is_fallback=False,
        citation_density=0.45,
        position_rationale="Position sized for moderate conviction.",
        strategy_rationale="Bull call spread for defined risk.",
        max_loss_estimate="$250 per contract",
        model_used="llama-3.3-70b-versatile",
        created_at="2026-03-22T12:00:00+00:00",
    )


def _make_debate_row(debate_id: int = 1) -> DebateRow:
    """Build a DebateRow with realistic old-format data."""
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        argument="Strong momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings risk"],
        contracts_referenced=["AAPL 190C"],
        model_used="llama-3.3-70b",
    )
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        summary="Buy the dip.",
        bull_score=7.5,
        bear_score=4.5,
        key_factors=["Strong RSI"],
        risk_assessment="Moderate risk.",
    )
    return DebateRow(
        id=debate_id,
        scan_run_id=1,
        ticker="AAPL",
        bull_json=bull.model_dump_json(),
        bear_json=bull.model_dump_json(),
        risk_json=thesis.model_dump_json(),
        verdict_json=thesis.model_dump_json(),
        vol_json=None,
        rebuttal_json=None,
        total_tokens=1000,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        is_fallback=False,
        created_at=datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# POST /api/debate — start recommendation
# ---------------------------------------------------------------------------


@pytest.mark.critical
async def test_start_recommendation(client: AsyncClient) -> None:
    """POST /api/debate returns 202 with debate_id."""
    response = await client.post("/api/debate", json={"ticker": "AAPL"})
    assert response.status_code == 202
    data = response.json()
    assert "debate_id" in data
    assert isinstance(data["debate_id"], int)


async def test_start_recommendation_normalizes_ticker(client: AsyncClient) -> None:
    """POST /api/debate uppercases ticker."""
    response = await client.post("/api/debate", json={"ticker": "aapl"})
    assert response.status_code == 202


async def test_start_recommendation_invalid_ticker(client: AsyncClient) -> None:
    """POST /api/debate rejects invalid ticker format."""
    response = await client.post("/api/debate", json={"ticker": "@@@@"})
    assert response.status_code == 422


async def test_start_recommendation_with_scan_id(client: AsyncClient) -> None:
    """POST /api/debate accepts optional scan_id."""
    response = await client.post("/api/debate", json={"ticker": "MSFT", "scan_id": 5})
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# GET /api/debate/{id} — dual table lookup
# ---------------------------------------------------------------------------


async def test_get_recommendation_result(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/{id} returns RecommendationResponse for new data."""
    rec_row = _make_recommendation_row(rec_id=1)
    mock_repo.get_recommendation_by_id = AsyncMock(return_value=rec_row)

    response = await client.get("/api/debate/1")
    assert response.status_code == 200
    data = response.json()
    assert "recommendation" in data
    assert "assessments" in data
    assert data["ticker"] == "AAPL"
    assert data["is_fallback"] is False
    assert data["recommendation_protocol"] == "unified_v1"
    assert "recommendation" in data
    assert data["recommendation"]["ticker"] == "AAPL"
    assert data["recommendation"]["confidence"] == pytest.approx(0.75)


async def test_get_old_debate_backward_compat(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/{old_id} returns old DebateResultDetail for legacy data."""
    # Recommendation lookup returns None, debate lookup returns old data
    mock_repo.get_recommendation_by_id = AsyncMock(return_value=None)
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row(debate_id=999))

    response = await client.get("/api/debate/999")
    assert response.status_code == 200
    data = response.json()
    # Old debate format has thesis, bull_response, bear_response
    assert "thesis" in data
    assert data["ticker"] == "AAPL"
    assert data["is_fallback"] is False


async def test_get_debate_not_found_both_tables(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/{id} returns 404 when ID in neither table."""
    mock_repo.get_recommendation_by_id = AsyncMock(return_value=None)
    mock_repo.get_debate_by_id = AsyncMock(return_value=None)

    response = await client.get("/api/debate/9999")
    assert response.status_code == 404


async def test_get_recommendation_fallback_flag(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Verify is_fallback=True is correctly returned."""
    rec_row = _make_recommendation_row(rec_id=2)
    rec_row.is_fallback = True
    rec_row.model_used = "data-driven-fallback"
    mock_repo.get_recommendation_by_id = AsyncMock(return_value=rec_row)

    response = await client.get("/api/debate/2")
    assert response.status_code == 200
    data = response.json()
    assert data["is_fallback"] is True
    assert data["model_used"] == "data-driven-fallback"


# ---------------------------------------------------------------------------
# GET /api/debate — list summaries
# ---------------------------------------------------------------------------


async def test_list_debates_empty(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate returns empty list when no data."""
    mock_repo.get_recent_recommendations = AsyncMock(return_value=[])
    mock_repo.get_recent_debates = AsyncMock(return_value=[])
    response = await client.get("/api/debate")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_debates_includes_both_types(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate merges recommendations and old debates."""
    mock_repo.get_recent_recommendations = AsyncMock(
        return_value=[_make_recommendation_row(rec_id=10)]
    )
    mock_repo.get_recent_debates = AsyncMock(return_value=[_make_debate_row(debate_id=5)])
    response = await client.get("/api/debate")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


# ---------------------------------------------------------------------------
# POST /api/debate/batch — batch recommendation
# ---------------------------------------------------------------------------


async def test_batch_recommendation_starts(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/debate/batch returns 202 with batch_id and tickers."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    response = await client.post(
        "/api/debate/batch",
        json={"scan_id": 1, "tickers": ["AAPL", "MSFT"]},
    )
    assert response.status_code == 202
    data = response.json()
    assert "batch_id" in data
    assert data["tickers"] == ["AAPL", "MSFT"]


async def test_batch_no_tickers_422(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/debate/batch returns 422 for empty ticker list."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    response = await client.post(
        "/api/debate/batch",
        json={"scan_id": 1, "tickers": []},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Operation mutex (409)
# ---------------------------------------------------------------------------


async def test_operation_mutex_409(
    client: AsyncClient, mock_repo: MagicMock, test_app: object
) -> None:
    """POST /api/debate/batch returns 409 when lock is held."""
    # Manually acquire the lock before the request
    from options_arena.api.deps import get_operation_lock

    lock = asyncio.Lock()
    await lock.acquire()  # Hold the lock

    # Override the lock dependency to return our pre-locked lock
    test_app.dependency_overrides[get_operation_lock] = lambda: lock  # type: ignore[union-attr]

    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

    response = await client.post(
        "/api/debate/batch",
        json={"scan_id": 1, "tickers": ["AAPL"]},
    )
    assert response.status_code == 409

    # Clean up
    lock.release()


# ---------------------------------------------------------------------------
# No run_debate import in debate routes
# ---------------------------------------------------------------------------


def test_no_run_debate_import() -> None:
    """Verify debate routes no longer import run_debate."""
    import inspect

    from options_arena.api.routes import debate as debate_module

    source = inspect.getsource(debate_module)
    # run_debate should not be imported — run_recommendation is the replacement
    assert "from options_arena.agents import" in source or "run_recommendation" in source
    # The old run_debate import should be gone
    lines = source.split("\n")
    import_lines = [ln for ln in lines if "import" in ln and "run_debate" in ln]
    assert len(import_lines) == 0, f"run_debate still imported: {import_lines}"
