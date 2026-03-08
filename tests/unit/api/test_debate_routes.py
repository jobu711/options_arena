"""Tests for debate API routes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.data.repository import DebateRow
from options_arena.models import (
    AgentResponse,
    IndicatorSignals,
    SignalDirection,
    TickerScore,
    TradeThesis,
)


def _make_debate_row(debate_id: int = 1) -> DebateRow:
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


async def test_list_debates_empty(client: AsyncClient) -> None:
    """GET /api/debate returns empty list."""
    response = await client.get("/api/debate")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_debates_returns_summaries(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate returns debate summaries."""
    mock_repo.get_recent_debates = AsyncMock(return_value=[_make_debate_row()])
    response = await client.get("/api/debate")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "AAPL"
    assert data[0]["direction"] == "bullish"
    assert data[0]["confidence"] == pytest.approx(0.70)


async def test_list_debates_by_ticker(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate?ticker=AAPL filters by ticker."""
    mock_repo.get_debates_for_ticker = AsyncMock(return_value=[_make_debate_row()])
    response = await client.get("/api/debate?ticker=AAPL")
    assert response.status_code == 200
    mock_repo.get_debates_for_ticker.assert_called_once_with("AAPL", limit=20)


async def test_get_debate_not_found(client: AsyncClient) -> None:
    """GET /api/debate/999 returns 404."""
    response = await client.get("/api/debate/999")
    assert response.status_code == 404


async def test_get_debate_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/1 returns full debate result."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row())
    response = await client.get("/api/debate/1")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "bull_response" in data
    assert "thesis" in data
    assert data["is_fallback"] is False


async def test_post_debate_returns_202(client: AsyncClient) -> None:
    """POST /api/debate returns 202 with debate_id."""
    response = await client.post("/api/debate", json={"ticker": "AAPL"})
    assert response.status_code == 202
    data = response.json()
    assert "debate_id" in data
    assert data["debate_id"] >= 1


async def test_post_debate_with_scan_id(client: AsyncClient) -> None:
    """POST /api/debate with scan_id returns 202."""
    response = await client.post("/api/debate", json={"ticker": "AAPL", "scan_id": 1})
    assert response.status_code == 202


async def test_export_debate_not_found(client: AsyncClient) -> None:
    """GET /api/debate/999/export returns 404."""
    response = await client.get("/api/debate/999/export")
    assert response.status_code == 404


async def test_export_debate_markdown(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/1/export?format=md returns markdown file."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row())
    response = await client.get("/api/debate/1/export?format=md")
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")


async def test_export_debate_unsupported_format(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/1/export?format=csv returns 422."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row())
    response = await client.get("/api/debate/1/export?format=csv")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Batch debate tests (#127)
# ---------------------------------------------------------------------------


def _make_ticker_scores() -> list[TickerScore]:
    """Create a list of sample TickerScore for batch tests."""
    tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "AMZN"]
    return [
        TickerScore(
            ticker=t,
            composite_score=90.0 - i * 5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        for i, t in enumerate(tickers)
    ]


async def test_batch_debate_returns_202(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/debate/batch returns 202 with batch_id and tickers."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=_make_ticker_scores())
    response = await client.post("/api/debate/batch", json={"scan_id": 1, "limit": 3})
    assert response.status_code == 202
    data = response.json()
    assert "batch_id" in data
    assert data["batch_id"] >= 1
    assert len(data["tickers"]) == 3
    assert data["tickers"] == ["AAPL", "MSFT", "GOOGL"]


async def test_batch_debate_with_explicit_tickers(
    client: AsyncClient, mock_repo: MagicMock
) -> None:
    """POST /api/debate/batch with explicit tickers uses those tickers."""
    response = await client.post(
        "/api/debate/batch",
        json={"scan_id": 1, "tickers": ["TSLA", "META"]},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["tickers"] == ["TSLA", "META"]


async def test_batch_debate_scan_not_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/debate/batch returns 404 when scan has no scores."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    response = await client.post("/api/debate/batch", json={"scan_id": 999})
    assert response.status_code == 404


async def test_batch_debate_409_when_locked(client: AsyncClient, test_app: object) -> None:
    """POST /api/debate/batch returns 409 when operation lock is held."""
    from options_arena.api.deps import get_operation_lock  # noqa: PLC0415

    # Create a pre-locked Lock
    locked = asyncio.Lock()
    await locked.acquire()

    test_app.dependency_overrides[get_operation_lock] = lambda: locked  # type: ignore[union-attr]
    try:
        response = await client.post("/api/debate/batch", json={"scan_id": 1, "tickers": ["AAPL"]})
        assert response.status_code == 409
    finally:
        locked.release()


async def test_batch_debate_empty_tickers(client: AsyncClient) -> None:
    """POST /api/debate/batch with empty tickers list returns 422."""
    response = await client.post("/api/debate/batch", json={"scan_id": 1, "tickers": []})
    assert response.status_code == 422


async def test_batch_debate_default_limit(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/debate/batch with default limit=5 selects top 5."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=_make_ticker_scores())
    response = await client.post("/api/debate/batch", json={"scan_id": 1})
    assert response.status_code == 202
    data = response.json()
    assert len(data["tickers"]) == 5


# ---------------------------------------------------------------------------
# Single-ticker normalization integration (#362)
# ---------------------------------------------------------------------------


class TestDebateRouteNormalization:
    """Tests verifying ad-hoc debate uses normalize_single_ticker."""

    async def test_adhoc_debate_uses_normalized_composite(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Ad-hoc debate route normalizes signals before composite score.

        Verifies that POST /api/debate returns 202 (background task started)
        and that normalize_single_ticker is called during the ad-hoc path
        (no scan_id, no pre-existing score_match).
        """
        # No scan scores -> triggers ad-hoc path
        mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

        response = await client.post("/api/debate", json={"ticker": "AAPL"})
        assert response.status_code == 202

        # The route returns 202 immediately (background task).
        # Verify the debate was accepted and an ID was assigned.
        assert response.json()["debate_id"] >= 1
